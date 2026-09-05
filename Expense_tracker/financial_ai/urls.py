from django.urls import path

from . import views


urlpatterns = [
    path("", views.financial_intelligence, name="financial_intelligence"),
]
