from django.contrib.auth.models import User
from django.db import models


class FinancialHealthScore(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField()
    savings_score = models.PositiveSmallIntegerField()
    expense_score = models.PositiveSmallIntegerField()
    budget_score = models.PositiveSmallIntegerField()
    overspending_score = models.PositiveSmallIntegerField()
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-calculated_at"]
        indexes = [models.Index(fields=["user", "calculated_at"])]


class FinancialInsight(models.Model):
    INSIGHT_TYPES = [
        ("positive", "Positive"),
        ("warning", "Warning"),
        ("info", "Information"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    message = models.TextField()
    insight_type = models.CharField(max_length=10, choices=INSIGHT_TYPES, default="info")
    source = models.CharField(max_length=10, default="rule")
    data_signature = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]


class FinancialAiState(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    last_seen_signature = models.CharField(max_length=64, blank=True)
    updates_since_ai = models.PositiveSmallIntegerField(default=0)
    suggestions = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
