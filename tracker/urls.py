from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_page, name='dashboard'),
    path('api/sms/', views.sms_webhook, name='sms_webhook'),
    path('api/dashboard/', views.dashboard_api, name='dashboard_api'),
]
