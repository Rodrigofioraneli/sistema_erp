from django.urls import path
from . import views
from sales import views as sales_views
from products import views as product_views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('dashboard/', views.reports_dashboard, name='reports_dashboard'),
    path('pdv/', sales_views.pos_view, name='pos_view'),
    path('estoque/', product_views.stock_manage, name='stock_manage'),
    path('exportar/', views.export_dashboard, name='export_dashboard'),
    path('download/<str:model_name>/<str:file_format>/', views.export_data, name='export_data'),
    path('importar/', views.import_data, name='import_data'),
    path('despesas/', views.expense_manage, name='expense_manage'),
    path('fiscal/download/<int:sale_id>/<str:doc_type>/', views.download_fiscal, name='download_fiscal'),
    path('backup/', views.download_db_backup, name='download_db_backup'),
    path('api/products/', sales_views.product_search_api, name='product_search_api'),
    path('api/customers/', sales_views.customer_search_api, name='customer_search_api'),
    path('save/', sales_views.save_sale, name='save_sale'),
    path('relatorios/download/', views.download_report_file, name='download_report_file'),
    path('vendas/excluir/<int:sale_id>/', views.delete_sale, name='delete_sale'),
    path('vendas/item/<int:item_id>/delete/', views.delete_sale_item, name='delete_sale_item'),
    path('vendas/detalhe/<int:sale_id>/', views.sale_detail, name='sale_detail'),
    path('vendas/pagamento/<int:sale_id>/', views.register_payment, name='register_payment'),
    path('logs/', views.audit_logs, name='audit_logs'),
]