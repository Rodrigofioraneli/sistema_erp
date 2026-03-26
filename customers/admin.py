from django.contrib import admin
from .models import Customer, FragranceFamily

@admin.register(FragranceFamily)
class FragranceFamilyAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'classification', 'loyalty_points')
    search_fields = ('name', 'cpf_cnpj', 'email')
    list_filter = ('classification', 'fragrance_preferences')
    filter_horizontal = ('fragrance_preferences',)