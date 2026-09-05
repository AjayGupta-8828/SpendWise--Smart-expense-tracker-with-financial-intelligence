from django.contrib import admin

from .models import FinancialHealthScore, FinancialInsight


@admin.register(FinancialHealthScore)
class FinancialHealthScoreAdmin(admin.ModelAdmin):
    list_display = ("user", "score", "calculated_at")
    list_filter = ("calculated_at",)
    search_fields = ("user__username",)


@admin.register(FinancialInsight)
class FinancialInsightAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "insight_type", "is_read", "created_at")
    list_filter = ("insight_type", "is_read")
    search_fields = ("user__username", "title")
