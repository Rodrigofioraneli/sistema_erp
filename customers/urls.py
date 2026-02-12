from django.urls import path
from . import views

urlpatterns = [
    path('', views.customer_list, name='customer_list'),
    path('novo/', views.customer_create, name='customer_create'),
    path('editar/<int:pk>/', views.customer_edit, name='customer_edit'),
    path('detalhe/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('excluir/<int:pk>/', views.customer_delete, name='customer_delete'),
]