import json
import logging
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, F

from .models import Transaction, MerchantRule, CategoryBudget, BudgetCycle
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
    if parsed is None:
        logger.info('Skipped — unrecognized format: %r', sms_text[:60])
        return JsonResponse({'status': 'skipped', 'reason': 'unrecognized format'}, status=200)

    if parsed['type'] == 'credit':
        category       = 'other'
        is_categorized = True
    else:
        merchant = parsed['merchant'].strip()
        rule     = MerchantRule.objects.filter(merchant__iexact=merchant).first() if merchant else None
        if rule:
            category       = rule.category
            is_categorized = True
            logger.info('Merchant rule hit — merchant=%r category=%s', merchant, category)
        else:
            category       = 'other'
            is_categorized = False

    logger.info('Parsed OK — type=%s amount=%s merchant=%r category=%s categorized=%s',
                parsed['type'], parsed['amount'], parsed['merchant'], category, is_categorized)

    Transaction.objects.create(
        amount=parsed['amount'],
        type=parsed['type'],
        merchant=parsed['merchant'],
        category=category,
        is_categorized=is_categorized,
        balance=parsed['balance'],
        date=parsed['date'],
        raw_sms=parsed['raw_sms'],
    )

    if is_categorized and parsed['type'] == 'debit':
        updated = BudgetCycle.objects.filter(status='active').update(
            remaining_balance=F('remaining_balance') - Decimal(str(parsed['amount']))
        )
        if updated:
            logger.info('Cycle decremented by %s (merchant rule match)', parsed['amount'])

    logger.info('Transaction saved successfully')
    return JsonResponse({'status': 'saved', 'category': category, 'is_categorized': is_categorized})


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
    if category not in [c[0] for c in Transaction.CATEGORIES]:
        return JsonResponse({'error': 'invalid category'}, status=400)

    tx.category       = category
    tx.is_categorized = True
    tx.save(update_fields=['category', 'is_categorized'])

    if tx.type == 'debit':
        updated = BudgetCycle.objects.filter(status='active').update(
            remaining_balance=F('remaining_balance') - tx.amount
        )
        if updated:
            logger.info('Cycle decremented by %s (manual categorize tx_id=%s)', tx.amount, tx_id)

    merchant_rule_saved = False
    merchant = tx.merchant.strip()
    if merchant:
        MerchantRule.objects.update_or_create(
            merchant=merchant,
            defaults={'category': category},
        )
        merchant_rule_saved = True
        logger.info('MerchantRule saved — merchant=%r category=%s', merchant, category)

    return JsonResponse({'status': 'ok', 'merchant_rule_saved': merchant_rule_saved})


# ── DELETE /api/transactions/<id>/ ───────────────────────────────────────────

@csrf_exempt
@require_http_methods(['DELETE'])
def delete_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)

    balance_restored = False
    if tx.type == 'debit' and tx.is_categorized:
        cycle = BudgetCycle.objects.filter(status='active').first()
        if cycle and tx.created_at >= cycle.started_at:
            BudgetCycle.objects.filter(status='active').update(
                remaining_balance=F('remaining_balance') + tx.amount
            )
            balance_restored = True
            logger.info('Balance restored — tx_id=%s amount=%s', tx_id, tx.amount)

    tx.delete()
    logger.info('Transaction deleted — id=%s', tx_id)
    return JsonResponse({'status': 'deleted', 'balance_restored': balance_restored})

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
        starting_balance = Decimal(str(body['starting_balance']))
        month = int(body['month'])
        year  = int(body['year'])
    except Exception:
        return JsonResponse({'error': 'invalid fields'}, status=400)

    if starting_balance <= 0 or not (1 <= month <= 12):
        return JsonResponse({'error': 'invalid values'}, status=400)

    cycle = BudgetCycle.objects.create(
        month=month,
        year=year,
        starting_balance=starting_balance,
        remaining_balance=starting_balance,
        started_at=timezone.now(),
        status='active',
    )
    logger.info('Cycle started — id=%s month=%s/%s balance=%s', cycle.pk, month, year, starting_balance)
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
        .filter(type='debit', is_categorized=True, created_at__gte=cycle.started_at)
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
        new_starting = Decimal(str(body['starting_balance']))
    except Exception:
        return JsonResponse({'error': 'invalid starting_balance'}, status=400)

    if new_starting <= 0:
        return JsonResponse({'error': 'invalid value'}, status=400)

    # Recompute remaining from actual transaction history
    total_spent = (
        Transaction.objects
        .filter(type='debit', is_categorized=True, created_at__gte=cycle.started_at)
        .aggregate(s=Sum('amount'))['s']
    ) or Decimal('0')

    cycle.starting_balance  = new_starting
    cycle.remaining_balance = new_starting - total_spent
    cycle.save(update_fields=['starting_balance', 'remaining_balance'])

    logger.info('Cycle updated — id=%s new_starting=%s remaining=%s',
                cycle.pk, new_starting, cycle.remaining_balance)
    return JsonResponse({
        'status':            'updated',
        'remaining_balance': float(cycle.remaining_balance),
    })


# ── GET /api/dashboard/ ───────────────────────────────────────────────────────

@require_http_methods(['GET'])
def dashboard_api(request):
    now = timezone.now()
    try:
        month = int(request.GET.get('month', now.month))
        year  = int(request.GET.get('year', now.year))
    except ValueError:
        return JsonResponse({'error': 'invalid month or year'}, status=400)

    qs     = Transaction.objects.filter(date__month=month, date__year=year)
    debits = qs.filter(type='debit')

    # Category totals — month-filtered, categorized debits only (for bar chart)
    by_category = list(
        debits.filter(is_categorized=True)
        .values('category')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    for row in by_category:
        row['total'] = float(row['total'])

    budgets = {
        b.category: float(b.monthly_limit)
        for b in CategoryBudget.objects.all()
        if b.monthly_limit
    }

    # Recent transactions — month-filtered (for table)
    recent = []
    for t in qs.filter(is_categorized=True).order_by('-created_at')[:20]:
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

    # Pending — global, all uncategorized debits
    pending = []
    for t in Transaction.objects.filter(is_categorized=False, type='debit').order_by('-date', '-created_at'):
        pending.append({
            'id':       t.pk,
            'merchant': t.merchant or '—',
            'amount':   float(t.amount),
            'date':     t.date.strftime('%Y-%m-%d') if t.date else None,
        })

    # Active cycle — cycle-scoped summary cards
    active_cycle = None
    cycle = BudgetCycle.objects.filter(status='active').first()
    if cycle:
        tx_count     = Transaction.objects.filter(created_at__gte=cycle.started_at).count()
        active_cycle = {
            'id':                cycle.pk,
            'month':             cycle.month,
            'year':              cycle.year,
            'starting_balance':  float(cycle.starting_balance),
            'remaining_balance': float(cycle.remaining_balance),
            'total_spent':       float(cycle.starting_balance - cycle.remaining_balance),
            'tx_count':          tx_count,
            'started_at':        cycle.started_at.strftime('%Y-%m-%d %H:%M'),
        }

    # Closed cycle history
    cycle_history = []
    for c in BudgetCycle.objects.filter(status='closed').order_by('-started_at'):
        spent = float(c.total_spent) if c.total_spent is not None else None
        cycle_history.append({
            'id':               c.pk,
            'month':            c.month,
            'year':             c.year,
            'starting_balance': float(c.starting_balance),
            'total_spent':      spent,
            'saved':            round(float(c.starting_balance) - spent, 2) if spent is not None else None,
            'closed_at':        c.closed_at.strftime('%Y-%m-%d') if c.closed_at else None,
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
