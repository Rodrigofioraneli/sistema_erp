from django.contrib import admin
from .models import Product, Brand, OlfactoryFamily
from django.utils.html import format_html

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(OlfactoryFamily)
class OlfactoryFamilyAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'volume', 'selling_price', 'stock_quantity', 'status_stock_icon', 'status_validity_icon')
    list_filter = ('brand', 'product_type', 'gender', 'olfactory_family')
    search_fields = ('name', 'barcode', 'brand__name')
    readonly_fields = ('profit_margin_display',)
    
    fieldsets = (
        ('Identificação', {
            'fields': ('name', 'brand', 'line', 'product_type', 'gender', 'olfactory_family', 'description')
        }),
        ('Notas Olfativas', {
            'fields': ('top_notes', 'heart_notes', 'base_notes'),
            'classes': ('collapse',),
        }),
        ('Detalhes e Estoque', {
            'fields': ('volume', 'barcode', 'batch_code', 'expiration_date', 'stock_quantity', 'min_stock')
        }),
        ('Financeiro', {
            'fields': ('cost_price', 'selling_price', 'profit_margin_display')
        }),
        ('Mídia', {
            'fields': ('image',)
        }),
    )

    def profit_margin_display(self, obj):
        return f"{obj.profit_margin}%"
    profit_margin_display.short_description = "Margem de Lucro"

    def status_stock_icon(self, obj):
        if obj.stock_quantity <= 0:
            return format_html('<span style="color: red;">🔴 Sem Estoque</span>')
        elif obj.stock_quantity <= obj.min_stock:
            return format_html('<span style="color: orange;">🟠 Baixo</span>')
        return format_html('<span style="color: green;">🟢 Ok</span>')
    status_stock_icon.short_description = "Estoque"

    def status_validity_icon(self, obj):
        status = obj.status_validity
        if status == "Vencido":
            return format_html('<span style="color: red; font-weight: bold;">⚠️ Vencido</span>')
        elif status == "Vencendo em breve":
            return format_html('<span style="color: orange;">⏳ Vencendo</span>')
        return "✅"
    status_validity_icon.short_description = "Validade"