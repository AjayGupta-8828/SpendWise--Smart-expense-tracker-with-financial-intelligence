"""
URL configuration for Expense_tracker project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django import views
from django.contrib import admin
from django.urls import include, path
from expenses.views import *
from django.conf.urls.static import static
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path("",mainpage,name="mainpage"),
    path('accounts/', include('allauth.urls')),
    path('admin/', admin.site.urls),
    path("register/",register_user,name="register"),
    path("login/",login_user,name="login"),
    path("logout/",logout_user,name="logout"),
    path("add_transaction/",add_transaction,name="add_transaction"),
    path("transactions/",transaction,name="transactions"),
    path("delete_transaction/<int:id>/",delete_transaction,name="delete_transaction"),
    path("update_transaction/<int:id>/",update_transaction,name="update_transaction"),
    path("budget_tracker/",budget_tracker,name="budget_tracker"),
    path("update_budget/<int:id>/",update_budget,name="update_budget"),
    path('verify-otp/', verify_otp, name='verify_otp'),
    path('resend-otp/', resend_otp, name='resend_otp'),
    path("profile/",profile_view,name="profile"),
    path("profile/change-password/",change_password_view,name="change_password"),
]

if settings.DEBUG:
    urlpatterns+=static(settings.MEDIA_URL,
                        document_root=settings.MEDIA_ROOT)
urlpatterns+=staticfiles_urlpatterns()