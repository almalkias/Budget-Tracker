from django.contrib import admin
from .models import Transaction, CategoryBudget, BudgetCycle


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display    = ('date', 'merchant', 'category', 'type', 'amount', 'is_categorized', 'is_skipped', 'balance', 'created_at')
    list_filter     = ('type', 'category', 'is_categorized', 'is_skipped')
    search_fields   = ('merchant', 'raw_sms')
    ordering        = ('-created_at',)
    readonly_fields = ('raw_sms', 'created_at')


@admin.register(CategoryBudget)
class CategoryBudgetAdmin(admin.ModelAdmin):
    list_display = ('category', 'monthly_limit', 'updated_at')
    ordering     = ('category',)


@admin.register(BudgetCycle)
class BudgetCycleAdmin(admin.ModelAdmin):
    list_display    = ('month', 'year', 'status', 'salary', 'total_spent', 'started_at', 'closed_at')
    list_filter     = ('status',)
    ordering        = ('-started_at',)
    readonly_fields = ('started_at', 'closed_at', 'total_spent')
