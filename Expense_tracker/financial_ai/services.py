from datetime import date
from decimal import Decimal

from django.db.models import Sum

from expenses.models import Budget, Transactions


def _amount(value):
    return value or Decimal("0")


def _score_savings(ratio):
    if ratio >= 30: return 30
    if ratio >= 20: return 25
    if ratio >= 10: return 18
    if ratio >= 5: return 10
    if ratio >= 0: return 5
    return 0


def _score_expenses(ratio):
    if ratio <= 50: return 25
    if ratio <= 60: return 22
    if ratio <= 70: return 18
    if ratio <= 80: return 12
    if ratio <= 90: return 6
    return 0


def _score_budget(usage):
    if usage <= 80: return 25
    if usage <= 90: return 22
    if usage <= 100: return 18
    if usage <= 110: return 10
    return 0


def _score_overspending(percent):
    if percent == 0: return 20
    if percent <= 10: return 17
    if percent <= 25: return 14
    if percent <= 40: return 9
    if percent <= 60: return 5
    return 0


def score_label(score):
    if score >= 90: return "Excellent"
    if score >= 80: return "Very Good"
    if score >= 70: return "Good"
    if score >= 60: return "Fair"
    return "Needs Improvement"


def monthly_metrics(user, today=None):
    today = today or date.today()
    current = Transactions.objects.filter(user=user, date__year=today.year, date__month=today.month)
    income = _amount(current.filter(types="Income").aggregate(total=Sum("amount"))["total"])
    expenses = _amount(current.filter(types="Expense").aggregate(total=Sum("amount"))["total"])
    savings = income - expenses
    category_data = list(current.filter(types="Expense").values("category").annotate(total=Sum("amount")).order_by("-total"))
    highest_category = category_data[0] if category_data else None
    expensive_day = current.filter(types="Expense").values("date").annotate(total=Sum("amount")).order_by("-total").first()

    first = today.replace(day=1)
    previous_end = first.fromordinal(first.toordinal() - 1)
    previous = Transactions.objects.filter(user=user, date__year=previous_end.year, date__month=previous_end.month)
    previous_expenses = _amount(previous.filter(types="Expense").aggregate(total=Sum("amount"))["total"])
    previous_income = _amount(previous.filter(types="Income").aggregate(total=Sum("amount"))["total"])
    previous_categories = {
        item["category"]: _amount(item["total"])
        for item in previous.filter(types="Expense").values("category").annotate(total=Sum("amount"))
    }
    category_changes = []
    for item in category_data:
        old_total = previous_categories.get(item["category"], Decimal("0"))
        change = float((item["total"] - old_total) / old_total * 100) if old_total else None
        category_changes.append({"category": item["category"], "current": item["total"], "change": change})

    return {
        "income": income, "expenses": expenses, "savings": savings,
        "savings_ratio": float(savings / income * 100) if income else 0,
        "expense_ratio": float(expenses / income * 100) if income else 0,
        "highest_category": highest_category, "expensive_day": expensive_day,
        "previous_income": previous_income, "previous_expenses": previous_expenses,
        "category_changes": category_changes,
        "transaction_count": current.count(), "has_data": current.exists(),
        "month_name": today.strftime("%B %Y"),
    }


def calculate_financial_health(user, today=None):
    metrics = monthly_metrics(user, today)
    budgets = list(Budget.objects.filter(user=user))
    budget_limit = sum((budget.limit for budget in budgets), Decimal("0"))
    budget_expenses = sum((_amount(Transactions.objects.filter(user=user, types="Expense", category=budget.category,
        date__year=(today or date.today()).year, date__month=(today or date.today()).month).aggregate(total=Sum("amount"))["total"]) for budget in budgets), Decimal("0"))
    budget_usage = float(budget_expenses / budget_limit * 100) if budget_limit else None
    over_budget = sum(1 for budget in budgets if _amount(Transactions.objects.filter(user=user, types="Expense", category=budget.category,
        date__year=(today or date.today()).year, date__month=(today or date.today()).month).aggregate(total=Sum("amount"))["total"]) > budget.limit)
    overspending_percent = (over_budget / len(budgets) * 100) if budgets else None

    if not metrics["has_data"] or not metrics["income"]:
        scores = {"savings_score": 0, "expense_score": 0, "budget_score": 0, "overspending_score": 0}
    else:
        scores = {
            "savings_score": _score_savings(metrics["savings_ratio"]),
            "expense_score": _score_expenses(metrics["expense_ratio"]),
            "budget_score": _score_budget(budget_usage) if budget_usage is not None else 0,
            "overspending_score": _score_overspending(overspending_percent) if overspending_percent is not None else 0,
        }
    score = sum(scores.values())
    metrics.update(scores)
    metrics.update({"score": score, "label": score_label(score), "budget_usage": budget_usage,
        "overspending_percent": overspending_percent, "budget_count": len(budgets), "over_budget_count": over_budget,
        "budget_limit": budget_limit, "budget_expenses": budget_expenses})
    return metrics


def investment_readiness(metrics):
    requirements = [
        ("Financial health score is 70 or more", metrics["score"] >= 70),
        ("You have a positive monthly saving", metrics["savings"] > 0),
        ("Expenses are 70% or less of income", metrics["expense_ratio"] <= 70 and metrics["income"] > 0),
        ("No more than 25% of budgets are exceeded", metrics["overspending_percent"] is not None and metrics["overspending_percent"] <= 25),
    ]
    achieved = sum(1 for _, met in requirements if met)
    readiness = int(achieved / len(requirements) * 100)
    if metrics["score"] < 60: state = "Focus on Financial Health"
    elif metrics["score"] < 70 or achieved < len(requirements): state = "Almost Ready"
    else: state = "Ready to Explore"
    return {"score": readiness, "state": state, "unlocked": achieved == len(requirements), "requirements": requirements}


def rule_based_insights(metrics):
    insights = []
    if not metrics["has_data"]:
        return [("Start tracking", "Add income and expense transactions to receive a financial health score.", "info")]
    if not metrics["income"]:
        insights.append(("Add your income", "Record income for this month to calculate savings and expense ratios accurately.", "warning"))
    elif metrics["savings"] > 0:
        insights.append(("Positive monthly savings", "You have saved ₹{:,.0f} this month.".format(metrics["savings"]), "positive"))
    else:
        insights.append(("Expenses exceed income", "Your expenses are higher than your recorded income this month.", "warning"))
    if metrics["highest_category"]:
        insights.append(("Largest expense category", "{} is your highest spending category at ₹{:,.0f}.".format(metrics["highest_category"]["category"], metrics["highest_category"]["total"]), "info"))
    if metrics["over_budget_count"]:
        insights.append(("Budget limit exceeded", "{} budget category{} exceeded its limit this month.".format(metrics["over_budget_count"], " has" if metrics["over_budget_count"] == 1 else "ies have"), "warning"))
    return insights[:4]


def investment_suggestions(metrics):
    if metrics["score"] >= 85:
        return [
            ("Nifty 50 Index Funds", "Learn how passive funds track a market index and how tracking error and costs affect outcomes."),
            ("Diversified Equity Mutual Funds", "Explore diversification, risk levels, and time horizon before considering equity-based products."),
            ("Gold ETFs", "Learn how exchange-traded funds work and how gold exposure can behave differently from equities."),
            ("Government Securities", "Research interest-rate risk, maturity, and how government-issued securities work."),
            ("Individual Equity Shares", "Study financial statements, diversification, and volatility before researching individual companies."),
        ]
    return [
        ("Fixed Deposits", "Learn about tenure, liquidity, interest-rate terms, and deposit insurance limits."),
        ("Government Securities", "Research government securities, maturity, and interest-rate risk before making decisions."),
        ("Liquid Funds", "Learn about liquidity, credit risk, and why a fund is not the same as a savings account."),
        ("Gold ETFs", "Explore ETF mechanics, costs, and how commodity exposure can fluctuate."),
        ("Nifty 50 Index Funds", "Study passive investing, diversification, expense ratios, and tracking error."),
    ]
