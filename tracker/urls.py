from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_page, name='dashboard'),
    path('login/',  views.login_view,  name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('manifest.json', views.pwa_manifest,       name='pwa_manifest'),
    path('sw.js',         views.pwa_service_worker, name='pwa_sw'),
    path('api/sms/', views.sms_webhook, name='sms_webhook'),
    path('api/dashboard/', views.dashboard_api, name='dashboard_api'),
    
    path('api/transactions/<int:tx_id>/categorize/', views.categorize_transaction, name='categorize_transaction'),
    path('api/transactions/<int:tx_id>/split/',      views.split_transaction,      name='split_transaction'),
    path('api/transactions/<int:tx_id>/skip/',       views.skip_transaction,       name='skip_transaction'),
    path('api/transactions/<int:tx_id>/',            views.delete_transaction,     name='delete_transaction'),

    path('api/cycle/start/',       views.cycle_start,  name='cycle_start'),
    path('api/cycle/close/',       views.cycle_close,  name='cycle_close'),
    path('api/cycle/update/',      views.cycle_update, name='cycle_update'),
    path('api/cycle/<int:cycle_id>/', views.cycle_delete, name='cycle_delete'),
]
