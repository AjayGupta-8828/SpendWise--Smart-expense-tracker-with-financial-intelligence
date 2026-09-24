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


def _metric_summary(metrics):
    category_lines = []
    for item in metrics["category_changes"][:3]:
        if item["change"] is None:
            category_lines.append("{} spending: new this month ({})".format(item["category"], _currency(item["current"])))
        else:
            category_lines.append("{} spending change: {:+.0f}%".format(item["category"], item["change"]))

    budget_usage = "No budgets set" if metrics["budget_usage"] is None else "{:.0f}%".format(metrics["budget_usage"])
    return """Financial Health Score: {score}/100 ({label})
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


def get_ai_financial_content(metrics):
    """Return validated educational AI content, or None for the deterministic fallback."""
    if not settings.GROQ_API_KEY or Groq is None:
        return None

    try:
        client = Groq(api_key=settings.GROQ_API_KEY, timeout=8.0)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a careful financial education assistant for SpendWise. Never give buy, sell, or hold instructions, name individual stocks, promise returns, "},
                {"role": "user", "content": """Use only these aggregate financial figures:\n{metrics}\n\nReturn valid JSON only in this exact shape:\n{{\"summary\": \"maximum 90 words of plain educational financial insight\", \"suggestions\": [{{\"title\": \"educational category\", \"message\": \"maximum 35 words explaining what to learn and why it relates to these figures\"}}]}}\n\nGive exactly 5 suggestions selected only from: Fixed Deposits, Government Securities, Liquid Funds, Gold ETFs, Nifty 50 Index Funds, Diversified Equity Mutual Funds, Individual Equity Shares. Do not mention a particular scheme, company, stock ticker, buy/sell action, price, return, or market prediction.""".format(metrics=_metric_summary(metrics))},
            ],
            temperature=0.2,
            max_completion_tokens=260,
            response_format={"type": "json_object"},
        )
        content = json.loads(response.choices[0].message.content or "{}")
        summary = str(content.get("summary", "")).strip()[:900]
        allowed = {"Fixed Deposits", "Government Securities", "Liquid Funds", "Gold ETFs", "Nifty 50 Index Funds", "Diversified Equity Mutual Funds", "Individual Equity Shares"}
        suggestions = []
        for item in content.get("suggestions", []):
            title = str(item.get("title", "")).strip()
            message = str(item.get("message", "")).strip()[:240]
            if title in allowed and message:
                suggestions.append({"title": title, "message": message})
        if summary and len(suggestions) == 5:
            return {"summary": summary, "suggestions": suggestions}
    except (Exception, ValueError, TypeError, json.JSONDecodeError):
        return None
