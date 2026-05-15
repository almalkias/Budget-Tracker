from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'merchant', 'category', 'type', 'amount', 'balance', 'created_at')
    list_filter = ('type', 'category')
    search_fields = ('merchant', 'raw_sms')
    ordering = ('-created_at',)
    readonly_fields = ('raw_sms', 'created_at')
