from django.contrib import admin
from .models import Sale, SaleItem

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1
    readonly_fields = ('price', 'subtotal')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'total', 'payment_method', 'created_at', 'status')
    inlines = [SaleItemInline]
    actions = ['finalize_sales']

    @admin.action(description='Finalizar Vendas Selecionadas (Baixar Estoque)')
    def finalize_sales(self, request, queryset):
        for sale in queryset:
            sale.status = 'completed'
            sale.save()
            sale.finalize()