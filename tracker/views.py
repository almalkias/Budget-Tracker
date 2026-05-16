import json
import logging
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from .models import Transaction, CategoryBudget, BudgetCycle
from .services.parser import parse_sms

logger = logging.getLogger('tracker')


# ── POST /api/sms/ ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def sms_webhook(request):
    logger.info('Webhook received — IP: %s', request.META.get('REMOTE_ADDR'))

    secret = request.headers.get('X-Secret', '') or request.GET.get('secret', '')
    if secret != settings.SMS_WEBHOOK_SECRET:
        logger.warning('Unauthorized webhook attempt — wrong secret')
        return JsonResponse({'error': 'unauthorized'}, status=401)

    logger.warning('RAW BODY: %r', request.body[:500])

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning('Invalid JSON body: %r', request.body[:200])
        return JsonResponse({'error': 'invalid json'}, status=400)

    sms_text = (body.get('content') or body.get('sms') or '').strip()
    logger.warning('SMS TEXT: %r', sms_text[:200])

    if not sms_text:
        return JsonResponse({'error': 'no sms'}, status=400)

    parsed = parse_sms(sms_text)
    if parsed is not None:
        Transaction.objects.create(
            amount=parsed['amount'],
            type=parsed['type'],
            merchant=parsed['merchant'],
            category='other',
            is_categorized=False,
            balance=parsed['balance'],
            date=parsed['date'],
            raw_sms=parsed['raw_sms'],
        )
        logger.info('Transaction saved — type=%s amount=%s', parsed['type'], parsed['amount'])
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

    tx.category       = category
    tx.is_categorized = True
    tx.cycle          = active_cycle
    tx.save(update_fields=['category', 'is_categorized', 'cycle'])
    logger.info('Transaction categorized — id=%s category=%s cycle=%s', tx_id, category, active_cycle and active_cycle.pk)
    return JsonResponse({'status': 'ok'})


# ── DELETE /api/transactions/<id>/ ───────────────────────────────────────────

@csrf_exempt
@require_http_methods(['DELETE'])
def delete_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)

    tx.delete()
    logger.info('Transaction deleted — id=%s', tx_id)
    return JsonResponse({'status': 'deleted'})


# ── POST /api/transactions/<id>/skip/ ────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def skip_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)
    tx.is_skipped = True
    tx.save(update_fields=['is_skipped'])
    logger.info('Transaction skipped — id=%s', tx_id)
    return JsonResponse({'status': 'skipped'})


@csrf_exempt
@require_http_methods(['POST'])
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



# ── GET /api/dashboard/ ───────────────────────────────────────────────────────

@require_http_methods(['GET'])
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
    by_category = list(
        debits.filter(is_categorized=True)
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

    # Recent transactions — all categorized, no date filter
    recent = []
    for t in Transaction.objects.filter(is_categorized=True, is_skipped=False).order_by('-created_at')[:20]:
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
    pending = []
    for t in Transaction.objects.filter(is_categorized=False, is_skipped=False).order_by('created_at'):
        pending.append({
            'id':      t.pk,
            'amount':  float(t.amount),
            'type':    t.type,
            'raw_sms': t.raw_sms,
            'date':    t.date.strftime('%Y-%m-%d') if t.date else None,
        })

    # Active cycle — cycle-scoped summary cards
    active_cycle = None
    if cycle:
        total_expenses = (
            Transaction.objects
            .filter(type='debit', is_categorized=True, cycle=cycle)
            .aggregate(s=Sum('amount'))['s']
        ) or Decimal('0')
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

    return JsonResponse({
        'month':         month,
        'year':          year,
        'by_category':   by_category,
        'budgets':       budgets,
        'recent':        recent,
        'pending':       pending,
        'active_cycle':  active_cycle,
        'cycle_history': cycle_history,
    })


# ── GET / ─────────────────────────────────────────────────────────────────────

def dashboard_page(request):
    return render(request, 'dashboard.html')
