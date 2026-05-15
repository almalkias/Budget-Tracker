import re
from datetime import date


def _clean_amount(raw: str) -> float:
    return float(raw.replace(',', '').replace(' ', ''))


def parse_sms(sms_text: str) -> dict | None:
    """
    يحلّل رسائل SMS من البنك الأهلي السعودي ويرجع dict أو None إذا لم يُعرف النمط.
    """
    sms = sms_text.strip()

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

    # ── نمط الحوالة بين الحسابات ─────────────────────────────────────────────
    # حوالة بين حساباتك
    # من 0102*  مبلغ 1 SAR  إلى 1110*  في 15/05/26 14:58
    internal_transfer_pattern = re.compile(
        r'حوالة بين حساباتك'
        r'.*?مبلغ\s+([\d,]+\.?\d*)\s+SAR'
        r'.*?في\s+(\d{2}/\d{2}/\d{2,4})',
        re.DOTALL,
    )

    def parse_date(raw: str) -> date:
        d, m, y = raw.split('/')
        # دعم السنة بصيغتين: YY أو YYYY
        y = int(y)
        if y < 100:
            y += 2000
        return date(y, int(m), int(d))

    # محاولة الإيداع
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

    return None
