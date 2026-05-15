import json
import logging
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count

from .models import Transaction, MerchantRule, CategoryBudget
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

    # Credits (salary/deposits) are auto-categorized — no manual review needed.
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
    valid_categories = [c[0] for c in Transaction.CATEGORIES]
    if category not in valid_categories:
        return JsonResponse({'error': 'invalid category'}, status=400)

    tx.category       = category
    tx.is_categorized = True
    tx.save(update_fields=['category', 'is_categorized'])

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


# ── GET /api/dashboard/ ───────────────────────────────────────────────────────

@require_http_methods(['GET'])
def dashboard_api(request):
    now = datetime.now()
    try:
        month = int(request.GET.get('month', now.month))
        year  = int(request.GET.get('year', now.year))
    except ValueError:
        return JsonResponse({'error': 'invalid month or year'}, status=400)

    qs      = Transaction.objects.filter(date__month=month, date__year=year)
    debits  = qs.filter(type='debit')
    credits = qs.filter(type='credit')

    total_spent  = debits.aggregate(s=Sum('amount'))['s'] or 0
    total_income = credits.aggregate(s=Sum('amount'))['s'] or 0

    latest        = qs.order_by('-created_at').first()
    balance_latest = float(latest.balance) if latest and latest.balance else 0

    # Category totals — categorized debits only
    by_category = list(
        debits.filter(is_categorized=True)
        .values('category')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    for row in by_category:
        row['total'] = float(row['total'])

    # Budget limits for future use
    budgets = {b.category: float(b.monthly_limit) for b in CategoryBudget.objects.all() if b.monthly_limit}

    # Recent transactions (last 20 of the selected month)
    recent = []
    for t in qs.order_by('-created_at')[:20]:
        recent.append({
            'id':       t.pk,
            'amount':   float(t.amount),
            'type':     t.type,
            'merchant': t.merchant,
            'category': t.category,
            'balance':  float(t.balance) if t.balance else None,
            'date':     t.date.strftime('%Y-%m-%d') if t.date else None,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    # Pending categorization — debit transactions across all time
    pending = []
    for t in Transaction.objects.filter(is_categorized=False, type='debit').order_by('-date', '-created_at'):
        pending.append({
            'id':       t.pk,
            'merchant': t.merchant or '—',
            'amount':   float(t.amount),
            'date':     t.date.strftime('%Y-%m-%d') if t.date else None,
        })

    return JsonResponse({
        'month':          month,
        'year':           year,
        'total_spent':    float(total_spent),
        'total_income':   float(total_income),
        'balance_latest': balance_latest,
        'by_category':    by_category,
        'budgets':        budgets,
        'recent':         recent,
        'pending':        pending,
    })


# ── GET / ─────────────────────────────────────────────────────────────────────

def dashboard_page(request):
    return render(request, 'dashboard.html')
