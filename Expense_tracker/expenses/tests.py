from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from allauth.socialaccount.models import SocialAccount

from .models import Budget, Transactions


class TransactionGuardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ajay", email="ajay@example.com", password="test-password")
        self.client.login(username="ajay", password="test-password")

    def post_transaction(self, **overrides):
        data = {
            "title": "Test transaction", "amount": "100", "types": "Expense",
            "category": "Food", "date": "2026-10-04",
        }
        data.update(overrides)
        return self.client.post(reverse("add_transaction"), data, follow=True)

    def test_expense_requires_income(self):
        response = self.post_transaction()
        self.assertEqual(Transactions.objects.count(), 0)
        self.assertContains(response, "Add income before recording an expense")

    def test_expense_cannot_exceed_available_income(self):
        self.post_transaction(types="Income", category="Salary", amount="500")
        response = self.post_transaction(amount="501")
        self.assertEqual(Transactions.objects.filter(types="Expense").count(), 0)
        self.assertContains(response, "would exceed your available income")

    def test_other_income_stores_custom_category(self):
        self.post_transaction(types="Income", category="Other", custom_category="Freelance", amount="500")
        income = Transactions.objects.get(types="Income")
        self.assertEqual(income.category, "Freelance")

    @patch("expenses.views.send_budget_alert_email")
    def test_crossing_budget_sends_one_alert_with_category_and_total(self, send_alert):
        self.post_transaction(types="Income", category="Salary", amount="1000")
        Budget.objects.create(user=self.user, category="Food", limit=Decimal("250"))
        self.post_transaction(amount="200")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_transaction(amount="100")

        self.assertContains(response, "Food budget has been exceeded")
        send_alert.assert_called_once_with(
            "ajay@example.com", "ajay", "Food", Decimal("300"), Decimal("250"),
        )


class ProfileChangeOtpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "profile-user", email="old@example.com", password="current-password"
        )
        self.client.login(username="profile-user", password="current-password")

    @patch("expenses.views.send_otp_email", return_value=True)
    def test_email_is_changed_only_after_otp_verification(self, send_otp):
        response = self.client.post(reverse("profile"), {
            "first_name": "Updated", "last_name": "User", "email": "new@example.com",
        })

        self.assertRedirects(response, reverse("verify_profile_otp"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")
        self.assertEqual(self.client.session["profile_change"]["email"], "new@example.com")
        send_otp.assert_called_once()

        response = self.client.post(reverse("verify_profile_otp"), {"otp": self.client.session["profile_change_otp"]})
        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.first_name, "Updated")

    @patch("expenses.views.send_otp_email", return_value=True)
    def test_password_is_changed_only_after_otp_verification(self, send_otp):
        response = self.client.post(reverse("change_password"), {
            "current_password": "current-password", "new_password": "new-password-123", "confirm_password": "new-password-123",
        })

        self.assertRedirects(response, reverse("verify_profile_otp"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("current-password"))
        self.assertFalse(self.user.check_password("new-password-123"))
        send_otp.assert_called_once_with("old@example.com", "profile-user", self.client.session["profile_change_otp"])

        response = self.client.post(reverse("verify_profile_otp"), {"otp": self.client.session["profile_change_otp"]})
        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-password-123"))


class SocialProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("social-user", password=None, first_name="Social")
        self.user.set_unusable_password()
        self.user.save()
        SocialAccount.objects.create(
            user=self.user, provider="google", uid="google-social-user",
            extra_data={"email": "social@example.com"},
        )
        self.client.force_login(self.user)

    def test_social_account_email_is_shown_and_password_form_is_hidden(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.context["profile_email"], "social@example.com")
        self.assertTrue(response.context["is_social_only"])
        self.assertFalse(response.context["can_change_password"])
        self.assertContains(response, "social@example.com")
        self.assertNotContains(response, "Change Password")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "social@example.com")

    def test_social_only_user_cannot_submit_a_password_change(self):
        response = self.client.post(reverse("change_password"), {
            "current_password": "anything", "new_password": "new-password-123", "confirm_password": "new-password-123",
        }, follow=True)

        self.assertContains(response, "Password changes are unavailable")
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
