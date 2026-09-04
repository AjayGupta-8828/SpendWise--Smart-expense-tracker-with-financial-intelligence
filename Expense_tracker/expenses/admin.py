from django.contrib import admin
from .models import Transactions, Budget

# Register your models here.
# admin.site.register(Transactions)
# admin.site.register(Budget)
@admin.register(Transactions)
class TransactionsAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'amount', 'types', 'category', 'date', 'created_at')
    list_filter = ('types', 'category', 'date')
    search_fields = ('title', 'amount','user__username')
@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'limit')
    list_filter = ('category',)
    search_fields = ('limit',)