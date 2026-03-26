from django.urls import path
from . import views

urlpatterns = [
    path('pdv/', views.pos_view, name='pos_view'),
    path('api/search-products/', views.product_search_api, name='product_search_api'),
    path('api/search-customers/', views.customer_search_api, name='customer_search_api'),
    path('api/save-sale/', views.save_sale, name='save_sale'),
]