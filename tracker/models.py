from django.db import models


class Transaction(models.Model):
    CATEGORIES = [
        ('supermarket', 'سوبر ماركت'),
        ('clothes',     'ملابس وخياط'),
        ('car',         'السيارة'),
        ('food',        'مطاعم وتوصيل'),
        ('pharmacy',    'صيدلية'),
        ('bnpl',        'تابي وتمارا'),
        ('cash',        'سحب كاش'),
        ('family',      'تحويل للعائلة'),
        ('reserve_in',  'تحويل الى الاحتياطي'),
        ('reserve_out', 'تحويل من الاحتياطي'),
        ('visa',        'تسديد الفيزا'),
        ('maids',       'شغالات'),
        ('school',      'طلبات مدرسة'),
        ('laundry',     'مغسلة ملابس'),
        ('maintenance', 'صيانة البيت'),
    ]
    TYPES = [('debit', 'خصم'), ('credit', 'إيداع')]

    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    type           = models.CharField(max_length=10, choices=TYPES)
    merchant       = models.CharField(max_length=200, blank=True)
    category       = models.CharField(max_length=50, choices=CATEGORIES, default='other')
    is_categorized = models.BooleanField(default=False)
    is_skipped     = models.BooleanField(default=False)
    cycle          = models.ForeignKey('BudgetCycle', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='transactions')
    balance        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    date           = models.DateField(null=True, blank=True)
    raw_sms        = models.TextField()
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} ر.س — {self.merchant or self.get_category_display()}"



class CategoryBudget(models.Model):
    category      = models.CharField(max_length=50, unique=True, choices=Transaction.CATEGORIES)
    monthly_limit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'حد الميزانية'
        verbose_name_plural = 'حدود الميزانية'

    def __str__(self):
        return f"{self.category}: {self.monthly_limit or 'بدون حد'}"


class MerchantMemory(models.Model):
    merchant   = models.CharField(max_length=200, unique=True)
    category   = models.CharField(max_length=50)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'ذاكرة التاجر'
        verbose_name_plural = 'ذاكرة التجار'

    def __str__(self):
        return f"{self.merchant} → {self.category}"


class ReserveBalance(models.Model):
    balance    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'رصيد الاحتياطي'
        verbose_name_plural = 'رصيد الاحتياطي'

    def __str__(self):
        return f"رصيد الاحتياطي: {self.balance}"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'balance': 0})
        return obj


class BudgetCycle(models.Model):
    STATUS = [('active', 'Active'), ('closed', 'Closed')]

    month       = models.IntegerField()
    year        = models.IntegerField()
    salary      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    started_at  = models.DateTimeField()
    closed_at   = models.DateTimeField(null=True, blank=True)
    status      = models.CharField(max_length=10, choices=STATUS, default='active')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.month}/{self.year} — {self.status}"


class AppSettings(models.Model):
    use_claude_parser = models.BooleanField(
        default=False,
        verbose_name='استخدام Claude API للتحليل',
        help_text='فعّل لاستخدام Claude API بدل الـ Regex Parser',
    )

    class Meta:
        verbose_name        = 'إعدادات التطبيق'
        verbose_name_plural = 'إعدادات التطبيق'

    def __str__(self):
        return 'Claude Parser: مفعّل' if self.use_claude_parser else 'Claude Parser: معطّل'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'use_claude_parser': False})
        return obj
