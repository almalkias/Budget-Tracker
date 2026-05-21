import json
import logging
import re
from datetime import date

logger = logging.getLogger('tracker')


def _clean_amount(raw: str) -> float:
    try:
        return float(raw.replace(',', '').replace(' ', ''))
    except (ValueError, TypeError):
        logger.warning('_clean_amount failed on %r — defaulting to 0.0', raw)
        return 0.0


# ── Generic amount extraction (fallback) ─────────────────────────────────────

_EXCLUDE_LINE = re.compile(r'الصرف المتبقي|الرصيد المتبقي|رسوم')

_AMOUNT_PATTERNS = [
    re.compile(r'مبلغ:?\s*([\d,]+\.?\d*)\s*SAR'),   # مبلغ: X SAR / مبلغ X SAR
    re.compile(r'مبلغ\s*SAR\s*([\d,]+\.?\d*)'),      # مبلغ SAR X
    re.compile(r'بـ\s*([\d,]+\.?\d*)\s*SAR'),         # بـ X SAR
    re.compile(r'مبلغ\s+([\d,]+\.?\d*)'),             # مبلغ X (بدون SAR)
    re.compile(r'([\d,]+\.?\d*)\s*SAR'),              # fallback: X SAR
]

_CREDIT_KEYWORDS = re.compile(r'إيداع|ايداع|واردة')


def _extract_amount(sms: str):
    lines = [l for l in sms.splitlines() if not _EXCLUDE_LINE.search(l)]
    text = '\n'.join(lines)
    for pat in _AMOUNT_PATTERNS:
        m = pat.search(text)
        if m:
            return _clean_amount(m.group(1))
    return None


def _parse_with_claude(sms: str) -> dict | None:
    """
    Try to extract amount, type, and date using Claude API.
    Returns dict with keys: amount (float), type (str), date (date|None)
    Returns None if the API call fails or returns unusable data.
    """
    try:
        from django.conf import settings
        import anthropic

        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            "Parse this Saudi bank SMS. Return ONLY JSON, no explanation:\n"
            '{"amount": <float in SAR. If foreign currency, multiply by exchange rate to get SAR. 0 if OTP/declined/no transaction>, '
            '"type": "credit" or "debit", '
            '"merchant": "<merchant name or empty string>", '
            '"date": "DD/MM/YY" or null}\n\n'
            "Rules:\n"
            "- credit = money received, debit = money sent/spent\n"
            "- If amount is in USD/EUR/other, convert to SAR using the exchange rate in the message\n"
            "- merchant: extract the store/recipient name, empty string if not found\n"
            "- OTP messages, declined transactions, notifications with no amount → amount: 0\n\n"
            f"{sms}"
        )

        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=128,
            messages=[{'role': 'user', 'content': prompt}],
        )

        # تجميع الـ tokens في AppSettings
        try:
            from tracker.models import AppSettings as _AS
            _s = _AS.get()
            _s.claude_input_tokens  += message.usage.input_tokens
            _s.claude_output_tokens += message.usage.output_tokens
            _s.save(update_fields=['claude_input_tokens', 'claude_output_tokens'])
        except Exception as _e:
            logger.warning('Failed to save Claude token usage: %s', _e)

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith('```'):
            raw = re.sub(r'^```[^\n]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        data = json.loads(raw)

        amount = float(data.get('amount') or 0)
        tx_type = data.get('type', 'debit')
        if tx_type not in ('credit', 'debit'):
            tx_type = 'debit'

        raw_date = data.get('date')
        parsed_date = None
        if raw_date:
            d, m, y = raw_date.split('/')
            y = int(y)
            if y < 100:
                y += 2000
            parsed_date = date(y, int(m), int(d))

        merchant = str(data.get('merchant') or '').strip()

        logger.debug('Claude parser succeeded: amount=%s type=%s merchant=%s date=%s', amount, tx_type, merchant, parsed_date)
        return {'amount': amount, 'type': tx_type, 'merchant': merchant, 'date': parsed_date}

    except Exception as exc:
        logger.warning('Claude parser failed, falling back to regex: %s', exc)
        return None


def parse_sms(sms_text: str) -> dict | None:
    """
    يحلّل رسائل SMS من البنك الأهلي السعودي ويرجع dict أو None إذا لم يُعرف النمط.
    """
    # Strip Unicode bidirectional + zero-width control characters
    sms = re.sub(r'[‎‏‪‫‬‭‮\u200b\u200c\u200d\u200e\u200f\ufeff]', '', sms_text)
    sms = re.sub(r' +', ' ', sms).strip()
    # Normalize Eastern Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) to ASCII
    sms = sms.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))

    # ── نمط الإيداع ──────────────────────────────────────────────────────────
    # تم إيداع 22,648.96 ر.س في حسابك رقم ****4986 بتاريخ 28/04/2026 الرصيد 22,690.59 ر.س
    credit_pattern = re.compile(
        r'تم إيداع\s+([\d,]+\.?\d*)\s+ر\.س\s+في حسابك'
        r'.*?بتاريخ\s+(\d{2}/\d{2}/\d{4})'
        r'.*?الرصيد\s+([\d,]+\.?\d*)\s+ر\.س',
        re.DOTALL,
    )

    # ── نمط الخصم في تاجر ────────────────────────────────────────────────────
    # تم الخصم 52.00 ر.س من حسابك رقم ****4986 بتاريخ 11/05/2026 في WHITE HEART الرصيد 5,127.91 ر.س
    debit_merchant_pattern = re.compile(
        r'تم الخصم\s+([\d,]+\.?\d*)\s+ر\.س\s+من حسابك'
        r'.*?بتاريخ\s+(\d{2}/\d{2}/\d{4})\s+في\s+(.+?)\s+الرصيد\s+([\d,]+\.?\d*)\s+ر\.س',
        re.DOTALL,
    )

    # ── نمط الخصم (تحويل / بدون تاجر) ───────────────────────────────────────
    # تم الخصم 200.00 ر.س من حسابك رقم ****4986 بتاريخ 10/05/2026 تحويل الى الاهل والاصدقاء الرصيد 5,344.10 ر.س
    debit_transfer_pattern = re.compile(
        r'تم الخصم\s+([\d,]+\.?\d*)\s+ر\.س\s+من حسابك'
        r'.*?بتاريخ\s+(\d{2}/\d{2}/\d{4})\s+(.+?)\s+الرصيد\s+([\d,]+\.?\d*)\s+ر\.س',
        re.DOTALL,
    )

    # ── نمط شراء POS / مدى ──────────────────────────────────────────────────
    # شراء-POS
    # بـ192 SAR
    # من HALA
    # مدى-ابل*4986
    # في 15/05/26 18:12
    pos_pattern = re.compile(
        r'شراء-POS'
        r'.*?بـ([\d,]+\.?\d*)\s+SAR'
        r'.*?من\s+([^\n]+)'
        r'.*?في\s+(\d{2}/\d{2}/\d{2,4})',
        re.DOTALL,
    )

    # ── نمط شراء انترنت / مدى (سطران من: رقم الحساب + التاجر) ──────────────
    # شراء انترنت
    # بـ69.71 SAR
    # من 0102*
    # من HUNGERSTA
    # مدى-ابل *4986
    # في 15/05/26 18:57
    online_purchase_pattern = re.compile(
        r'شراء انترنت'
        r'.*?بـ([\d,]+\.?\d*)\s+SAR'
        r'.*?من\s+\S+\*[^\n]*\n'   # سطر رقم الحساب (ينتهي بـ *)
        r'\s*من\s+([^\n]+)'         # سطر اسم التاجر
        r'.*?في\s+(\d{2}/\d{2}/\d{2,4})',
        re.DOTALL,
    )

    # ── نمط سداد بطاقة ائتمانية ─────────────────────────────────────────────
    # سداد بطاقة ائتمانية
    # من حساب *0102
    # الى بطاقة **2140
    # مبلغ SAR 1.00
    # في 15/05/26 23:56
    # الصرف المتبقي SAR 1.50
    credit_card_payment_pattern = re.compile(
        r'سداد بطاقة ائتمانية'
        r'.*?مبلغ\s+SAR\s+([\d,]+\.?\d*)'
        r'.*?في\s+(\d{2}/\d{2}/\d{2,4})'
        r'(?:.*?الصرف المتبقي\s+SAR\s+([\d,]+\.?\d*))?',
        re.DOTALL,
    )

    # ── نمط تحويل للاحتياطي (من 0102* إلى 1110*) ────────────────────────────
    # حوالة بين حساباتك
    # من 0102*  مبلغ 500 SAR  إلى 1110*  في 20/05/26 10:00
    reserve_in_pattern = re.compile(
        r'حوالة بين حساباتك'
        r'.*?من\s+0102\*'
        r'.*?مبلغ\s+([\d,]+\.?\d*)\s+SAR'
        r'.*?إلى\s+1110\*'
        r'.*?في\s+(\d{2}/\d{2}/\d{2,4})',
        re.DOTALL,
    )

    # ── نمط تحويل من الاحتياطي (من 1110* إلى 0102*) ─────────────────────────
    # حوالة بين حساباتك
    # من 1110*  مبلغ 500 SAR  إلى 0102*  في 20/05/26 10:00
    reserve_out_pattern = re.compile(
        r'حوالة بين حساباتك'
        r'.*?من\s+1110\*'
        r'.*?مبلغ\s+([\d,]+\.?\d*)\s+SAR'
        r'.*?في\s+(\d{2}/\d{2}/\d{2,4})',
        re.DOTALL,
    )

    # ── نمط الحوالة بين الحسابات ─────────────────────────────────────────────
    # حوالة بين حساباتك
    # من 0102*  مبلغ 1 SAR  إلى 1110*  في 15/05/26 14:58
    internal_transfer_pattern = re.compile(
        r'حوالة بين حساباتك'
        r'.*?مبلغ\s+([\d,]+\.?\d*)\s+SAR'
        r'.*?في\s+(\d{2}/\d{2}/\d{2,4})',
        re.DOTALL,
    )

    def parse_date(raw: str) -> date | None:
        try:
            d, m, y = raw.split('/')
            y = int(y)
            if y < 100:
                y += 2000
            return date(y, int(m), int(d))
        except (ValueError, TypeError):
            logger.warning('Could not parse date %r — date will be None', raw)
            return None

    # ── Parser selection ──────────────────────────────────────────────────────
    # To enable Claude API parser: set USE_CLAUDE_PARSER=True in .env
    # Claude API parser behaviour:
    #   None  → API failed (exception / bad JSON) → fall through to regex
    #   dict  → Claude responded; trust it completely
    #     amount > 0 → valid transaction
    #     amount = 0 → declined / OTP / not a transaction → return None immediately
    from tracker.models import AppSettings
    if AppSettings.get().use_claude_parser:
        claude_result = _parse_with_claude(sms)
        if claude_result is not None:
            if claude_result['amount'] > 0:
                return {
                    'amount':   claude_result['amount'],
                    'type':     claude_result['type'],
                    'merchant': claude_result['merchant'],
                    'balance':  None,
                    'date':     claude_result['date'],
                    'raw_sms':  sms,
                }
            # Claude returned amount=0 (declined / OTP / uncertain).
            # Fall through to regex as a safety net — if regex also finds
            # nothing, we return None. This prevents silently losing a real
            # transaction that Claude misclassified as declined.
            logger.info('Claude returned amount=0 — falling through to regex for verification')

    # ── محاولة الإيداع ────────────────────────────────────────────────────────
    m = credit_pattern.search(sms)
    if m:
        return {
            'amount': _clean_amount(m.group(1)),
            'type': 'credit',
            'merchant': '',
            'balance': _clean_amount(m.group(3)),
            'date': parse_date(m.group(2)),
            'raw_sms': sms,
        }

    # محاولة الخصم بتاجر
    m = debit_merchant_pattern.search(sms)
    if m:
        return {
            'amount': _clean_amount(m.group(1)),
            'type': 'debit',
            'merchant': m.group(3).strip(),
            'balance': _clean_amount(m.group(4)),
            'date': parse_date(m.group(2)),
            'raw_sms': sms,
        }

    # محاولة الخصم بتحويل/وصف
    m = debit_transfer_pattern.search(sms)
    if m:
        return {
            'amount': _clean_amount(m.group(1)),
            'type': 'debit',
            'merchant': m.group(3).strip(),
            'balance': _clean_amount(m.group(4)),
            'date': parse_date(m.group(2)),
            'raw_sms': sms,
        }

    # محاولة سداد بطاقة ائتمانية
    m = credit_card_payment_pattern.search(sms)
    if m:
        return {
            'amount':   _clean_amount(m.group(1)),
            'type':     'debit',
            'merchant': 'سداد بطاقة ائتمانية',
            'balance':  _clean_amount(m.group(3)) if m.group(3) else None,
            'date':     parse_date(m.group(2)),
            'raw_sms':  sms,
        }

    # محاولة تحويل للاحتياطي (0102* → 1110*)
    m = reserve_in_pattern.search(sms)
    if m:
        return {
            'amount':   _clean_amount(m.group(1)),
            'type':     'debit',
            'merchant': 'تحويل الى الاحتياطي',
            'balance':  None,
            'date':     parse_date(m.group(2)),
            'raw_sms':  sms,
            'category': 'reserve_in',
        }

    # محاولة تحويل من الاحتياطي (1110* → 0102*)
    m = reserve_out_pattern.search(sms)
    if m:
        return {
            'amount':   _clean_amount(m.group(1)),
            'type':     'debit',
            'merchant': 'تحويل من الاحتياطي',
            'balance':  None,
            'date':     parse_date(m.group(2)),
            'raw_sms':  sms,
            'category': 'reserve_out',
        }

    # محاولة الحوالة بين الحسابات
    m = internal_transfer_pattern.search(sms)
    if m:
        return {
            'amount': _clean_amount(m.group(1)),
            'type': 'debit',
            'merchant': 'حوالة بين الحسابات',
            'balance': None,
            'date': parse_date(m.group(2)),
            'raw_sms': sms,
        }

    # محاولة شراء POS / مدى
    m = pos_pattern.search(sms)
    if m:
        return {
            'amount': _clean_amount(m.group(1)),
            'type': 'debit',
            'merchant': m.group(2).strip(),
            'balance': None,
            'date': parse_date(m.group(3)),
            'raw_sms': sms,
        }

    # محاولة شراء انترنت / مدى
    m = online_purchase_pattern.search(sms)
    if m:
        return {
            'amount': _clean_amount(m.group(1)),
            'type': 'debit',
            'merchant': m.group(2).strip(),
            'balance': None,
            'date': parse_date(m.group(3)),
            'raw_sms': sms,
        }

    # ── Fallback: generic amount extraction ───────────────────────────────────
    amount = _extract_amount(sms)
    if amount is not None:
        tx_type = 'credit' if _CREDIT_KEYWORDS.search(sms) else 'debit'
        return {
            'amount':   amount,
            'type':     tx_type,
            'merchant': '',
            'balance':  None,
            'date':     None,
            'raw_sms':  sms,
        }

    return None
