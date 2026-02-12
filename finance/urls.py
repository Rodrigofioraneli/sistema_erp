from django.urls import path
from . import views

urlpatterns = [
    path('', views.finance_dashboard, name='finance_dashboard'),
    path('nova/', views.transaction_create, name='transaction_create'),
    path('editar/<int:pk>/', views.transaction_edit, name='transaction_edit'),
    path('excluir/<int:pk>/', views.transaction_delete, name='transaction_delete'),
    path('relatorios/', views.financial_reports, name='financial_reports'),
]