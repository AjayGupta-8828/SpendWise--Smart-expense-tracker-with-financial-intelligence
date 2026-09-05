from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .models import FinancialHealthScore, FinancialInsight
from .ai_service import get_ai_insight, metrics_signature
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
    ai_insight = FinancialInsight.objects.filter(user=request.user, source="ai").first()
    if ai_insight and ai_insight.data_signature == signature:
        insights = [ai_insight]
    else:
        ai_message = get_ai_insight(metrics) if metrics["has_data"] else None
        if ai_message:
            if ai_insight:
                ai_insight.message = ai_message
                ai_insight.data_signature = signature
                ai_insight.save()
            else:
                ai_insight = FinancialInsight.objects.create(user=request.user, title="AI financial summary",
                    message=ai_message, insight_type="info", source="ai", data_signature=signature)
            insights = [ai_insight]
        else:
            insights = FinancialInsight.objects.filter(user=request.user, source="rule", created_at__date=today)
    if not insights:
        FinancialInsight.objects.bulk_create([
            FinancialInsight(user=request.user, title=title, message=message, insight_type=insight_type, source="rule")
            for title, message, insight_type in rule_based_insights(metrics)
        ])
        insights = FinancialInsight.objects.filter(user=request.user, source="rule", created_at__date=today)

    return render(request, "financial_ai/financial_intelligence.html", {
        "metrics": metrics, "readiness": readiness, "insights": insights,
        "suggestions": investment_suggestions(metrics) if readiness["unlocked"] else [],
    })
