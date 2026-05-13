import json
import logging
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count

from .models import Transaction
from .services.parser import parse_sms
from .services.classifier import classify

logger = logging.getLogger('tracker')


# ── POST /api/sms/ ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def sms_webhook(request):
    logger.info('Webhook received — IP: %s', request.META.get('REMOTE_ADDR'))

    # Accept secret from X-Secret header OR ?secret= query param
    secret = request.headers.get('X-Secret', '') or request.GET.get('secret', '')
    if secret != settings.SMS_WEBHOOK_SECRET:
        logger.warning('Unauthorized webhook attempt — wrong secret')
        return JsonResponse({'error': 'unauthorized'}, status=401)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning('Invalid JSON body: %r', request.body[:200])
        return JsonResponse({'error': 'invalid json'}, status=400)

    # Support both 'content' (Forward SMS app) and 'sms' (direct/test)
    sms_text = (body.get('content') or body.get('sms') or '').strip()
    logger.debug('SMS text: %r', sms_text[:100])

    if not sms_text:
        logger.warning('Empty sms/content field in body')
        return JsonResponse({'error': 'no sms'}, status=400)

    parsed = parse_sms(sms_text)
    if parsed is None:
        logger.info('Skipped — unrecognized format: %r', sms_text[:60])
        return JsonResponse({'status': 'skipped', 'reason': 'unrecognized format'}, status=200)

    category = classify(sms_text)
    logger.info('Parsed OK — type=%s amount=%s merchant=%r category=%s',
                parsed['type'], parsed['amount'], parsed['merchant'], category)

    Transaction.objects.create(
        amount=parsed['amount'],
        type=parsed['type'],
        merchant=parsed['merchant'],
        category=category,
        balance=parsed['balance'],
        date=parsed['date'],
        raw_sms=parsed['raw_sms'],
    )

    logger.info('Transaction saved successfully')
    return JsonResponse({'status': 'saved', 'category': category})


# ── GET /api/dashboard/ ───────────────────────────────────────────────────────

@require_http_methods(['GET'])
def dashboard_api(request):
    now = datetime.now()
    try:
        month = int(request.GET.get('month', now.month))
        year = int(request.GET.get('year', now.year))
    except ValueError:
        return JsonResponse({'error': 'invalid month or year'}, status=400)

    qs = Transaction.objects.filter(date__month=month, date__year=year)

    debits = qs.filter(type='debit')
    credits = qs.filter(type='credit')

    total_spent = debits.aggregate(s=Sum('amount'))['s'] or 0
    total_income = credits.aggregate(s=Sum('amount'))['s'] or 0

    latest = qs.order_by('-created_at').first()
    balance_latest = float(latest.balance) if latest and latest.balance else 0

    by_category = list(
        debits
        .values('category')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    for row in by_category:
        row['total'] = float(row['total'])

    recent = []
    for t in qs.order_by('-created_at')[:20]:
        recent.append({
            'amount': float(t.amount),
            'type': t.type,
            'merchant': t.merchant,
            'category': t.category,
            'balance': float(t.balance) if t.balance else None,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    return JsonResponse({
        'month': month,
        'year': year,
        'total_spent': float(total_spent),
        'total_income': float(total_income),
        'balance_latest': balance_latest,
        'by_category': by_category,
        'recent': recent,
    })


# ── GET / ─────────────────────────────────────────────────────────────────────

def dashboard_page(request):
    return render(request, 'dashboard.html')
