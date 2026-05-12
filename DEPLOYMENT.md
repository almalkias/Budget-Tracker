# دليل النشر على PythonAnywhere

## نظرة عامة على الخطوات
1. إنشاء حساب PythonAnywhere
2. رفع الكود
3. إعداد Virtual Environment
4. إعداد ملف .env
5. تشغيل Migrations
6. إعداد Web App (WSGI)
7. إعداد Static Files
8. الحصول على GEMINI_API_KEY
9. إعداد SMS Forwarder على iPhone
10. اختبار النظام كاملاً

---

## الخطوة 1 — إنشاء حساب PythonAnywhere

1. افتح [pythonanywhere.com](https://www.pythonanywhere.com)
2. اضغط **Pricing & signup** ← **Create a Beginner account** (مجاني)
3. اختر **username** — سيصبح رابطك: `https://username.pythonanywhere.com`
4. أكمل التسجيل وتحقق من البريد الإلكتروني
5. سجّل الدخول

> **ملاحظة:** الحساب المجاني يكفي تماماً لهذا المشروع (شخص واحد، SQLite).

---

## الخطوة 2 — رفع الكود

من **Dashboard** → افتح **Bash console**

```bash
# استنسخ المشروع من GitHub
git clone https://github.com/almalkias/Budget-Tracker.git budget_tracker
cd budget_tracker

# تحقق من وجود الملفات
ls
```

---

## الخطوة 3 — إعداد Virtual Environment

```bash
# أنشئ البيئة الافتراضية
python3.11 -m venv venv

# فعّلها
source venv/bin/activate

# ثبّت المتطلبات
pip install -r requirements.txt
```

> إذا ظهر خطأ في psycopg2-binary يمكن تجاهله — SQLite لا تحتاجه.

---

## الخطوة 4 — إعداد ملف .env

```bash
# انسخ النموذج
cp .env.example .env

# افتح المحرر
nano .env
```

املأ القيم:

```env
SECRET_KEY=اكتب-مفتاح-عشوائي-طويل-هنا
GEMINI_API_KEY=ضع-مفتاح-جيميناي-هنا
SMS_WEBHOOK_SECRET=اختر-كلمة-سر-قوية-للـ-webhook
DEBUG=False
ALLOWED_HOSTS=username.pythonanywhere.com
DATABASE_URL=sqlite:///db.sqlite3
```

**لتوليد SECRET_KEY:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

احفظ الملف: `Ctrl+O` ثم `Enter` ثم `Ctrl+X`

---

## الخطوة 5 — تشغيل Migrations

```bash
# تأكد أنك في مجلد المشروع والبيئة مفعّلة
python manage.py migrate

# تحقق من النتيجة — يجب أن تظهر: OK لكل migration
```

---

## الخطوة 6 — إعداد Web App (WSGI)

### أ) إنشاء Web App

1. من **Dashboard** → اضغط **Web**
2. اضغط **Add a new web app** → Next
3. اختر **Manual configuration** (ليس Django)
4. اختر **Python 3.11** → Next

### ب) إعداد Virtualenv

في صفحة Web، نزّل لقسم **Virtualenv**:
```
/home/username/budget_tracker/venv
```

### ج) تعديل WSGI file

في قسم **Code**، اضغط على رابط **WSGI configuration file**، امسح كل المحتوى والصق هذا:

```python
import sys
import os

# مسار المشروع
path = '/home/username/budget_tracker'
if path not in sys.path:
    sys.path.insert(0, path)

# تفعيل البيئة الافتراضية
activate_this = '/home/username/budget_tracker/venv/bin/activate_this.py'
with open(activate_this) as f:
    exec(f.read(), {'__file__': activate_this})

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

> **مهم:** استبدل `username` باسم حسابك في كل مكان.

احفظ الملف.

### د) إعداد مسار الكود

في قسم **Code**:
- **Source code:** `/home/username/budget_tracker`
- **Working directory:** `/home/username/budget_tracker`

---

## الخطوة 7 — إعداد Static Files

في صفحة Web، نزّل لقسم **Static files**:

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/username/budget_tracker/staticfiles` |

ثم في Bash console:
```bash
python manage.py collectstatic --noinput
```

---

## الخطوة 8 — تشغيل الموقع

1. في صفحة Web اضغط **Reload** (الزر الأخضر الكبير)
2. افتح رابطك: `https://username.pythonanywhere.com`
3. يجب أن يظهر الداشبورد فارغاً (لا توجد عمليات بعد)

---

## الخطوة 9 — الحصول على GEMINI_API_KEY

1. افتح [aistudio.google.com](https://aistudio.google.com)
2. سجّل الدخول بحساب Google
3. اضغط **Get API key** → **Create API key**
4. انسخ المفتاح
5. افتح `.env` على PythonAnywhere وضعه في `GEMINI_API_KEY`
6. أعد تشغيل الموقع (Reload)

> المفتاح مجاني تماماً — يُستخدم فقط للعمليات غير المعروفة (fallback).

---

## الخطوة 10 — إعداد SMS Forwarder على iPhone

### تحميل التطبيق
- ابحث في App Store عن **"SMS Forwarder"** أو **"Auto Forward SMS"**
- أي تطبيق يدعم Webhook يكفي

### إعداد القاعدة (Rule)

| الحقل | القيمة |
|-------|--------|
| **Filter / Sender** | يحتوي على: `SNB` أو `الأهلي` |
| **Destination** | Webhook |
| **URL** | `https://username.pythonanywhere.com/api/sms/` |
| **Method** | POST |
| **Header Key** | `X-Secret` |
| **Header Value** | نفس قيمة `SMS_WEBHOOK_SECRET` في .env |
| **Body** | `{"sms": "{{message}}"}` |
| **Content-Type** | `application/json` |

### اختبار الإعداد
1. اضغط **Test** في التطبيق
2. يجب أن تصل رسالة `{"status": "saved", "category": "..."}` أو خطأ واضح
3. افتح الداشبورد وتحقق من ظهور العملية

---

## الخطوة 11 — اختبار النظام كاملاً

من Bash console على PythonAnywhere:

```bash
cd ~/budget_tracker
source venv/bin/activate
python test_webhook.py https://username.pythonanywhere.com
```

النتيجة المتوقعة:
```
النتيجة: 10/10 — جميع الاختبارات نجحت ✅
```

---

## استكشاف الأخطاء

### الموقع لا يفتح
```bash
# تحقق من سجل الأخطاء
# في صفحة Web → Error log
cat /var/log/username.pythonanywhere.com.error.log | tail -50
```

### خطأ 500
```bash
# تحقق من الـ .env
cat .env

# تحقق من الـ migrations
python manage.py migrate --check
```

### الـ Webhook لا يستقبل
- تحقق من أن URL صحيح تماماً (https وليس http)
- تحقق من أن `X-Secret` يطابق `.env` حرفاً بحرف
- تحقق من Error log في صفحة Web

### تحديث الكود بعد تعديلات
```bash
cd ~/budget_tracker
git pull origin main
source venv/bin/activate
pip install -r requirements.txt  # إذا تغيرت المتطلبات
python manage.py migrate          # إذا تغيرت النماذج
python manage.py collectstatic --noinput
# ثم اضغط Reload في صفحة Web
```

---

## ملاحظات مهمة

- **لا ترفع `.env` على GitHub أبداً** — يحتوي على مفاتيح سرية
- **SMS_WEBHOOK_SECRET** يجب أن يكون قوياً (16+ حرف)
- الحساب المجاني على PythonAnywhere ينام بعد عدم استخدام — أول طلب قد يتأخر قليلاً
- قاعدة البيانات SQLite محفوظة في `/home/username/budget_tracker/db.sqlite3`
