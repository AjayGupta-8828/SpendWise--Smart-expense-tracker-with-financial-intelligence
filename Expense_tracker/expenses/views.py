import random
import secrets
from decimal import Decimal, InvalidOperation
from urllib import request
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.shortcuts import render,redirect, get_object_or_404
from django.contrib.auth import authenticate, login,logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.hashers import make_password
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.contrib import messages
from django.urls import reverse
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from .models import Transactions,Budget
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from datetime import timedelta
from .emails import send_welcome_email, send_otp_email, send_budget_alert_email
from financial_ai.services import calculate_financial_health

EXPENSE_CATEGORIES = {"Food", "Groceries", "Travel", "Shopping", "Bills", "Entertainment", "Other"}
INCOME_CATEGORIES = {"Salary", "Other"}


def landing_page(request):
    """Render the public marketing page before a visitor signs in."""
    return render(request, "expenses/landing.html")


def _transaction_data(request, existing=None):
    """Validate form data and return values safe to save, or an error message."""
    title = request.POST.get("title", "").strip()
    types = request.POST.get("types")
    category = request.POST.get("category", "").strip()
    custom_category = request.POST.get("custom_category", "").strip()
    date_value = request.POST.get("date")
    date = parse_date(date_value) if date_value else None
    try:
        amount = Decimal(request.POST.get("amount", ""))
    except (InvalidOperation, TypeError):
        return None, "Enter a valid transaction amount."

    if not title or types not in {"Income", "Expense"} or amount <= 0:
        return None, "Please provide a title, a valid transaction type, and an amount greater than zero."
    if date_value and not date:
        return None, "Enter a valid transaction date."
    if types == "Income":
        if category not in INCOME_CATEGORIES:
            return None, "Income can only use Salary or Other as its category."
        if category == "Other":
            if not custom_category:
                return None, "Enter a custom category for Other income."
            if len(custom_category) > 100:
                return None, "Custom income categories must be 100 characters or fewer."
            category = custom_category
    elif category not in EXPENSE_CATEGORIES:
        return None, "Choose one of the available expense categories."

    return {
        "title": title, "amount": amount, "types": types,
        "category": category, "date": date or None,
    }, None


def _can_afford_transaction(user, values, existing=None):
    """Ensure the resulting lifetime expenses never exceed the user's income."""
    transactions = Transactions.objects.filter(user=user)
    if existing:
        transactions = transactions.exclude(pk=existing.pk)
    totals = transactions.values("types").annotate(total=Sum("amount"))
    amounts = {item["types"]: item["total"] for item in totals}
    income = amounts.get("Income", Decimal("0"))
    expense = amounts.get("Expense", Decimal("0"))
    if values["types"] == "Income":
        income += values["amount"]
    else:
        expense += values["amount"]
    if income == 0:
        return False, "Add income before recording an expense."
    if expense > income:
        return False, "This expense would exceed your available income. Add income or reduce the expense amount."
    return True, None


def _budget_crossing(user, values, existing=None):
    """Return the monthly budget and projected spend only when it newly crosses."""
    if values["types"] != "Expense":
        return None
    entry_date = values["date"] or (existing.date if existing else timezone.localdate())
    budget = Budget.objects.filter(user=user, category=values["category"]).first()
    if not budget:
        return None
    monthly_expenses = Transactions.objects.filter(
        user=user, types="Expense", category=values["category"],
        date__year=entry_date.year, date__month=entry_date.month,
    )
    if existing:
        monthly_expenses = monthly_expenses.exclude(pk=existing.pk)
    prior_spent = monthly_expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    projected_spent = prior_spent + values["amount"]
    if prior_spent <= budget.limit < projected_spent:
        return budget, projected_spent
    return None
@login_required(login_url="/login/")
def mainpage(request):

    today = timezone.localdate()
    # This flag is set once after OTP verification, then consumed here.
    is_new_user = request.session.pop("show_new_user_welcome", False)

    title = request.GET.get("search_text") 
    date = request.GET.get("search_date")
    types = request.GET.get("search_types")
    category = request.GET.get("search_category")
    amount = request.GET.get("search_amount")
    see_all = request.GET.get("see_all")
    month = request.GET.get("search_month")

    # Dashboard summary cards always reflect the current calendar month.  The
    # `search_month` value belongs to the recent-transactions table only; using
    # it here caused the cards to show a different month while still saying
    # "This month".
    selected_month = today.month
    try:
        transaction_month = int(month) if month else None
    except (TypeError, ValueError):
        transaction_month = None
    if transaction_month not in range(1, 13):
        transaction_month = None

    # Dashboard Cards
    expense = Transactions.objects.filter(
        user=request.user,
        types="Expense",
        date__year=today.year,
        date__month=selected_month
    ).aggregate(total_expense=Sum("amount"))

    income = Transactions.objects.filter(
        user=request.user,
        types="Income",
        date__year=today.year,
        date__month=selected_month
    ).aggregate(total_income=Sum("amount"))

    number_of_transactions = Transactions.objects.filter(
        user=request.user,
        date__year=today.year,
        date__month=selected_month
    ).count()

    Balance = (
        (income["total_income"] or 0)
        - (expense["total_expense"] or 0)
    )

    if Balance < 0:
        Balance = 0

    # Pie Chart
    expenseData = list(
        Transactions.objects.filter(
            user=request.user,
            types="Expense",
            date__year=today.year,
            date__month=selected_month
        )
        .values("category")
        .annotate(total=Sum("amount"))
    )

    # Transaction List
    queryset = Transactions.objects.filter(user=request.user).order_by("-created_at")

    if title:
        queryset = queryset.filter(title__icontains=title)

    if date:
        queryset = queryset.filter(date=date)

    if types:
        queryset = queryset.filter(types=types)

    if category:
        queryset = queryset.filter(category=category)

    if amount:
        queryset = queryset.filter(amount=amount)

    if transaction_month:
        queryset = queryset.filter(
            date__year=today.year,
            date__month=transaction_month,
        )
    elif not see_all:
        queryset = queryset.filter(
            date__year=today.year,
            date__month=selected_month
        )

    queryset = queryset[:10] if see_all else queryset[:5]

    # Budget Tracker
    budgets = Budget.objects.filter(user=request.user)

    budget_data = []

    for budget in budgets:

        spent = (
            Transactions.objects.filter(
                user=request.user,
                category=budget.category,
                types="Expense",
                date__year=today.year,
                date__month=selected_month
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )

        percentage = (spent / budget.limit) * 100 if budget.limit else 0

        budget_data.append({
            "id": budget.id,
            "category": budget.category,
            "limit": budget.limit,
            "spent": spent,
            "percentage": min(percentage, 100),
            "over_budget": spent > budget.limit,
            "remaining": max(budget.limit - spent, 0),
            "exceeded": max(spent - budget.limit, 0),
        })

    # ==========================
    # Income vs Expense Bar Chart
    # ==========================

    income_queryset = (
        Transactions.objects.filter(user=request.user, types="Income", date__year=today.year)
        .annotate(month=ExtractMonth("date")).values("month").annotate(total=Sum("amount")).order_by("month")
    )
    expense_queryset = (
        Transactions.objects.filter(user=request.user, types="Expense", date__year=today.year)
        .annotate(month=ExtractMonth("date")).values("month").annotate(total=Sum("amount")).order_by("month")
    )
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    income_data = [0] * 12
    expense_data = [0] * 12
    for item in income_queryset:
        income_data[item["month"] - 1] = float(item["total"])
    for item in expense_queryset:
        expense_data[item["month"] - 1] = float(item["total"])

    health_preview = calculate_financial_health(request.user)
    edit_budget = None
    if request.GET.get("edit_budget"):
        edit_budget = get_object_or_404(
            Budget, user=request.user, pk=request.GET["edit_budget"]
        )

    return render(
        request,
        "expenses/mainpage.html",
        {
            "expense": expense,
            "income": income,
            "Balance": Balance,
            "number_of_transactions": number_of_transactions,
            "queryset": queryset,
            "expenseData": expenseData,
            
            "budget_data": budget_data,

            # Bar Chart
            "months": months,
            "income_data": income_data,
            "expense_data": expense_data,
            "health_preview": health_preview,
            "is_new_user": is_new_user,
            "edit_budget": edit_budget,
        },
    )
@login_required(login_url="/login/")
def budget_tracker(request):
    if request.method=="POST":
        category=request.POST.get("category")
        limit=request.POST.get("limit")
        if category not in EXPENSE_CATEGORIES:
            messages.error(request, "Choose a valid expense category for the budget.")
        else:
            try:
                limit = Decimal(limit)
                if limit <= 0:
                    raise InvalidOperation
            except (InvalidOperation, TypeError):
                messages.error(request, "Enter a budget limit greater than zero.")
                return redirect("/dashboard/?modal=budget")
            Budget.objects.update_or_create(
                user=request.user,
                category=category,
                defaults={"limit":limit}
            )
        return redirect("/dashboard/")
    return redirect("/dashboard/?modal=budget")

@login_required(login_url="/login/")
def update_budget(request,id):
    budget = get_object_or_404(Budget, user=request.user, id=id)
    if request.method=="POST":
        
        limit=request.POST.get("limit")
        try:
            limit = Decimal(limit)
            if limit <= 0:
                raise InvalidOperation
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a budget limit greater than zero.")
            return redirect(f"/dashboard/?edit_budget={id}")
        budget.limit = limit
        budget.save()
        messages.info(request,"Budget updated successfully")
        return redirect("/dashboard/")
    return redirect(f"/dashboard/?edit_budget={id}")

@login_required(login_url="/login/")
def add_transaction(request):
    if request.method=="POST":
        values, error = _transaction_data(request)
        if error:
            messages.error(request, error)
            return redirect("/dashboard/?modal=transaction")
        allowed, error = _can_afford_transaction(request.user, values)
        if not allowed:
            messages.error(request, error)
            return redirect("/dashboard/?modal=transaction")
        budget_alert = _budget_crossing(request.user, values)
        Transactions.objects.create(user=request.user, **values)
        if budget_alert:
            budget, spent = budget_alert
            messages.warning(request, f"Your {budget.category} budget has been exceeded. Spent: ₹{spent:.2f}.")
            if request.user.email:
                db_transaction.on_commit(lambda: send_budget_alert_email(
                    request.user.email, request.user.first_name or request.user.username,
                    budget.category, spent, budget.limit,
                ))
        messages.success(request,"Transaction added successfully")
        return redirect("/dashboard/")

    return redirect("/dashboard/?modal=transaction")

# Create your views here.


@login_required(login_url="/login/")
def transaction(request):
    transactions = Transactions.objects.filter(
        user=request.user
    )
    edit_transaction = None
    if request.GET.get("edit_transaction"):
        edit_transaction = get_object_or_404(
            Transactions, user=request.user, pk=request.GET["edit_transaction"]
        )

    return render(
        request,
        'expenses/transactions.html',
        {'tasks': transactions, 'edit_transaction': edit_transaction}
    )

def delete_transaction(request,id):
    queryset = Transactions.objects.get(
        user=request.user,id=id
    )
    queryset.delete()
    return redirect("/transactions/")

@login_required(login_url="/login/")
def update_transaction(request,id):
    queryset = get_object_or_404(Transactions, user=request.user, id=id)
    if request.method == "POST":
        values, error = _transaction_data(request, queryset)
        if error:
            messages.error(request, error)
            return redirect(f"/transactions/?edit_transaction={id}")
        allowed, error = _can_afford_transaction(request.user, values, queryset)
        if not allowed:
            messages.error(request, error)
            return redirect(f"/transactions/?edit_transaction={id}")
        budget_alert = _budget_crossing(request.user, values, queryset)
        queryset.title = values["title"]
        queryset.amount = values["amount"]
        queryset.types = values["types"]
        queryset.category = values["category"]
        if values["date"]:
            queryset.date = values["date"]
        queryset.save()
        if budget_alert:
            budget, spent = budget_alert
            messages.warning(request, f"Your {budget.category} budget has been exceeded. Spent: ₹{spent:.2f}.")
            if request.user.email:
                db_transaction.on_commit(lambda: send_budget_alert_email(
                    request.user.email, request.user.first_name or request.user.username,
                    budget.category, spent, budget.limit,
                ))
        messages.success(request,"Transaction updated successfully")
        return redirect("/transactions/")
    return redirect(f"/transactions/?edit_transaction={id}")




def register_user(request):
    if request.method == "POST":
        data = request.POST
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if User.objects.filter(username=username).first():
            messages.info(request, "Username already exists")
            return redirect('/register/')

        # Create user but inactive until OTP verified
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password
        )
        user.is_active = False
        user.save()
        # Generate 6-digit OTP
        otp_code = str(random.randint(100000, 999999))
        # Store in session
        request.session['pending_user_id'] = user.id
        request.session['otp_code'] = otp_code
        request.session['otp_created_at'] = timezone.now().isoformat()

        if not send_otp_email(email, first_name, otp_code):
            user.delete()
            request.session.flush()
            messages.error(request, "We could not send the verification email. Please try again.")
            return redirect('/register/')
        return redirect('/verify-otp/')
    return render(request, "expenses/register.html")


def verify_otp(request):
    pending_user_id = request.session.get('pending_user_id')

    if not pending_user_id:
        messages.error(request, "No pending verification. Please register again.")
        return redirect('/register/')

    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        stored_otp = request.session.get('otp_code')
        created_at_str = request.session.get('otp_created_at')

        created_at = timezone.datetime.fromisoformat(created_at_str)
        if timezone.now() > created_at + timedelta(minutes=10):
            messages.error(request, "OTP expired. Please register again.")
            User.objects.filter(id=pending_user_id).delete()
            request.session.flush()
            return redirect('/register/')

        if entered_otp == stored_otp:
            user = User.objects.get(id=pending_user_id)
            user.is_active = True
            user.save()

            send_welcome_email(user.email, user.first_name)

            login(request, user, backend='django.contrib.auth.backends.ModelBackend') #Since there are two backends i.e 
            #MOdelBAckend and allauth backend ,#login() function gets confuse ,therefore we mentioned it explicilty

            del request.session['pending_user_id']
            del request.session['otp_code']
            del request.session['otp_created_at']

            request.session['show_new_user_welcome'] = True
            display_name = user.first_name or user.username
            messages.success(request, f"Welcome {display_name}! Your account is ready.")
            return redirect('/dashboard/')
        else:
            messages.error(request, "Invalid OTP. Try again.")
            return redirect('/verify-otp/')

    return render(request, "expenses/verify_otp.html")


def resend_otp(request):
    pending_user_id = request.session.get('pending_user_id')
    if not pending_user_id:
        return redirect('/register/')

    user = User.objects.get(id=pending_user_id)
    otp_code = str(random.randint(100000, 999999))

    request.session['otp_code'] = otp_code
    request.session['otp_created_at'] = timezone.now().isoformat()

    if send_otp_email(user.email, user.first_name, otp_code):
        messages.info(request, "A new OTP has been sent to your email.")
    else:
        messages.error(request, "We could not send a new OTP. Please try again.")
    return redirect('/verify-otp/')

def login_user(request):
    if request.method=="POST":
        data=request.POST
        username=data.get("username")
        password=data.get("password")

        if not User.objects.filter(username=username).exists():
            messages.error(request,"Invalid Username")
            return redirect('/login/')
        
        existing_user = User.objects.get(username=username)
        if not existing_user.is_active:
            messages.error(request, "Please verify your email first.")
            return redirect('/login/')

        user=authenticate(username=username,password=password)

        if user is None:
            messages.error(request,"Invalid Password")
            return redirect('/login/')
        else:
            login(request,user)
            display_name = user.first_name or user.username
            messages.success(request, f"Welcome back {display_name}!")
            return redirect(request.POST.get("next") or "/dashboard/")

    return render(request,"expenses/login.html")

def logout_user(request):
    logout(request)
    return redirect('/login/')

PROFILE_OTP_LIFETIME = timedelta(minutes=10)


def _begin_profile_change_otp(request, change):
    """Send and store an OTP for a pending sensitive profile change."""
    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    if not send_otp_email(change["email"], request.user.first_name or request.user.username, otp_code):
        return False
    request.session["profile_change"] = change
    request.session["profile_change_otp"] = otp_code
    request.session["profile_change_otp_created_at"] = timezone.now().isoformat()
    return True


def _clear_profile_change_otp(request):
    for key in ("profile_change", "profile_change_otp", "profile_change_otp_created_at"):
        request.session.pop(key, None)


def _social_profile_email(user):
    """Return the email supplied by allauth when User.email is blank."""
    if user.email:
        return user.email
    verified_email = (
        EmailAddress.objects.filter(user=user, verified=True)
        .order_by("-primary", "id").values_list("email", flat=True).first()
    )
    if verified_email:
        return verified_email
    for account in SocialAccount.objects.filter(user=user):
        email = (
            account.extra_data.get("email")
            or account.extra_data.get("emailAddress")
            or account.extra_data.get("email_address")
        )
        if email:
            return email
    return ""


def _is_social_only_user(user):
    return SocialAccount.objects.filter(user=user).exists() and not user.has_usable_password()


@login_required(login_url="/login/")
def profile_view(request):
    user = request.user
    profile_email = _social_profile_email(user)
    is_social_only = _is_social_only_user(user)
    # Keep the normal Django user field in sync with an email supplied by a
    # trusted allauth provider, so the profile works consistently afterwards.
    if profile_email and not user.email and not User.objects.filter(email__iexact=profile_email).exclude(id=user.id).exists():
        user.email = profile_email
        user.save(update_fields=["email"])
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
 
        if email and User.objects.filter(email=email).exclude(id=user.id).exists():
            messages.error(request, "That email is already in use by another account")
            return redirect("/profile/")

        if email and EmailAddress.objects.filter(email__iexact=email).exclude(user=user).exists():
            messages.error(request, "That email is already in use by another account")
            return redirect("/profile/")

        if is_social_only and email != profile_email:
            messages.error(request, "Your email is managed by your social login provider.")
            return redirect("/profile/")

        if email != profile_email:
            if not email:
                messages.error(request, "Enter an email address to verify this change.")
                return redirect("/profile/")
            change = {
                "user_id": user.id, "kind": "email", "email": email,
                "first_name": first_name, "last_name": last_name,
            }
            if not _begin_profile_change_otp(request, change):
                messages.error(request, "We could not send a verification code. Your profile was not changed.")
                return redirect("/profile/")
            messages.info(request, "Enter the verification code sent to your new email address.")
            return redirect("/profile/verify-otp/")

        user.first_name = first_name
        user.last_name = last_name
        user.save()
        messages.info(request, "Profile updated successfully")
        return redirect("/profile/")
 
    return render(request, "expenses/profile.html", {
        "profile_email": profile_email,
        "is_social_only": is_social_only,
        "can_change_password": not is_social_only and user.has_usable_password(),
    })
 
 
@login_required(login_url="/login/")
def change_password_view(request):
    if request.method == "POST":
        user = request.user
        if _is_social_only_user(user) or not user.has_usable_password():
            messages.error(request, "Password changes are unavailable for accounts signed in through a social provider.")
            return redirect("/profile/")
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")
 
        if not user.check_password(current_password):
            messages.error(request, "Current password is incorrect")
            return redirect("/profile/")
 
        if not new_password or new_password != confirm_password:
            messages.error(request, "New passwords do not match")
            return redirect("/profile/")
 
        if not user.email:
            messages.error(request, "Add and verify an email address before changing your password.")
            return redirect("/profile/")

        change = {
            "user_id": user.id, "kind": "password", "email": user.email,
            "password_hash": make_password(new_password),
        }
        if not _begin_profile_change_otp(request, change):
            messages.error(request, "We could not send a verification code. Your password was not changed.")
            return redirect("/profile/")
        messages.info(request, "Enter the verification code sent to your email address.")
        return redirect("/profile/verify-otp/")
 
    return redirect("/profile/")


@login_required(login_url="/login/")
def verify_profile_change_otp(request):
    change = request.session.get("profile_change")
    if not change or change.get("user_id") != request.user.id:
        messages.error(request, "There is no pending profile change to verify.")
        return redirect("/profile/")

    if request.method == "POST":
        created_at_str = request.session.get("profile_change_otp_created_at")
        try:
            created_at = timezone.datetime.fromisoformat(created_at_str)
        except (TypeError, ValueError):
            _clear_profile_change_otp(request)
            messages.error(request, "Verification session expired. Please try again.")
            return redirect("/profile/")
        if timezone.now() > created_at + PROFILE_OTP_LIFETIME:
            _clear_profile_change_otp(request)
            messages.error(request, "Verification code expired. Please submit the change again.")
            return redirect("/profile/")

        entered_otp = request.POST.get("otp", "")
        stored_otp = request.session.get("profile_change_otp", "")
        if not secrets.compare_digest(entered_otp, stored_otp):
            messages.error(request, "Invalid verification code. Try again.")
            return redirect("/profile/verify-otp/")

        user = request.user
        if change["kind"] == "email":
            if User.objects.filter(email=change["email"]).exclude(id=user.id).exists():
                _clear_profile_change_otp(request)
                messages.error(request, "That email is already in use by another account.")
                return redirect("/profile/")
            user.first_name = change["first_name"]
            user.last_name = change["last_name"]
            user.email = change["email"]
            success_message = "Email address updated successfully."
        elif change["kind"] == "password":
            user.password = change["password_hash"]
            success_message = "Password updated successfully."
        else:
            _clear_profile_change_otp(request)
            messages.error(request, "Invalid profile change request.")
            return redirect("/profile/")

        user.save()
        if change["kind"] == "password":
            update_session_auth_hash(request, user)
        _clear_profile_change_otp(request)
        messages.success(request, success_message)
        return redirect("/profile/")

    return render(request, "expenses/verify_otp.html", {
        "otp_heading": "Confirm account change",
        "otp_message": "Enter the 6-digit verification code we sent to your email before this change is applied.",
        "otp_resend_url": reverse("resend_profile_otp"),
        "otp_back_url": reverse("profile"),
        "otp_back_label": "Back to profile",
    })


@login_required(login_url="/login/")
def resend_profile_change_otp(request):
    change = request.session.get("profile_change")
    if request.method != "POST" or not change or change.get("user_id") != request.user.id:
        return redirect("/profile/")
    if _begin_profile_change_otp(request, change):
        messages.info(request, "A new verification code has been sent.")
    else:
        messages.error(request, "We could not send a new verification code. Please try again.")
    return redirect("/profile/verify-otp/")

from io import BytesIO
from datetime import timedelta
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

@login_required(login_url="/login/")
def export_transactions_csv(request):
    transactions = Transactions.objects.filter(user=request.user)

    preset = request.GET.get('preset', 'current_month')
    today = timezone.now().date()
    label = "export"

    if preset == 'today':
        transactions = transactions.filter(date=today)
        label = str(today)

    elif preset == 'yesterday':
        yesterday = today - timedelta(days=1)
        transactions = transactions.filter(date=yesterday)
        label = str(yesterday)

    elif preset == 'current_month':
        transactions = transactions.filter(date__year=today.year, date__month=today.month)
        label = today.strftime('%Y-%m')

    elif preset == 'last_month':
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        transactions = transactions.filter(date__year=last_month_end.year, date__month=last_month_end.month)
        label = last_month_end.strftime('%Y-%m')

    elif preset == 'custom':
        custom_type = request.GET.get('custom_type')

        if custom_type == 'month':
            month_value = request.GET.get('month')  # "YYYY-MM" from <input type="month">
            if month_value:
                year, month = map(int, month_value.split('-'))
                transactions = transactions.filter(date__year=year, date__month=month)
                label = month_value

        elif custom_type == 'date':
            date_value = request.GET.get('date')
            if date_value:
                transactions = transactions.filter(date=date_value)
                label = date_value

        elif custom_type == 'range':
            start_date = request.GET.get('start')
            end_date = request.GET.get('end')
            if start_date:
                transactions = transactions.filter(date__gte=start_date)
            if end_date:
                transactions = transactions.filter(date__lte=end_date)
            label = f"{start_date or 'start'}_to_{end_date or 'end'}"

    transactions = transactions.order_by('date')

    filename = f"spendwise_{request.user.username}_{label}.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Transactions"
    worksheet.freeze_panes = "A2"
    worksheet.sheet_view.showGridLines = False

    header_fill = PatternFill("solid", fgColor="2563EB")
    header_font = Font(color="FFFFFF", bold=True)
    alternate_fill = PatternFill("solid", fgColor="F8FAFC")
    border = Border(bottom=Side(style="thin", color="E2E8F0"))

    worksheet.append(['Date', 'Title', 'Type', 'Category', 'Amount', 'Created At'])
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_number, txn in enumerate(transactions, start=2):
        worksheet.append([
            txn.date,
            txn.title,
            txn.types,
            txn.category,
            txn.amount,
            timezone.localtime(txn.created_at).replace(tzinfo=None),
        ])
        for cell in worksheet[row_number]:
            cell.border = border
            cell.alignment = Alignment(vertical="center")
            if row_number % 2 == 0:
                cell.fill = alternate_fill
        worksheet.cell(row=row_number, column=1).number_format = "yyyy-mm-dd"
        worksheet.cell(row=row_number, column=5).number_format = '₹#,##0.00'
        worksheet.cell(row=row_number, column=6).number_format = "yyyy-mm-dd hh:mm"

    for column, width in {"A": 14, "B": 28, "C": 14, "D": 18, "E": 16, "F": 22}.items():
        worksheet.column_dimensions[column].width = width

    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.row_dimensions[1].height = 23

    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
