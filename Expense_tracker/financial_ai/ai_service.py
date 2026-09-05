import hashlib
import json

from django.conf import settings

try:
    from groq import Groq
except ImportError:
    Groq = None


def _currency(amount):
    return "₹{:,.0f}".format(amount or 0)


def metrics_signature(metrics):
    """A signature lets us reuse a summary until meaningful values change."""
    data = {
        "score": metrics["score"], "income": str(metrics["income"]),
        "expenses": str(metrics["expenses"]), "savings": str(metrics["savings"]),
        "budget_usage": metrics["budget_usage"],
        "category_changes": [
            {"category": item["category"], "current": str(item["current"]), "change": item["change"]}
            for item in metrics["category_changes"]
        ],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _build_prompt(metrics):
    category_lines = []
    for item in metrics["category_changes"][:3]:
        if item["change"] is None:
            category_lines.append("{} spending: new this month ({})".format(item["category"], _currency(item["current"])))
        else:
            category_lines.append("{} spending change: {:+.0f}%".format(item["category"], item["change"]))

    budget_usage = "No budgets set" if metrics["budget_usage"] is None else "{:.0f}%".format(metrics["budget_usage"])
    return """Write one concise, helpful financial summary in plain text (maximum 90 words).
Use only the supplied aggregate numbers. Do not invent facts, give buy/sell advice,
or use HTML. This is educational information, not financial advice.

Financial Health Score: {score}/100 ({label})
Savings Ratio: {savings_ratio:.0f}%
Expense Ratio: {expense_ratio:.0f}%
Budget Usage: {budget_usage}
Monthly Savings: {savings}
Highest Spending Category: {top_category}
{category_changes}""".format(
        score=metrics["score"], label=metrics["label"], savings_ratio=metrics["savings_ratio"],
        expense_ratio=metrics["expense_ratio"], budget_usage=budget_usage,
        savings=_currency(metrics["savings"]),
        top_category=metrics["highest_category"]["category"] if metrics["highest_category"] else "No expense category",
        category_changes="\n".join(category_lines) or "No category comparison is available.",
    )


def get_ai_insight(metrics):
    """Return a plain-text Groq summary, or None so the page can use its fallback."""
    if not settings.GROQ_API_KEY or Groq is None:
        return None

    try:
        client = Groq(api_key=settings.GROQ_API_KEY, timeout=8.0)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a careful financial education assistant for SpendWise."},
                {"role": "user", "content": _build_prompt(metrics)},
            ],
            temperature=0.2,
            max_completion_tokens=180,
        )
        content = (response.choices[0].message.content or "").strip()
        return content[:900] or None
    except Exception:
        return None
