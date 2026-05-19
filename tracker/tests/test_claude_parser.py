"""
Tests for the Claude-based SMS parser (_parse_with_claude) and parse_sms fallback.

Two test classes:
  - ClaudeParserUnitTests  : fully mocked, no API calls, fast
  - ClaudeParserLiveTests  : real API calls, skipped when ANTHROPIC_API_KEY is absent
"""

import json
import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import django
from django.test import TestCase, override_settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tracker.services.parser import _parse_with_claude, parse_sms  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_claude(json_payload: dict):
    """Return a mock anthropic client whose messages.create returns json_payload."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(json_payload))]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client


def _call(sms: str, payload: dict) -> dict | None:
    """Call _parse_with_claude with a mocked client returning payload."""
    with patch('anthropic.Anthropic', return_value=_mock_claude(payload)):
        with override_settings(ANTHROPIC_API_KEY='test-key', USE_CLAUDE_PARSER=True):
            return _parse_with_claude(sms)


def _call_parse_sms(sms: str, payload: dict) -> dict | None:
    """Call parse_sms with Claude enabled and a mocked client."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(payload))]
    )
    with patch('anthropic.Anthropic', return_value=mock_client):
        with override_settings(ANTHROPIC_API_KEY='test-key', USE_CLAUDE_PARSER=True):
            return parse_sms(sms)


# ── unit tests (mocked) ───────────────────────────────────────────────────────

class ClaudeParserUnitTests(TestCase):

    # ── formats from test_simulation.sh ──────────────────────────────────────

    def test_debit_merchant_inline(self):
        sms = "تم الخصم 42.00 ر.س من حسابك رقم ****4986 بتاريخ 01/05/2026 في STARBUCKS الرصيد 14,958.00 ر.س"
        result = _call(sms, {"amount": 42.0, "type": "debit", "date": "01/05/26"})
        self.assertEqual(result['amount'], 42.0)
        self.assertEqual(result['type'], 'debit')
        self.assertEqual(result['date'], date(2026, 5, 1))

    def test_debit_merchant_large_amount(self):
        sms = "تم الخصم 215.50 ر.س من حسابك رقم ****4986 بتاريخ 02/05/2026 في DANUBE MARKET الرصيد 14,742.50 ر.س"
        result = _call(sms, {"amount": 215.5, "type": "debit", "date": "02/05/26"})
        self.assertEqual(result['amount'], 215.5)
        self.assertEqual(result['date'], date(2026, 5, 2))

    def test_online_purchase_multiline(self):
        sms = "شراء انترنت\nبـ189.00 SAR\nمن 0102*\nمن AMAZON SA\nمدى-ابل *4986\nفي 03/05/26 14:22"
        result = _call(sms, {"amount": 189.0, "type": "debit", "date": "03/05/26"})
        self.assertEqual(result['amount'], 189.0)
        self.assertEqual(result['type'], 'debit')
        self.assertEqual(result['date'], date(2026, 5, 3))

    def test_credit_salary_deposit(self):
        sms = "تم إيداع 18,500.00 ر.س في حسابك رقم ****4986 بتاريخ 04/05/2026 الرصيد 33,036.50 ر.س"
        result = _call(sms, {"amount": 18500.0, "type": "credit", "date": "04/05/26"})
        self.assertEqual(result['amount'], 18500.0)
        self.assertEqual(result['type'], 'credit')

    def test_debit_bill_electricity(self):
        sms = "تم الخصم 380.00 ر.س من حسابك رقم ****4986 بتاريخ 05/05/2026 تحويل الى سداد الكهرباء الرصيد 32,656.50 ر.س"
        result = _call(sms, {"amount": 380.0, "type": "debit", "date": "05/05/26"})
        self.assertEqual(result['amount'], 380.0)
        self.assertEqual(result['type'], 'debit')

    def test_debit_bill_water(self):
        sms = "تم الخصم 95.00 ر.س من حسابك رقم ****4986 بتاريخ 05/05/2026 تحويل الى سداد المياه الرصيد 32,561.50 ر.س"
        result = _call(sms, {"amount": 95.0, "type": "debit", "date": "05/05/26"})
        self.assertEqual(result['amount'], 95.0)

    def test_debit_bill_telecom(self):
        sms = "تم الخصم 210.00 ر.س من حسابك رقم ****4986 بتاريخ 06/05/2026 تحويل الى سداد الاتصالات الرصيد 32,351.50 ر.س"
        result = _call(sms, {"amount": 210.0, "type": "debit", "date": "06/05/26"})
        self.assertEqual(result['amount'], 210.0)

    def test_credit_card_payment(self):
        sms = "سداد بطاقة ائتمانية\nمن حساب *0102\nالى بطاقة **2140\nمبلغ SAR 2,400.00\nفي 07/05/26 09:00\nالصرف المتبقي SAR 29,951.50"
        result = _call(sms, {"amount": 2400.0, "type": "debit", "date": "07/05/26"})
        self.assertEqual(result['amount'], 2400.0)
        self.assertEqual(result['type'], 'debit')
        self.assertEqual(result['date'], date(2026, 5, 7))

    def test_pos_purchase_multiline(self):
        sms = "شراء-POS\nبـ87.50 SAR\nمن AL NAHDI\nمدى-ابل*4986\nفي 09/05/26 11:30"
        result = _call(sms, {"amount": 87.5, "type": "debit", "date": "09/05/26"})
        self.assertEqual(result['amount'], 87.5)
        self.assertEqual(result['date'], date(2026, 5, 9))

    def test_online_purchase_hungerstation(self):
        sms = "شراء انترنت\nبـ65.00 SAR\nمن 0102*\nمن HUNGERSTATION\nمدى-ابل *4986\nفي 10/05/26 20:15"
        result = _call(sms, {"amount": 65.0, "type": "debit", "date": "10/05/26"})
        self.assertEqual(result['amount'], 65.0)

    def test_debit_rent_large(self):
        sms = "تم الخصم 3,500.00 ر.س من حسابك رقم ****4986 بتاريخ 16/05/2026 تحويل الى الايجار الرصيد 43,544.00 ر.س"
        result = _call(sms, {"amount": 3500.0, "type": "debit", "date": "16/05/26"})
        self.assertEqual(result['amount'], 3500.0)

    def test_pos_purchase_fuel(self):
        sms = "شراء-POS\nبـ150.00 SAR\nمن ALDREES\nمدى-ابل*4986\nفي 17/05/26 16:45"
        result = _call(sms, {"amount": 150.0, "type": "debit", "date": "17/05/26"})
        self.assertEqual(result['amount'], 150.0)
        self.assertEqual(result['date'], date(2026, 5, 17))

    def test_online_purchase_noon(self):
        sms = "شراء انترنت\nبـ430.00 SAR\nمن 0102*\nمن NOON SA\nمدى-ابل *4986\nفي 17/05/26 19:00"
        result = _call(sms, {"amount": 430.0, "type": "debit", "date": "17/05/26"})
        self.assertEqual(result['amount'], 430.0)

    # ── date format variations ────────────────────────────────────────────────

    def test_date_format_dd_mm_yyyy(self):
        sms = "تم الخصم 100.00 ر.س بتاريخ 01/05/2026"
        result = _call(sms, {"amount": 100.0, "type": "debit", "date": "01/05/26"})
        self.assertEqual(result['date'], date(2026, 5, 1))

    def test_date_format_dd_mm_yy(self):
        sms = "شراء-POS\nبـ50.00 SAR\nفي 15/03/26"
        result = _call(sms, {"amount": 50.0, "type": "debit", "date": "15/03/26"})
        self.assertEqual(result['date'], date(2026, 3, 15))

    def test_date_null(self):
        sms = "تم إيداع 500 ر.س في حسابك"
        result = _call(sms, {"amount": 500.0, "type": "credit", "date": None})
        self.assertIsNone(result['date'])

    # ── amount format variations ──────────────────────────────────────────────

    def test_amount_with_commas(self):
        sms = "تم إيداع 18,500.00 ر.س"
        result = _call(sms, {"amount": 18500.0, "type": "credit", "date": None})
        self.assertEqual(result['amount'], 18500.0)

    def test_amount_integer(self):
        sms = "شراء-POS\nبـ200 SAR\nفي 01/01/26"
        result = _call(sms, {"amount": 200.0, "type": "debit", "date": "01/01/26"})
        self.assertEqual(result['amount'], 200.0)

    def test_amount_small_decimal(self):
        sms = "مبلغ SAR 1.50\nفي 01/01/26"
        result = _call(sms, {"amount": 1.5, "type": "debit", "date": "01/01/26"})
        self.assertEqual(result['amount'], 1.5)

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_declined_transaction_skipped_by_parse_sms(self):
        sms = "رصيد غير كافي\nلـشراء نقاط البيع\nبـ416.06 SAR\nمن 0102*\nفي 09/23 17:46"
        result = _call_parse_sms(sms, {"amount": 0, "type": "debit", "date": None})
        self.assertIsNone(result, "Declined transaction should not be saved")

    def test_otp_message_skipped_by_parse_sms(self):
        sms = "لا تشارك رمز التفعيل 3965\nتحويل بين حساباتي\nمبلغ SAR 500"
        result = _call_parse_sms(sms, {"amount": 0, "type": "debit", "date": None})
        self.assertIsNone(result, "OTP message should not be saved")

    def test_internal_transfer_debit(self):
        sms = "حوالة بين حساباتك\nمن 0102*  مبلغ 1 SAR  إلى 1110*  في 15/05/26 14:58"
        result = _call(sms, {"amount": 1.0, "type": "debit", "date": "15/05/26"})
        self.assertEqual(result['type'], 'debit')

    def test_incoming_transfer_credit(self):
        sms = "حوالة واردة\nمبلغ SAR 5,000.00\nمن محمد أحمد\nفي 10/04/26 09:00"
        result = _call(sms, {"amount": 5000.0, "type": "credit", "date": "10/04/26"})
        self.assertEqual(result['type'], 'credit')

    def test_outgoing_transfer_debit(self):
        sms = "حوالة صادرة\nمبلغ SAR 1,000.00\nإلى أحمد خالد\nفي 12/04/26 11:30"
        result = _call(sms, {"amount": 1000.0, "type": "debit", "date": "12/04/26"})
        self.assertEqual(result['type'], 'debit')

    def test_atm_withdrawal(self):
        sms = "سحب صراف آلي\nمبلغ 500 SAR\nفي 20/04/26 18:00"
        result = _call(sms, {"amount": 500.0, "type": "debit", "date": "20/04/26"})
        self.assertEqual(result['type'], 'debit')
        self.assertEqual(result['amount'], 500.0)

    def test_salary_deposit_credit(self):
        sms = "ايداع رواتب\nمبلغ SAR 12,000.00\nفي 01/05/26"
        result = _call(sms, {"amount": 12000.0, "type": "credit", "date": "01/05/26"})
        self.assertEqual(result['type'], 'credit')

    def test_internet_purchase_alternative_spelling(self):
        # شراء إنترنت (with hamza) vs شراء انترنت (without)
        sms = "شراء إنترنت\nبـ99.00 SAR\nمن 0102*\nمن NETFLIX\nفي 05/05/26 00:00"
        result = _call(sms, {"amount": 99.0, "type": "debit", "date": "05/05/26"})
        self.assertEqual(result['amount'], 99.0)

    def test_bill_payment_sadad(self):
        sms = "سداد فاتورة\nمبلغ SAR 320.00\nالجهة: STC\nفي 16/05/26 08:45"
        result = _call(sms, {"amount": 320.0, "type": "debit", "date": "16/05/26"})
        self.assertEqual(result['type'], 'debit')

    def test_ministry_payment_credit(self):
        sms = "مدفوعات وزارة الداخلية\nمبلغ SAR 2,000.00\nفي 01/04/26"
        result = _call(sms, {"amount": 2000.0, "type": "credit", "date": "01/04/26"})
        self.assertEqual(result['type'], 'credit')

    # ── response robustness ───────────────────────────────────────────────────

    def test_markdown_fenced_json_is_stripped(self):
        sms = "تم الخصم 50.00 ر.س بتاريخ 01/05/26"
        fenced = "```json\n{\"amount\": 50.0, \"type\": \"debit\", \"date\": \"01/05/26\"}\n```"
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=fenced)]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        with patch('anthropic.Anthropic', return_value=mock_client):
            with override_settings(ANTHROPIC_API_KEY='test-key', USE_CLAUDE_PARSER=True):
                result = _parse_with_claude(sms)
        self.assertIsNotNone(result)
        self.assertEqual(result['amount'], 50.0)

    def test_invalid_type_defaults_to_debit(self):
        sms = "عملية غير معروفة 100 SAR"
        result = _call(sms, {"amount": 100.0, "type": "unknown", "date": None})
        self.assertEqual(result['type'], 'debit')

    def test_no_api_key_returns_none(self):
        with override_settings(ANTHROPIC_API_KEY=''):
            result = _parse_with_claude("any sms")
        self.assertIsNone(result)

    # ── fallback to regex ─────────────────────────────────────────────────────

    def test_api_error_falls_back_to_regex(self):
        """When Claude raises an exception, parse_sms should still succeed via regex."""
        sms = "تم الخصم 42.00 ر.س من حسابك رقم ****4986 بتاريخ 01/05/2026 في STARBUCKS الرصيد 14,958.00 ر.س"
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("network error")
        with patch('anthropic.Anthropic', return_value=mock_client):
            with override_settings(ANTHROPIC_API_KEY='test-key', USE_CLAUDE_PARSER=True):
                result = parse_sms(sms)
        self.assertIsNotNone(result)
        self.assertEqual(result['amount'], 42.0)
        self.assertEqual(result['type'], 'debit')

    def test_malformed_json_falls_back_to_regex(self):
        """When Claude returns invalid JSON, parse_sms should fall back to regex."""
        sms = "تم إيداع 18,500.00 ر.س في حسابك رقم ****4986 بتاريخ 04/05/2026 الرصيد 33,036.50 ر.س"
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="not json at all")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        with patch('anthropic.Anthropic', return_value=mock_client):
            with override_settings(ANTHROPIC_API_KEY='test-key', USE_CLAUDE_PARSER=True):
                result = parse_sms(sms)
        self.assertIsNotNone(result)
        self.assertEqual(result['amount'], 18500.0)
        self.assertEqual(result['type'], 'credit')

    def test_flag_disabled_skips_claude(self):
        """When USE_CLAUDE_PARSER=False, Claude is never called and regex runs."""
        sms = "تم الخصم 42.00 ر.س من حسابك رقم ****4986 بتاريخ 01/05/2026 في STARBUCKS الرصيد 14,958.00 ر.س"
        mock_client = MagicMock()
        with patch('anthropic.Anthropic', return_value=mock_client):
            with override_settings(USE_CLAUDE_PARSER=False):
                result = parse_sms(sms)
        mock_client.messages.create.assert_not_called()
        self.assertEqual(result['amount'], 42.0)


# ── live integration tests (skipped without real key) ────────────────────────

@unittest.skipUnless(os.getenv('ANTHROPIC_API_KEY'), "ANTHROPIC_API_KEY not set — skipping live tests")
class ClaudeParserLiveTests(TestCase):
    """
    Calls the real Claude API. Run with:
        ANTHROPIC_API_KEY=sk-... python manage.py test tracker.tests.test_claude_parser.ClaudeParserLiveTests
    """

    def _live(self, sms: str) -> dict | None:
        from django.conf import settings
        with override_settings(ANTHROPIC_API_KEY=os.getenv('ANTHROPIC_API_KEY', settings.ANTHROPIC_API_KEY)):
            return _parse_with_claude(sms)

    def test_live_debit_merchant(self):
        r = self._live("تم الخصم 42.00 ر.س من حسابك رقم ****4986 بتاريخ 01/05/2026 في STARBUCKS الرصيد 14,958.00 ر.س")
        self.assertEqual(r['amount'], 42.0)
        self.assertEqual(r['type'], 'debit')
        self.assertEqual(r['date'], date(2026, 5, 1))

    def test_live_credit_salary(self):
        r = self._live("تم إيداع 18,500.00 ر.س في حسابك رقم ****4986 بتاريخ 04/05/2026 الرصيد 33,036.50 ر.س")
        self.assertEqual(r['amount'], 18500.0)
        self.assertEqual(r['type'], 'credit')

    def test_live_pos_purchase(self):
        r = self._live("شراء-POS\nبـ87.50 SAR\nمن AL NAHDI\nمدى-ابل*4986\nفي 09/05/26 11:30")
        self.assertEqual(r['amount'], 87.5)
        self.assertEqual(r['type'], 'debit')
        self.assertEqual(r['date'], date(2026, 5, 9))

    def test_live_credit_card_payment(self):
        r = self._live("سداد بطاقة ائتمانية\nمن حساب *0102\nالى بطاقة **2140\nمبلغ SAR 2,400.00\nفي 07/05/26 09:00\nالصرف المتبقي SAR 29,951.50")
        self.assertEqual(r['amount'], 2400.0)
        self.assertEqual(r['type'], 'debit')

    def test_live_declined_returns_none(self):
        r = self._live("رصيد غير كافي\nلـشراء نقاط البيع\nبـ416.06 SAR\nمن 0102*\nفي 09/23 17:46")
        self.assertIsNone(r)

    def test_live_otp_returns_none(self):
        r = self._live("لا تشارك رمز التفعيل 3965\nتحويل بين حساباتي\nمبلغ SAR 500")
        self.assertIsNone(r)

    def test_live_online_purchase(self):
        r = self._live("شراء انترنت\nبـ430.00 SAR\nمن 0102*\nمن NOON SA\nمدى-ابل *4986\nفي 17/05/26 19:00")
        self.assertEqual(r['amount'], 430.0)
        self.assertEqual(r['type'], 'debit')
        self.assertEqual(r['date'], date(2026, 5, 17))

    def test_live_incoming_transfer(self):
        r = self._live("حوالة واردة\nمبلغ SAR 5,000.00\nمن محمد أحمد\nفي 10/04/26 09:00")
        self.assertEqual(r['type'], 'credit')
        self.assertEqual(r['amount'], 5000.0)

    def test_live_atm_withdrawal(self):
        r = self._live("سحب صراف آلي\nمبلغ 500 SAR\nفي 20/04/26 18:00")
        self.assertEqual(r['type'], 'debit')
        self.assertEqual(r['amount'], 500.0)
