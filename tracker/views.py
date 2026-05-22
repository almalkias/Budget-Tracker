import json
import logging
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from .models import Transaction, CategoryBudget, BudgetCycle, MerchantMemory, ReserveBalance, Category, AppSettings
from .services.parser import parse_sms

logger = logging.getLogger('tracker')

RESERVE_CATEGORIES_IN  = {'reserve_in'}
RESERVE_CATEGORIES_OUT = {'reserve_out'}


def _adjust_reserve(delta: Decimal):
    """يعدّل رصيد الاحتياطي بمقدار delta (موجب = إضافة، سالب = سحب)."""
    rb = ReserveBalance.get()
    rb.balance += delta
    rb.save(update_fields=['balance', 'updated_at'])


def _category_delta(category: str, amount: Decimal) -> Decimal:
    """يرجع التأثير على رصيد الاحتياطي لفئة معينة."""
    if category in RESERVE_CATEGORIES_IN:
        return +amount
    if category in RESERVE_CATEGORIES_OUT:
        return -amount
    return Decimal('0')


def api_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'authentication required'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


# ── GET/POST /login/ ──────────────────────────────────────────────────────────

@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next', '/'))
        error = 'اسم المستخدم أو كلمة المرور غير صحيحة'
        logger.warning('Failed login attempt — username: %s', username)
    return render(request, 'login.html', {'error': error})


# ── POST /logout/ ─────────────────────────────────────────────────────────────

@require_http_methods(['POST'])
def logout_view(request):
    logout(request)
    return redirect('login')


# ── POST /api/sms/ ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def sms_webhook(request):
    logger.info('Webhook received — IP: %s', request.META.get('REMOTE_ADDR'))

    secret = request.headers.get('X-Secret', '') or request.GET.get('secret', '')
    if secret != settings.SMS_WEBHOOK_SECRET:
        logger.warning('Unauthorized webhook attempt — wrong secret')
        return JsonResponse({'error': 'unauthorized'}, status=401)

    logger.warning('RAW BODY: %s', request.body[:500].decode('utf-8', errors='replace'))

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning('Invalid JSON body: %r', request.body[:200])
        return JsonResponse({'error': 'invalid json'}, status=400)

    sender   = (body.get('sender') or '').strip()
    sms_text = (body.get('content') or body.get('sms') or '').strip()
    logger.warning('SMS SENDER: %r — TEXT: %r', sender, sms_text[:200])

    if sender != 'SNB-AlAhli':
        logger.info('Ignored SMS from sender: %r', sender)
        return JsonResponse({'status': 'ignored'})

    if not sms_text:
        return JsonResponse({'error': 'no sms'}, status=400)

    parsed = parse_sms(sms_text)
    if parsed is not None:
        auto_category = parsed.get('category')
        # عمليات الاحتياطي لا تُصنَّف تلقائياً — تنتظر التصنيف اليدوي
        if auto_category in RESERVE_CATEGORIES_IN | RESERVE_CATEGORIES_OUT:
            auto_category = None
        active_cycle  = BudgetCycle.objects.filter(status='active').first() if auto_category else None
        Transaction.objects.create(
            amount=parsed['amount'],
            type=parsed['type'],
            merchant=parsed['merchant'],
            category=auto_category or 'other',
            is_categorized=bool(auto_category),
            cycle=active_cycle,
            balance=parsed['balance'],
            date=parsed['date'],
            raw_sms=parsed['raw_sms'],
        )
        logger.info('Transaction saved — type=%s amount=%s category=%s', parsed['type'], parsed['amount'], auto_category or 'other')
    else:
        Transaction.objects.create(
            amount=Decimal('0'),
            type='debit',
            merchant='',
            category='other',
            is_categorized=False,
            balance=None,
            date=None,
            raw_sms=sms_text,
        )
        logger.info('Unrecognized format — saved raw SMS for manual review')

    return JsonResponse({'status': 'saved'})


# ── POST /api/transactions/<id>/categorize/ ───────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@api_login_required
def categorize_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    category = body.get('category', '').strip()
    if not category:
        return JsonResponse({'error': 'invalid category'}, status=400)

    active_cycle = BudgetCycle.objects.filter(status='active').first()
    if not active_cycle:
        return JsonResponse({'error': 'no active cycle'}, status=400)

    old_category      = tx.category
    tx.category       = category
    tx.is_categorized = True
    tx.cycle          = active_cycle
    tx.save(update_fields=['category', 'is_categorized', 'cycle'])

    if tx.merchant:
        MerchantMemory.objects.update_or_create(
            merchant=tx.merchant,
            defaults={'category': category},
        )

    delta = _category_delta(category, tx.amount) - _category_delta(old_category, tx.amount)
    if delta:
        _adjust_reserve(delta)

    # حفظ الفئة لو لم تكن موجودة في جدول الفئات
    Category.objects.get_or_create(key=category, defaults={'label': category})

    logger.info('Transaction categorized — id=%s category=%s cycle=%s', tx_id, category, active_cycle and active_cycle.pk)
    return JsonResponse({'status': 'ok'})


# ── DELETE /api/transactions/<id>/ ───────────────────────────────────────────

@csrf_exempt
@require_http_methods(['DELETE'])
@api_login_required
def delete_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)

    delta = _category_delta(tx.category, tx.amount)
    tx.delete()
    if delta:
        _adjust_reserve(-delta)
    logger.info('Transaction deleted — id=%s', tx_id)
    return JsonResponse({'status': 'deleted'})


# ── POST /api/transactions/<id>/split/ ───────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@api_login_required
def split_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    parts = body.get('parts', [])
    if len(parts) < 2:
        return JsonResponse({'error': 'need at least 2 parts'}, status=400)

    active_cycle = BudgetCycle.objects.filter(status='active').first()
    if not active_cycle:
        return JsonResponse({'error': 'no active cycle'}, status=400)

    try:
        amounts = [Decimal(str(p['amount'])) for p in parts]
        categories = [str(p['category']).strip() for p in parts]
    except Exception:
        return JsonResponse({'error': 'invalid parts'}, status=400)

    if any(a <= 0 for a in amounts):
        return JsonResponse({'error': 'amounts must be positive'}, status=400)

    if abs(sum(amounts) - tx.amount) > Decimal('0.01'):
        return JsonResponse({'error': f'parts sum {sum(amounts)} != original {tx.amount}'}, status=400)

    for amount, category in zip(amounts, categories):
        new_tx = Transaction.objects.create(
            amount=amount,
            type=tx.type,
            merchant=tx.merchant,
            category=category,
            is_categorized=True,
            cycle=active_cycle,
            balance=None,
            date=tx.date,
            raw_sms=tx.raw_sms,
        )
        delta = _category_delta(category, amount)
        if delta:
            _adjust_reserve(delta)
        if tx.merchant:
            MerchantMemory.objects.update_or_create(
                merchant=tx.merchant,
                defaults={'category': categories[-1]},
            )

    tx.delete()
    logger.info('Transaction split — id=%s into %s parts', tx_id, len(parts))
    return JsonResponse({'status': 'split'})


# ── POST /api/transactions/<id>/skip/ ────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@api_login_required
def skip_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)
    tx.is_skipped = True
    tx.save(update_fields=['is_skipped'])
    logger.info('Transaction skipped — id=%s', tx_id)
    return JsonResponse({'status': 'skipped'})

# ── POST /api/cycle/start/ ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@api_login_required
def cycle_start(request):
    if BudgetCycle.objects.filter(status='active').exists():
        return JsonResponse({'error': 'a cycle is already active'}, status=400)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    try:
        salary = Decimal(str(body['starting_balance']))
        month  = int(body['month'])
        year   = int(body['year'])
    except Exception:
        return JsonResponse({'error': 'invalid fields'}, status=400)

    if salary <= 0 or not (1 <= month <= 12):
        return JsonResponse({'error': 'invalid values'}, status=400)

    cycle = BudgetCycle.objects.create(
        month=month,
        year=year,
        salary=salary,
        started_at=timezone.now(),
        status='active',
    )
    logger.info('Cycle started — id=%s month=%s/%s salary=%s', cycle.pk, month, year, salary)
    return JsonResponse({'status': 'created', 'id': cycle.pk})


# ── POST /api/cycle/close/ ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@api_login_required
def cycle_close(request):
    cycle = BudgetCycle.objects.filter(status='active').first()
    if not cycle:
        return JsonResponse({'error': 'no active cycle'}, status=400)

    total_spent = (
        Transaction.objects
        .filter(type='debit', is_categorized=True, cycle=cycle)
        .aggregate(s=Sum('amount'))['s']
    ) or Decimal('0')

    cycle.status      = 'closed'
    cycle.closed_at   = timezone.now()
    cycle.total_spent = total_spent
    cycle.save(update_fields=['status', 'closed_at', 'total_spent'])

    logger.info('Cycle closed — id=%s total_spent=%s', cycle.pk, total_spent)
    return JsonResponse({'status': 'closed', 'total_spent': float(total_spent)})


# ── PATCH /api/cycle/update/ ──────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['PATCH'])
@api_login_required
def cycle_update(request):
    cycle = BudgetCycle.objects.filter(status='active').first()
    if not cycle:
        return JsonResponse({'error': 'no active cycle'}, status=400)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    try:
        new_salary = Decimal(str(body['salary']))
    except Exception:
        return JsonResponse({'error': 'invalid salary'}, status=400)

    if new_salary < 0:
        return JsonResponse({'error': 'invalid value'}, status=400)

    cycle.salary = new_salary
    cycle.save(update_fields=['salary'])

    logger.info('Cycle salary updated — id=%s salary=%s', cycle.pk, new_salary)
    return JsonResponse({
        'status': 'updated',
        'salary': float(new_salary),
    })


# ── DELETE /api/cycle/<id>/ ───────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['DELETE'])
@api_login_required
def cycle_delete(request, cycle_id):
    cycle = get_object_or_404(BudgetCycle, pk=cycle_id, status='closed')
    cycle.delete()
    logger.info('Cycle deleted — id=%s', cycle_id)
    return JsonResponse({'status': 'deleted'})


# ── GET /api/dashboard/ ───────────────────────────────────────────────────────

@require_http_methods(['GET'])
@api_login_required
def dashboard_api(request):
    cycle = BudgetCycle.objects.filter(status='active').first()

    if cycle:
        qs    = Transaction.objects.filter(cycle=cycle, is_skipped=False)
        month = cycle.month
        year  = cycle.year
    else:
        qs    = Transaction.objects.none()
        _now  = timezone.now()
        month = _now.month
        year  = _now.year

    debits = qs.filter(type='debit')

    # Category totals — month-filtered, categorized debits only (for bar chart)
    # Reserve transfers are excluded as they are not spending
    by_category = list(
        debits.filter(is_categorized=True)
        .exclude(category__in=['reserve_in', 'reserve_out'])
        .values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    for row in by_category:
        row['total'] = float(row['total'])

    budgets = {
        b.category: float(b.monthly_limit)
        for b in CategoryBudget.objects.all()
        if b.monthly_limit
    }

    # Recent transactions — current cycle only
    recent = []
    recent_qs = (
        Transaction.objects.filter(is_categorized=True, is_skipped=False, cycle=cycle)
        .order_by('-created_at')[:20]
        if cycle else []
    )
    for t in recent_qs:
        recent.append({
            'id':         t.pk,
            'amount':     float(t.amount),
            'type':       t.type,
            'merchant':   t.merchant,
            'category':   t.category,
            'balance':    float(t.balance) if t.balance else None,
            'date':       t.date.strftime('%Y-%m-%d') if t.date else None,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    # Pending — global, all uncategorized non-skipped transactions
    memory = {m.merchant: m.category for m in MerchantMemory.objects.all()}
    pending = []
    for t in Transaction.objects.filter(is_categorized=False, is_skipped=False).order_by('created_at'):
        pending.append({
            'id':                 t.pk,
            'amount':             float(t.amount),
            'type':               t.type,
            'merchant':           t.merchant,
            'raw_sms':            t.raw_sms,
            'date':               t.date.strftime('%Y-%m-%d') if t.date else None,
            'suggested_category': memory.get(t.merchant) if t.merchant else None,
        })

    # Active cycle — cycle-scoped summary cards
    active_cycle = None
    if cycle:
        total_expenses = (
            Transaction.objects
            .filter(type='debit', is_categorized=True, cycle=cycle)
            .exclude(category__in=['reserve_in', 'reserve_out'])
            .aggregate(s=Sum('amount'))['s']
        ) or Decimal('0')

        reserve_balance = float(ReserveBalance.get().balance)
        spending_percentage = (
            round(float(total_expenses / cycle.salary) * 100, 1)
            if cycle.salary > 0 else None
        )
        active_cycle = {
            'id':                  cycle.pk,
            'month':               cycle.month,
            'year':                cycle.year,
            'salary':              float(cycle.salary),
            'total_expenses':      float(total_expenses),
            'spending_percentage': spending_percentage,
            'tx_count':            qs.count(),
            'started_at':          cycle.started_at.strftime('%Y-%m-%d %H:%M'),
            'reserve_balance':     reserve_balance,
        }

    # Closed cycle history
    cycle_history = []
    for c in BudgetCycle.objects.filter(status='closed').order_by('-started_at'):
        spent = float(c.total_spent) if c.total_spent is not None else None
        spending_pct = (
            round(spent / float(c.salary) * 100, 1)
            if c.salary > 0 and spent is not None else None
        )
        cat_rows = list(
            Transaction.objects
            .filter(type='debit', is_categorized=True, cycle=c)
            .values('category')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        for row in cat_rows:
            row['total'] = float(row['total'])
        cycle_history.append({
            'id':                  c.pk,
            'month':               c.month,
            'year':                c.year,
            'salary':              float(c.salary),
            'total_spent':         spent,
            'spending_percentage': spending_pct,
            'by_category':         cat_rows,
            'closed_at':           c.closed_at.strftime('%Y-%m-%d') if c.closed_at else None,
        })

    categories = list(Category.objects.order_by('order', 'key').values('key', 'label'))

    app_settings = AppSettings.get()
    claude_cost = None
    if app_settings.use_claude_parser:
        input_cost  = app_settings.claude_input_tokens  / 1_000_000 * 3
        output_cost = app_settings.claude_output_tokens / 1_000_000 * 15
        claude_cost = round(input_cost + output_cost, 4)

    return JsonResponse({
        'month':         month,
        'year':          year,
        'by_category':   by_category,
        'budgets':       budgets,
        'recent':        recent,
        'pending':       pending,
        'active_cycle':  active_cycle,
        'cycle_history': cycle_history,
        'categories':    categories,
        'claude_cost':   claude_cost,
    })


# ── GET / ─────────────────────────────────────────────────────────────────────

@login_required
def dashboard_page(request):
    return render(request, 'dashboard.html')


# ── PWA: manifest.json ────────────────────────────────────────────────────────

def pwa_manifest(request):
    manifest = {
        "name": "مراقب الميزانية",
        "short_name": "ميزانيتي",
        "description": "تتبع مصروفاتك بذكاء",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#F5F4EF",
        "theme_color": "#D97757",
        "lang": "ar",
        "dir": "rtl",
        "icons": [
            {
                "src": "/static/tracker/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/tracker/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }
    return HttpResponse(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        content_type='application/manifest+json'
    )


# ── PWA: service worker ───────────────────────────────────────────────────────

def pwa_service_worker(request):
    sw_js = """
const CACHE = 'budget-tracker-v1';

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(['/login/']))
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.url.includes('/api/') || e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
"""
    return HttpResponse(sw_js, content_type='application/javascript')
