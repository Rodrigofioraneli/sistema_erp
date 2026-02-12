from django import forms
from .models import Product, StockMovement

class ProductForm(forms.ModelForm):
    profit_margin = forms.DecimalField(
        label="Margem (%)", required=False, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'placeholder': 'Ex: 50'})
    )

    class Meta:
        model = Product
        exclude = ['created_at', 'updated_at']
        
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ex: Malbec Gold'}),
            'line': forms.TextInput(attrs={'placeholder': 'Ex: Malbec'}),
            'top_notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Ex: Limão, Bergamota...'}),
            'heart_notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Ex: Lavanda, Pimenta...'}),
            'base_notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Ex: Âmbar, Patchouli...'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Descrição detalhada do produto...'}),
            'volume': forms.TextInput(attrs={'placeholder': 'Ex: 100ml'}),
            'barcode': forms.TextInput(attrs={'placeholder': '789...'}),
            'batch_code': forms.TextInput(attrs={'placeholder': 'Lote 123'}),
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
            'cost_price': forms.NumberInput(attrs={'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'step': '0.01'}),
            'stock_quantity': forms.NumberInput(attrs={'step': '1'}),
            'min_stock': forms.NumberInput(attrs={'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        readonly = kwargs.pop('readonly', False)
        super().__init__(*args, **kwargs)
        
        # Preenche a margem automaticamente ao editar
        if self.instance and self.instance.pk:
            self.fields['profit_margin'].initial = self.instance.profit_margin

        for field_name, field in self.fields.items():
            if field_name != 'image':
                field.widget.attrs['class'] = 'form-control'
            if readonly:
                field.disabled = True

class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ['product', 'movement_type', 'quantity', 'reason']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'movement_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Compra de Lote, Decant, Venda...'}),
        }