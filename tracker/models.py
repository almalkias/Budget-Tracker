from django.db import models


class Transaction(models.Model):
    CATEGORIES = [
        ('food', 'مطاعم وتوصيل'),
        ('fuel', 'وقود'),
        ('pharmacy', 'صيدليات'),
        ('shopping', 'تسوق'),
        ('bills', 'فواتير وسداد'),
        ('family', 'تحويلات الأهل'),
        ('bnpl', 'تقسيط'),
        ('investment', 'استثمار'),
        ('salary', 'راتب وارد'),
        ('other', 'متنوع'),
    ]

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    TYPES = [('debit', 'خصم'), ('credit', 'إيداع')]

    type = models.CharField(max_length=10, choices=TYPES)
    merchant = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=50, choices=CATEGORIES, default='other')
    balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    raw_sms = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} ر.س — {self.merchant or self.get_category_display()}"
