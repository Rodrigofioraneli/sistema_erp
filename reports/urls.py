from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('dashboard/', views.reports_dashboard, name='reports_dashboard'),
    path('pdv/', views.pos_view, name='pos_view'),
    path('estoque/', views.stock_manage, name='stock_manage'),
    path('exportar/', views.export_dashboard, name='export_dashboard'),
    path('download/<str:model_name>/<str:file_format>/', views.export_data, name='export_data'),
    path('importar/', views.import_data, name='import_data'),
    path('fiscal/download/<int:sale_id>/<str:doc_type>/', views.download_fiscal, name='download_fiscal'),
    path('backup/', views.download_db_backup, name='download_db_backup'),
    path('api/products/', views.product_search_api, name='product_search_api'),
    path('api/customers/', views.customer_search_api, name='customer_search_api'),
    path('save/', views.save_sale, name='save_sale'),
    path('relatorios/download/', views.download_report_file, name='download_report_file'),
    path('vendas/finalizar/<int:sale_id>/', views.finalize_sale, name='finalize_sale'),
    path('vendas/excluir/<int:sale_id>/', views.delete_sale, name='delete_sale'),
    path('vendas/pagamento/<int:sale_id>/', views.register_payment, name='register_payment'),
]