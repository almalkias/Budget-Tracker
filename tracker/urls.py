from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_page, name='dashboard'),
    path('api/sms/', views.sms_webhook, name='sms_webhook'),
    path('api/dashboard/', views.dashboard_api, name='dashboard_api'),
    path('api/transactions/<int:tx_id>/categorize/', views.categorize_transaction, name='categorize_transaction'),
    path('api/transactions/<int:tx_id>/skip/',       views.skip_transaction,      name='skip_transaction'),
    path('api/transactions/<int:tx_id>/',            views.delete_transaction,    name='delete_transaction'),
    path('api/cycle/start/',  views.cycle_start,  name='cycle_start'),
    path('api/cycle/close/',  views.cycle_close,  name='cycle_close'),
    path('api/cycle/update/', views.cycle_update, name='cycle_update'),
]
