from django.urls import path
from . import views

urlpatterns = [
    path('despesas/', views.expense_list, name='expense_list'),
]