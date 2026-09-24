from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .models import FinancialAiState, FinancialHealthScore, FinancialInsight
from .ai_service import get_ai_financial_content, metrics_signature
from .services import calculate_financial_health, investment_readiness, investment_suggestions, rule_based_insights


@login_required(login_url="/login/")
def financial_intelligence(request):
    metrics = calculate_financial_health(request.user)
    readiness = investment_readiness(metrics)
    today = timezone.localdate()
    score, created = FinancialHealthScore.objects.get_or_create(
        user=request.user,
        calculated_at__date=today,
        defaults={"score": metrics["score"], "savings_score": metrics["savings_score"],
            "expense_score": metrics["expense_score"], "budget_score": metrics["budget_score"],
            "overspending_score": metrics["overspending_score"]},
    )
    if not created:
        score.score = metrics["score"]
        score.savings_score = metrics["savings_score"]
        score.expense_score = metrics["expense_score"]
        score.budget_score = metrics["budget_score"]
        score.overspending_score = metrics["overspending_score"]
        score.save()

    signature = metrics_signature(metrics)
    state, _ = FinancialAiState.objects.get_or_create(user=request.user)
    signature_changed = state.last_seen_signature != signature
    if signature_changed:
        state.last_seen_signature = signature
        state.updates_since_ai += 1
        state.save()

    rule_insights = [
        {"title": title, "message": message, "insight_type": insight_type}
        for title, message, insight_type in rule_based_insights(metrics)
    ]
    ai_insight = FinancialInsight.objects.filter(user=request.user, source="ai").first()
    # Refresh immediately after a meaningful financial-data change, but never
    # again on a normal page reload with the same aggregate values.
    should_refresh_ai = metrics["has_data"] and (ai_insight is None or signature_changed)
    if should_refresh_ai:
        ai_content = get_ai_financial_content(metrics)
        if ai_content:
            if ai_insight:
                ai_insight.message = ai_content["summary"]
                ai_insight.data_signature = signature
                ai_insight.save()
            else:
                ai_insight = FinancialInsight.objects.create(user=request.user, title="AI financial summary",
                    message=ai_content["summary"], insight_type="info", source="ai", data_signature=signature)
            state.suggestions = ai_content["suggestions"]
            state.updates_since_ai = 0
            state.save()
            insights = [{"title": ai_insight.title, "message": ai_insight.message, "insight_type": ai_insight.insight_type}]
        else:
            insights = rule_insights
    elif ai_insight and not signature_changed:
        insights = [{"title": ai_insight.title, "message": ai_insight.message, "insight_type": ai_insight.insight_type}]
    else:
        insights = rule_insights

    fallback_suggestions = [{"title": title, "message": message} for title, message in investment_suggestions(metrics)]
    suggestions = list(state.suggestions or fallback_suggestions)
    present_titles = {suggestion["title"] for suggestion in suggestions}
    suggestions.extend(suggestion for suggestion in fallback_suggestions if suggestion["title"] not in present_titles)
    suggestions = suggestions[:5]
    learning_resources = {
        "Fixed Deposits": {"risk": "Lower volatility", "url": "https://investor.sebi.gov.in/iematerial.html", "label": "Learn about financial planning"},
        "Government Securities": {"risk": "Interest-rate risk", "url": "https://investor.sebi.gov.in/pdf/reference-material/beginners.pdf", "label": "Learn about government securities"},
        "Liquid Funds": {"risk": "Low to moderate risk", "url": "https://investor.sebi.gov.in/inv_aware_edu_videos.html", "label": "Learn about mutual funds"},
        "Gold ETFs": {"risk": "Market-price risk", "url": "https://investor.sebi.gov.in/pdf/reference-material/ppt/PPT%2013%20%20on%20Introduction%20to%20ETFs.pdf", "label": "Learn about ETFs"},
        "Nifty 50 Index Funds": {"risk": "Equity-market risk", "url": "https://investor.sebi.gov.in/index_mutual_fund.html", "label": "Learn about index funds"},
        "Diversified Equity Mutual Funds": {"risk": "Equity-market risk", "url": "https://investor.sebi.gov.in/iematerial.html", "label": "Learn about mutual funds"},
        "Individual Equity Shares": {"risk": "Higher volatility", "url": "https://investor.sebi.gov.in/iematerial.html", "label": "Learn about securities research"},
    }
    for suggestion in suggestions:
        suggestion.update(learning_resources.get(suggestion["title"], {}))

    return render(request, "financial_ai/financial_intelligence.html", {
        "metrics": metrics, "readiness": readiness, "insights": insights,
        "suggestions": suggestions if readiness["unlocked"] else [],
    })
