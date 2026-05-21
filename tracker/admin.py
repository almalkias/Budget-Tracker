from django.contrib import admin
from .models import Transaction, CategoryBudget, BudgetCycle, MerchantMemory, ReserveBalance, AppSettings, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ('key', 'label', 'order')
    search_fields = ('key', 'label')
    ordering      = ('order', 'key')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display    = ('date', 'merchant', 'category', 'type', 'amount', 'is_categorized', 'is_skipped', 'cycle', 'created_at')
    list_filter     = ('type', 'category', 'is_categorized', 'is_skipped', 'cycle')
    search_fields   = ('merchant', 'raw_sms')
    ordering        = ('-created_at',)
    readonly_fields = ('raw_sms', 'created_at')


@admin.register(CategoryBudget)
class CategoryBudgetAdmin(admin.ModelAdmin):
    list_display = ('category', 'monthly_limit', 'updated_at')
    ordering     = ('category',)


@admin.register(MerchantMemory)
class MerchantMemoryAdmin(admin.ModelAdmin):
    list_display  = ('merchant', 'category', 'updated_at')
    search_fields = ('merchant',)
    ordering      = ('merchant',)


@admin.register(BudgetCycle)
class BudgetCycleAdmin(admin.ModelAdmin):
    list_display    = ('month', 'year', 'status', 'salary', 'total_spent', 'started_at', 'closed_at')
    list_filter     = ('status',)
    ordering        = ('-started_at',)
    readonly_fields = ('started_at', 'closed_at', 'total_spent')


@admin.register(ReserveBalance)
class ReserveBalanceAdmin(admin.ModelAdmin):
    list_display = ('balance', 'updated_at')


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'use_claude_parser', 'claude_input_tokens', 'claude_output_tokens')
    readonly_fields = ('claude_input_tokens', 'claude_output_tokens')

    def has_add_permission(self, request):
        return not AppSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
