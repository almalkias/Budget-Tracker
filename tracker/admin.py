from django.contrib import admin
from .models import Transaction, MerchantRule, CategoryBudget, BudgetCycle


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display    = ('date', 'merchant', 'category', 'type', 'amount', 'is_categorized', 'balance', 'created_at')
    list_filter     = ('type', 'category', 'is_categorized')
    search_fields   = ('merchant', 'raw_sms')
    ordering        = ('-created_at',)
    readonly_fields = ('raw_sms', 'created_at')


@admin.register(MerchantRule)
class MerchantRuleAdmin(admin.ModelAdmin):
    list_display  = ('merchant', 'category', 'updated_at')
    list_filter   = ('category',)
    search_fields = ('merchant',)
    ordering      = ('merchant',)


@admin.register(CategoryBudget)
class CategoryBudgetAdmin(admin.ModelAdmin):
    list_display = ('category', 'monthly_limit', 'updated_at')
    ordering     = ('category',)


@admin.register(BudgetCycle)
class BudgetCycleAdmin(admin.ModelAdmin):
    list_display    = ('month', 'year', 'status', 'starting_balance', 'remaining_balance', 'total_spent', 'started_at', 'closed_at')
    list_filter     = ('status',)
    ordering        = ('-started_at',)
    readonly_fields = ('started_at', 'closed_at', 'remaining_balance', 'total_spent')
