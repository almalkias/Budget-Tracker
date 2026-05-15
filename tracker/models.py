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
        ('reserve',     'سحب من الرصيد الاحتياطي'),
        ('visa',        'تسديد الفيزا'),
        ('other',       'أخرى'),
    ]
    TYPES = [('debit', 'خصم'), ('credit', 'إيداع')]

    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    type           = models.CharField(max_length=10, choices=TYPES)
    merchant       = models.CharField(max_length=200, blank=True)
    category       = models.CharField(max_length=50, choices=CATEGORIES, default='other')
    is_categorized = models.BooleanField(default=False)
    balance        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    date           = models.DateField(null=True, blank=True)
    raw_sms        = models.TextField()
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} ر.س — {self.merchant or self.get_category_display()}"


class MerchantRule(models.Model):
    merchant   = models.CharField(max_length=200, unique=True)
    category   = models.CharField(max_length=50, choices=Transaction.CATEGORIES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['merchant']

    def __str__(self):
        return f"{self.merchant} → {dict(Transaction.CATEGORIES).get(self.category, self.category)}"


class CategoryBudget(models.Model):
    category      = models.CharField(max_length=50, unique=True, choices=Transaction.CATEGORIES)
    monthly_limit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'حد الميزانية'
        verbose_name_plural = 'حدود الميزانية'

    def __str__(self):
        return f"{self.category}: {self.monthly_limit or 'بدون حد'}"


class BudgetCycle(models.Model):
    STATUS = [('active', 'Active'), ('closed', 'Closed')]

    month             = models.IntegerField()
    year              = models.IntegerField()
    starting_balance  = models.DecimalField(max_digits=12, decimal_places=2)
    remaining_balance = models.DecimalField(max_digits=12, decimal_places=2)
    total_spent       = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    started_at        = models.DateTimeField()
    closed_at         = models.DateTimeField(null=True, blank=True)
    status            = models.CharField(max_length=10, choices=STATUS, default='active')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.month}/{self.year} — {self.status}"
