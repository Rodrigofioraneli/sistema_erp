from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('novo/', views.product_create, name='product_create'),
    path('editar/<int:pk>/', views.product_edit, name='product_edit'),
    path('detalhes/<int:pk>/', views.product_detail, name='product_detail'),
    path('excluir/<int:pk>/', views.product_delete, name='product_delete'),
    path('estoque/', views.stock_manage, name='stock_manage'),
    path('kits/', views.kit_manage, name='kit_manage'),
]