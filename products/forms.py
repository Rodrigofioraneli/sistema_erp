from django import forms
from .models import Product, StockMovement

class ProductForm(forms.ModelForm):
    profit_margin = forms.DecimalField(
        label="Margem (%)", required=False, max_digits=10, decimal_places=2,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 50', 'style': 'text-align: left;', 'inputmode': 'decimal'})
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
            'cost_price': forms.TextInput(attrs={'class': 'money', 'placeholder': '0,00'}),
            'selling_price': forms.TextInput(attrs={'class': 'money', 'placeholder': '0,00'}),
            'stock_quantity': forms.NumberInput(attrs={'step': '1'}),
            'min_stock': forms.NumberInput(attrs={'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        readonly = kwargs.pop('readonly', False)
        super().__init__(*args, **kwargs)
        
        # Preenche a margem automaticamente ao editar
        if self.instance and self.instance.pk:
            self.fields['profit_margin'].initial = self.instance.profit_margin

        # Garante que os campos usem vírgula ao editar (Localização)
        self.fields['profit_margin'].localize = True
        self.fields['cost_price'].localize = True
        self.fields['selling_price'].localize = True

        for field_name, field in self.fields.items():
            if field_name != 'image':
                # Adiciona form-control sem remover classes existentes (como 'money')
                existing_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in existing_classes:
                    field.widget.attrs['class'] = f"{existing_classes} form-control".strip()
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