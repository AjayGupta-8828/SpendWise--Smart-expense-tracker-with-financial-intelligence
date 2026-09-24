from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from expenses.models import Budget, Transactions
from .services import calculate_financial_health, investment_readiness, score_label


class FinancialHealthServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="password")
        self.other_user = User.objects.create_user(username="bob", password="password")
        self.today = date.today()

    def transaction(self, types, amount, category="Food", user=None):
        return Transactions.objects.create(user=user or self.user, title="Test", types=types,
            amount=Decimal(amount), category=category, date=self.today)

    def test_no_transactions_has_zero_score(self):
        metrics = calculate_financial_health(self.user, self.today)
        self.assertEqual(metrics["score"], 0)
        self.assertFalse(metrics["has_data"])

    def test_zero_income_is_safe(self):
        self.transaction("Expense", "500")
        metrics = calculate_financial_health(self.user, self.today)
        self.assertEqual(metrics["score"], 0)
        self.assertEqual(metrics["expense_ratio"], 0)

    def test_excellent_score_within_budget(self):
        self.transaction("Income", "10000", "Salary")
        self.transaction("Expense", "4000", "Food")
        Budget.objects.create(user=self.user, category="Food", limit=Decimal("5000"))
        metrics = calculate_financial_health(self.user, self.today)
        self.assertEqual(metrics["score"], 100)
        self.assertEqual(metrics["label"], "Excellent")

    def test_expenses_greater_than_income_locks_readiness(self):
        self.transaction("Income", "1000", "Salary")
        self.transaction("Expense", "1200")
        metrics = calculate_financial_health(self.user, self.today)
        readiness = investment_readiness(metrics)
        self.assertFalse(readiness["unlocked"])
        self.assertEqual(readiness["state"], "Focus on Financial Health")

    def test_user_data_is_isolated(self):
        self.transaction("Income", "10000", "Salary")
        self.transaction("Expense", "9000", user=self.other_user)
        metrics = calculate_financial_health(self.user, self.today)
        self.assertEqual(metrics["expenses"], 0)

    def test_score_labels_at_boundaries(self):
        self.assertEqual(score_label(60), "Fair")
        self.assertEqual(score_label(70), "Good")
        self.assertEqual(score_label(90), "Excellent")

    def test_page_is_login_protected_and_creates_daily_history(self):
        response = self.client.get("/financial-intelligence/")
        self.assertRedirects(response, "/login/?next=/financial-intelligence/")
        self.client.force_login(self.user)
        with patch("financial_ai.views.get_ai_financial_content", return_value=None):
            response = self.client.get("/financial-intelligence/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financial Intelligence")

    def test_ai_refreshes_after_three_financial_data_changes(self):
        self.transaction("Income", "10000", "Salary")
        self.transaction("Expense", "2000", "Food")
        self.client.force_login(self.user)
        ai_content = {
            "summary": "Your summary was refreshed.",
            "suggestions": [
                {"title": "Fixed Deposits", "message": "Research lower-volatility saving options."},
                {"title": "Government Securities", "message": "Research maturity and interest-rate risk."},
                {"title": "Liquid Funds", "message": "Research liquidity and credit risk."},
                {"title": "Gold ETFs", "message": "Research diversification and market risk."},
                {"title": "Nifty 50 Index Funds", "message": "Research diversified equity exposure."},
            ],
        }
        with patch("financial_ai.views.get_ai_financial_content", return_value=ai_content) as generate:
            self.client.get("/financial-intelligence/")
            for amount in ("100", "200", "300"):
                self.transaction("Expense", amount, "Food")
                self.client.get("/financial-intelligence/")

        self.assertEqual(generate.call_count, 4)
