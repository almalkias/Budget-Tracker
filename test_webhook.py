#!/usr/bin/env python
"""
اختبار شامل للنظام — يرسل SMS لـ /api/sms/ ويتحقق من النتائج
الاستخدام: python test_webhook.py [base_url]
"""
import sys
import json
import urllib.request
import urllib.error
from decouple import config

BASE_URL = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
SECRET   = config('SMS_WEBHOOK_SECRET')

GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
RESET  = '\033[0m'
BOLD   = '\033[1m'

TEST_SMS_SAMPLES = [
    {
        'label':    'خصم — WHITE HEART (مطاعم)',
        'sms':      'تم الخصم 52.00 ر.س من حسابك رقم ****4986 بتاريخ 11/05/2026 في WHITE HEART الرصيد 5,127.91 ر.س',
        'expected_category': 'food',
        'expected_type':     'debit',
    },
    {
        'label':    'إيداع — راتب',
        'sms':      'تم إيداع 22,648.96 ر.س في حسابك رقم ****4986 بتاريخ 28/04/2026 الرصيد 22,690.59 ر.س',
        'expected_category': 'other',
        'expected_type':     'credit',
    },
    {
        'label':    'خصم — تحويل الأهل',
        'sms':      'تم الخصم 200.00 ر.س من حسابك رقم ****4986 بتاريخ 10/05/2026 تحويل الى الاهل والاصدقاء الرصيد 5,344.10 ر.س',
        'expected_category': 'family',
        'expected_type':     'debit',
    },
    {
        'label':    'خصم — ALNAHDI MEDICAL (صيدلية)',
        'sms':      'تم الخصم 111.26 ر.س من حسابك رقم ****4986 بتاريخ 10/05/2026 في ALNAHDI MEDICAL الرصيد 5,544.10 ر.س',
        'expected_category': 'pharmacy',
        'expected_type':     'debit',
    },
    {
        'label':    'خصم — Aldrees 1281 (وقود)',
        'sms':      'تم الخصم 75.12 ر.س من حسابك رقم ****4986 بتاريخ 08/05/2026 في Aldrees 1281 الرصيد 5,826.10 ر.س',
        'expected_category': 'fuel',
        'expected_type':     'debit',
    },
]


def post_json(url, data, headers=None):
    body = json.dumps(data).encode('utf-8')
    req  = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get_json(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def separator(char='─', width=55):
    print(char * width)


def run_tests():
    print()
    print(f'{BOLD}{"=" * 55}')
    print(f'  اختبار نظام مراقب الميزانية')
    print(f'  الخادم: {BASE_URL}')
    print(f'{"=" * 55}{RESET}')

    passed = failed = 0

    # ── 1. اختبارات الأمان ──────────────────────────────────
    print(f'\n{BOLD}[1] اختبارات الأمان{RESET}')
    separator()

    status, _ = post_json(f'{BASE_URL}/api/sms/', {'sms': 'test'})
    ok = status == 401
    print(f'{"✅" if ok else "❌"}  بدون X-Secret → HTTP {status} (يتوقع 401)')
    passed += ok; failed += not ok

    status, _ = post_json(f'{BASE_URL}/api/sms/', {'sms': 'test'},
                          headers={'X-Secret': 'wrong-secret'})
    ok = status == 401
    print(f'{"✅" if ok else "❌"}  Secret خاطئ   → HTTP {status} (يتوقع 401)')
    passed += ok; failed += not ok

    status, body = post_json(f'{BASE_URL}/api/sms/', {},
                             headers={'X-Secret': SECRET})
    ok = status == 400 and body.get('error') == 'no sms'
    print(f'{"✅" if ok else "❌"}  بدون sms      → HTTP {status} | {body}')
    passed += ok; failed += not ok

    status, body = post_json(f'{BASE_URL}/api/sms/',
                             {'sms': 'نص عشوائي لا يُعرف نمطه XYZ 999'},
                             headers={'X-Secret': SECRET})
    ok = status == 400
    print(f'{"✅" if ok else "❌"}  SMS غير معروف → HTTP {status} | {body}')
    passed += ok; failed += not ok

    # ── 2. اختبارات الـ SMS ──────────────────────────────────
    print(f'\n{BOLD}[2] إرسال رسائل SMS{RESET}')
    separator()

    for i, sample in enumerate(TEST_SMS_SAMPLES, 1):
        status, body = post_json(
            f'{BASE_URL}/api/sms/',
            {'sms': sample['sms']},
            headers={'X-Secret': SECRET},
        )
        saved    = status == 200 and body.get('status') == 'saved'
        cat_ok   = body.get('category') == sample['expected_category']
        all_ok   = saved and cat_ok

        icon = '✅' if all_ok else ('⚠️ ' if saved else '❌')
        cat_got  = body.get('category', '—')
        cat_exp  = sample['expected_category']
        cat_note = '' if cat_ok else f'{YELLOW}(يتوقع: {cat_exp}){RESET}'

        print(f'{icon}  SMS-{i}: {sample["label"]}')
        print(f'        HTTP {status} | category: {cat_got} {cat_note}')

        passed += all_ok; failed += not all_ok

    # ── 3. اختبار Dashboard API ──────────────────────────────
    print(f'\n{BOLD}[3] Dashboard API{RESET}')
    separator()

    status, data = get_json(f'{BASE_URL}/api/dashboard/?month=5&year=2026')
    ok = status == 200 and 'total_spent' in data
    print(f'{"✅" if ok else "❌"}  GET /api/dashboard/ → HTTP {status}')
    if ok:
        print(f'        الشهر        : {data["month"]}/{data["year"]}')
        print(f'        إجمالي مصروف : {data["total_spent"]} ر.س')
        print(f'        إجمالي دخل   : {data["total_income"]} ر.س')
        print(f'        الرصيد       : {data["balance_latest"]} ر.س')
        print(f'        الفئات       : {len(data["by_category"])} فئة')
        print(f'        آخر عمليات  : {len(data["recent"])} عملية')
        if data['by_category']:
            print(f'        تفصيل الفئات:')
            for row in data['by_category']:
                label = row['category']
                print(f'          • {label}: {row["total"]} ر.س ({row["count"]} عملية)')
    passed += ok; failed += not ok

    # ── النتيجة النهائية ─────────────────────────────────────
    total = passed + failed
    print()
    separator('═')
    if failed == 0:
        print(f'{GREEN}{BOLD}  النتيجة: {passed}/{total} — جميع الاختبارات نجحت ✅{RESET}')
    else:
        print(f'{RED}{BOLD}  النتيجة: {passed}/{total} — {failed} اختبار فشل ❌{RESET}')
    separator('═')
    print()

    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
