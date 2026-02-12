from django import forms
from .models import Customer
import re

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        readonly = kwargs.pop('readonly', False)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            # Adiciona classe form-control para Bootstrap em todos os campos
            if not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect, forms.FileInput)):
                field.widget.attrs['class'] = 'form-control'
            if isinstance(field.widget, forms.FileInput):
                field.widget.attrs['class'] = 'form-control'
            
            if readonly:
                field.disabled = True

    def clean_cpf_cnpj(self):
        cpf_cnpj = self.cleaned_data.get('cpf_cnpj', '')
        if not cpf_cnpj:
            return cpf_cnpj
            
        # Remove caracteres não numéricos para validar apenas os dígitos
        numbers = re.sub(r'[^0-9]', '', cpf_cnpj)
        
        if len(numbers) == 11:
            if not self.validate_cpf(numbers):
                raise forms.ValidationError("CPF inválido.")
            # Retorna formatado: 000.000.000-00
            return f"{numbers[:3]}.{numbers[3:6]}.{numbers[6:9]}-{numbers[9:]}"
            
        elif len(numbers) == 14:
            if not self.validate_cnpj(numbers):
                raise forms.ValidationError("CNPJ inválido.")
            # Retorna formatado: 00.000.000/0000-00
            return f"{numbers[:2]}.{numbers[2:5]}.{numbers[5:8]}/{numbers[8:12]}-{numbers[12:]}"
            
        else:
            raise forms.ValidationError("O documento deve ter 11 (CPF) ou 14 (CNPJ) dígitos.")

    def validate_cpf(self, cpf):
        # Verifica tamanho e se todos os dígitos são iguais (ex: 111.111.111-11 é inválido)
        if len(cpf) != 11 or len(set(cpf)) == 1: return False
        
        # Validação do 1º Dígito Verificador
        sum_val = sum(int(cpf[i]) * (10 - i) for i in range(9))
        digit1 = (sum_val * 10 % 11) % 10
        if digit1 != int(cpf[9]): return False
        
        # Validação do 2º Dígito Verificador
        sum_val = sum(int(cpf[i]) * (11 - i) for i in range(10))
        digit2 = (sum_val * 10 % 11) % 10
        if digit2 != int(cpf[10]): return False
        
        return True

    def validate_cnpj(self, cnpj):
        if len(cnpj) != 14 or len(set(cnpj)) == 1: return False
        
        def calculate_digit(digits, weights):
            s = sum(d * w for d, w in zip(digits, weights))
            rem = s % 11
            return 0 if rem < 2 else 11 - rem

        # Pesos para o cálculo dos dígitos do CNPJ
        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        
        digits = [int(d) for d in cnpj]
        
        # Validação do 1º Dígito
        digit1 = calculate_digit(digits[:12], weights1)
        if digit1 != digits[12]: return False
        
        # Validação do 2º Dígito
        digit2 = calculate_digit(digits[:13], weights2)
        if digit2 != digits[13]: return False
        
        return True