from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django import forms
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Sum, Count, F, Avg, Q, Case, When, Value, CharField
from django.db.models.functions import TruncMonth, ExtractHour
from django.utils import timezone
from django.conf import settings
from datetime import date, timedelta
from django.core.serializers.json import DjangoJSONEncoder
import json
import unicodedata
import csv
import os
import openpyxl
from io import TextIOWrapper
from sales.models import Sale, SaleItem
from products.models import Product, Brand, OlfactoryFamily, StockMovement, Category, Supplier, ProductComponent
from customers.models import Customer
from .models import CompanySettings, PaymentMethod
from finance.models import Transaction
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from django.urls import reverse

def normalize_str(s):
    """Remove acentos e coloca em minúsculo para busca robusta"""
    if s is None: return ''
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn').lower()

# --- Configuração da Empresa (Home) ---

class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = ['name', 'cnpj', 'state_registration', 'address', 'phone', 'email', 'website', 'logo']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            if isinstance(field.widget, forms.FileInput):
                field.widget.attrs['class'] = 'form-control'

@login_required
def settings_dashboard(request):
    """
    Nova aba de Configurações da Loja.
    Centraliza edição de Empresa, Categorias, Fornecedores, etc.
    """
    # 1. Processamento do Formulário da Empresa
    try:
        company = CompanySettings.objects.first()
        if not company:
            company = CompanySettings.objects.create()
    except (OperationalError, ProgrammingError):
        company = None

    # --- Lógica para Adicionar/Remover Itens (Marcas, Categorias, etc.) ---
    if request.method == 'POST' and 'item_action' in request.POST:
        action = request.POST.get('item_action')
        model_type = request.POST.get('model_type')
        item_name = request.POST.get('item_name')
        item_id = request.POST.get('item_id')

        model_map = {
            'brand': Brand,
            'category': Category,
            'family': OlfactoryFamily,
            'supplier': Supplier,
            'payment_method': PaymentMethod
        }

        ModelClass = model_map.get(model_type)
        if ModelClass:
            if action == 'add' and item_name:
                defaults = {}
                if model_type == 'supplier':
                    defaults = {'cnpj_cpf': '', 'phone': '', 'email': ''}
                
                ModelClass.objects.get_or_create(name=item_name.strip(), defaults=defaults)
                messages.success(request, f'Item adicionado com sucesso!')
            elif action == 'delete' and item_id:
                try:
                    ModelClass.objects.filter(pk=item_id).delete()
                    messages.success(request, 'Item removido com sucesso!')
                except Exception as e:
                    messages.error(request, f'Erro ao remover: {str(e)}')
        
        # Redireciona mantendo a aba ativa
        tab_map = {'brand': 'brands', 'family': 'families', 'category': 'categories', 'supplier': 'suppliers', 'payment_method': 'payments'}
        target_tab = tab_map.get(model_type, 'company')
        return redirect(f"{reverse('settings_dashboard')}?tab={target_tab}")

    if request.method == 'POST' and 'company_form' in request.POST:
        form = CompanySettingsForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dados da empresa atualizados!')
            return redirect(f"{reverse('settings_dashboard')}?tab=company")
    else:
        form = CompanySettingsForm(instance=company)

    # Define a aba ativa com base no parâmetro GET (padrão: company)
    active_tab = request.GET.get('tab', 'company')

    # 2. Dados para Listagem nas Abas de Configuração
    context = {
        'company_form': form,
        'company': company,
        'categories': Category.objects.all(),
        'suppliers': Supplier.objects.all(),
        'payment_methods': PaymentMethod.objects.all(),
        'olfactory_families': OlfactoryFamily.objects.all(),
        'brands': Brand.objects.all(),
        'active_tab': active_tab,
    }
    return render(request, 'reports/settings.html', context)

def home_view(request):
    """
    Antiga 'company_settings'. Agora é apenas a Home com Logo.
    """
    if not request.user.is_authenticated:
        return render(request, 'home.html')
    
    try:
        company = CompanySettings.objects.first()
    except (OperationalError, ProgrammingError):
        company = None
    
    return render(request, 'home.html', {'company': company})

# Alias para manter compatibilidade com config/urls.py que busca a view antiga
company_settings = home_view

@login_required
def product_list(request):
    q = request.GET.get('q', '')
    products = Product.objects.all().select_related('brand').order_by('name')
    
    if q:
        # Filtra usando Python para ignorar acentos (ex: 'limão' == 'limao')
        q_norm = normalize_str(q)
        # Converte QuerySet para lista filtrada
        products = [p for p in products if q_norm in normalize_str(p.name) or q_norm in normalize_str(p.barcode)]
    
    context = {
        'products': products,
        'search_query': q
    }
    return render(request, 'products/list.html', context)

# --- Formulários e Views de Cadastro de Produtos ---

class ProductForm(forms.ModelForm):
    # Campos personalizados para permitir digitar ou selecionar (Datalist)
    brand = forms.CharField(required=False, label="Marca", widget=forms.TextInput(attrs={'list': 'brands_list', 'class': 'form-control', 'placeholder': 'Selecione ou digite uma nova'}))
    olfactory_family = forms.CharField(required=False, label="Família Olfativa", widget=forms.TextInput(attrs={'list': 'families_list', 'class': 'form-control', 'placeholder': 'Selecione ou digite uma nova'}))
    
    # Campo de Margem de Lucro (Não salvo no banco, apenas para cálculo)
    profit_margin = forms.DecimalField(
        label="Margem de Lucro (%)", required=False, max_digits=10, decimal_places=2,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0', 'id': 'id_profit_margin'})
    )

    class Meta:
        model = Product
        fields = '__all__'
        widgets = {
            'name': forms.Textarea(attrs={'rows': 2}),
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
            'top_notes': forms.Textarea(attrs={'rows': 2}),
            'heart_notes': forms.Textarea(attrs={'rows': 2}),
            'base_notes': forms.Textarea(attrs={'rows': 2}),
            'description': forms.Textarea(attrs={'rows': 2}),
            'cost_price': forms.TextInput(attrs={'class': 'form-control money', 'placeholder': '0,00', 'id': 'id_cost_price'}),
            'selling_price': forms.TextInput(attrs={'class': 'form-control money', 'placeholder': '0,00', 'id': 'id_selling_price'}),
            'stock_quantity': forms.NumberInput(attrs={'class': 'form-control', 'onfocus': 'this.select()'}),
            'min_stock': forms.NumberInput(attrs={'class': 'form-control', 'onfocus': 'this.select()'}),
            'volume': forms.TextInput(attrs={'class': 'form-control', 'onfocus': 'this.select()'}),
        }
        
    class Media:
        js = ('js/product_scripts.js',)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Preenche os campos de texto com os nomes das FKs se estiver editando
        if self.instance.pk:
            if self.instance.brand:
                self.initial['brand'] = self.instance.brand.name
            if self.instance.olfactory_family:
                self.initial['olfactory_family'] = self.instance.olfactory_family.name

            # Calcula a margem inicial se houver preços
            if self.instance.cost_price and self.instance.selling_price and self.instance.cost_price > 0:
                margin = ((self.instance.selling_price - self.instance.cost_price) / self.instance.cost_price) * 100
                self.initial['profit_margin'] = round(margin, 2)

        # Habilita localização para campos decimais (aceitar vírgula)
        self.fields['cost_price'].localize = True
        self.fields['selling_price'].localize = True

        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect, forms.FileInput)):
                field.widget.attrs['class'] = 'form-control'
            if isinstance(field.widget, forms.FileInput):
                field.widget.attrs['class'] = 'form-control'

        # Adiciona eventos JS para cálculo e formatação
        self.fields['cost_price'].widget.attrs.update({'oninput': 'formatMoney(this); calculateSellingPrice()', 'onfocus': 'this.select()'})
        self.fields['profit_margin'].widget.attrs.update({'oninput': 'calculateSellingPrice()', 'onfocus': 'this.select()'})
        self.fields['selling_price'].widget.attrs.update({'oninput': 'formatMoney(this); calculateMargin()', 'onfocus': 'this.select()'})

    def clean_brand(self):
        name = self.cleaned_data.get('brand')
        if name:
            brand_obj, _ = Brand.objects.get_or_create(name__iexact=name.strip(), defaults={'name': name.strip()})
            return brand_obj
        return None

    def clean_olfactory_family(self):
        name = self.cleaned_data.get('olfactory_family')
        if name:
            family_obj, _ = OlfactoryFamily.objects.get_or_create(name__iexact=name.strip(), defaults={'name': name.strip()})
            return family_obj
        return None

@login_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Produto cadastrado com sucesso!')
            return redirect('product_list')
    else:
        form = ProductForm()
    
    # Contexto para a aba de catálogo no form (se usada)
    products = Product.objects.all().select_related('brand').order_by('-created_at')[:20]
    brands = Brand.objects.all().order_by('name')
    families = OlfactoryFamily.objects.all().order_by('name')
    
    return render(request, 'products/product_form.html', {'form': form, 'products': products, 'brands': brands, 'families': families})

@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Produto atualizado com sucesso!')
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    
    products = Product.objects.all().select_related('brand').order_by('-created_at')[:20]
    brands = Brand.objects.all().order_by('name')
    families = OlfactoryFamily.objects.all().order_by('name')
    
    return render(request, 'products/product_form.html', {'form': form, 'products': products, 'brands': brands, 'families': families})

@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.success(request, 'Produto excluído com sucesso!')
    return redirect('product_list')

# --- Gerenciamento de Estoque ---

class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ['product', 'movement_type', 'quantity', 'reason']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
            if isinstance(field.widget, forms.NumberInput):
                field.widget.attrs['onfocus'] = 'this.select()'

@login_required
def stock_manage(request):
    if request.method == 'POST':
        form = StockMovementForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Movimentação registrada!')
            return redirect('stock_manage')
    else:
        form = StockMovementForm()

    low_stock = Product.objects.filter(stock_quantity__lte=F('min_stock'))
    expiring = Product.objects.filter(expiration_date__lte=date.today() + timedelta(days=30))
    movements = StockMovement.objects.select_related('product').order_by('-created_at')[:20]

    context = {
        'form': form,
        'low_stock': low_stock,
        'expiring': expiring,
        'movements': movements
    }
    return render(request, 'products/stock_manage.html', context)

@login_required
def pos_view(request):
    return render(request, 'sales/pos.html')

@login_required
def reports_dashboard(request):
    # Filtros básicos de data (podem ser expandidos depois)
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # Queryset base de vendas finalizadas
    sales_qs = Sale.objects.filter(status='completed')
    
    # Aplica filtros de data se existirem
    if start_date_str:
        sales_qs = sales_qs.filter(created_at__date__gte=start_date_str)
    if end_date_str:
        sales_qs = sales_qs.filter(created_at__date__lte=end_date_str)
    
    # 1. Métricas de Vendas
    total_revenue = sales_qs.aggregate(Sum('total'))['total__sum'] or 0
    total_count = sales_qs.count()
    avg_ticket = (total_revenue / total_count) if total_count > 0 else 0

    # 1.1 Métricas Financeiras (Lucro e Custos)
    # Calcula o custo total dos itens das vendas filtradas
    # Nota: Assume o custo atual do produto (Product.cost_price)
    total_cost = SaleItem.objects.filter(sale__in=sales_qs).aggregate(
        cost=Sum(F('product__cost_price') * F('quantity'))
    )['cost'] or 0

    gross_profit = total_revenue - total_cost
    profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    sales_metrics = {
        'total_revenue': total_revenue,
        'total_count': total_count,
        'avg_ticket': avg_ticket,
        'total_cost': total_cost,
        'gross_profit': gross_profit,
        'profit_margin': profit_margin
    }
    
    # 1.2 Evolução Mensal (Vendas e Lucros)
    # Agrupa vendas por mês
    monthly_sales = sales_qs.annotate(month=TruncMonth('created_at'))\
        .values('month')\
        .annotate(revenue=Sum('total'))\
        .order_by('month')
    
    monthly_profit = []
    for item in monthly_sales:
        if item['month']:
            # Calcula custo aproximado para o mês (query separada para simplificar agregação)
            month_cost = SaleItem.objects.filter(sale__in=sales_qs, sale__created_at__month=item['month'].month, sale__created_at__year=item['month'].year)\
                .aggregate(cost=Sum(F('product__cost_price') * F('quantity')))['cost'] or 0
            monthly_profit.append({
                'month': item['month'].strftime('%Y-%m'),
                'revenue': float(item['revenue']),
                'cost': float(month_cost),
                'profit': float(item['revenue'] - month_cost)
            })

    # 1.3 Vendas por Forma de Pagamento
    payment_stats_qs = sales_qs.values('payment_method')\
        .annotate(total=Sum('total'), count=Count('id'))\
        .order_by('-total')
    
    payment_stats = list(payment_stats_qs)

    # 1.4 Horários de Pico (Operacional)
    peak_hours_qs = sales_qs.annotate(hour=ExtractHour('created_at'))\
        .values('hour')\
        .annotate(count=Count('id'))\
        .order_by('hour')
    
    peak_hours = [{'hour': item['hour'], 'count': item['count']} for item in peak_hours_qs]

    # 2. Top Produtos
    top_products = SaleItem.objects.filter(sale__in=sales_qs)\
        .values('product__name')\
        .annotate(total_qty=Sum('quantity'))\
        .order_by('-total_qty')[:5]
        
    # 3. Métricas de Estoque
    stock_metrics = Product.objects.aggregate(
        total_value=Sum(F('stock_quantity') * F('cost_price')),
        total_items=Sum('stock_quantity')
    )
    
    low_stock_count = Product.objects.filter(stock_quantity__lte=5).count()
    
    # Lista de produtos com estoque baixo para exibir na tabela
    low_stock_products = Product.objects.filter(stock_quantity__lte=5)\
        .values('name', 'stock_quantity', 'selling_price', 'image', 'image_url')\
        .order_by('stock_quantity')[:10]
    
    # Lista de vendas recentes para exibição em tabela
    recent_sales = sales_qs.select_related('customer').order_by('-created_at')[:20]

    # 4. Visualização de Relatório na Tela (Se solicitado)
    report_type = request.GET.get('report_type')
    report_data = None
    if report_type:
        # Gera os dados do relatório escolhido para exibir na tela
        r_title, r_headers, r_data, r_summary = _get_report_data(report_type, start_date_str, end_date_str)
        report_data = {
            'title': r_title, 'headers': r_headers, 'data': r_data, 'summary': r_summary
        }

    context = {
        'sales_metrics': sales_metrics,
        'top_products': top_products,
        'stock_metrics': stock_metrics,
        'low_stock_count': low_stock_count,
        # Flags para exibir as seções no template
        'show_sales': True,
        'show_products': True,
        'show_stock': True,
        'show_financial': True,
        'show_customers': True,
        'show_employees': True,
        # Listas vazias para evitar erros nos gráficos enquanto não implementamos a lógica complexa
        'monthly_profit': monthly_profit, # Agora populado
        'payment_stats': payment_stats,   # Novo dado
        'olfactory_stats': [],
        'peak_hours': peak_hours,         # Agora populado
        'monthly_expenses': [],
        'stock_by_brand': [],
        'dead_stock': [],
        'expiring_soon': low_stock_products, # Usando para mostrar estoque baixo
        'recent_movements': [],
        'recent_sales': recent_sales, # Nova lista de vendas
        'start_date': start_date_str,
        'end_date': end_date_str,
        'report_data': report_data,   # Dados do relatório visualizado
        'report_type': report_type,   # Tipo selecionado
    }
    return render(request, 'reports/index.html', context)

@login_required
def product_search_api(request):
    """Busca produtos de forma eficiente para o PDV via API."""
    q = request.GET.get('q', '')
    q_norm = normalize_str(q)
    
    all_products = Product.objects.all().values('id', 'name', 'selling_price', 'volume', 'stock_quantity', 'image', 'image_url', 'barcode')
    products = []
    for p in all_products:
        if q_norm in normalize_str(p['name']) or (p['barcode'] and q_norm in normalize_str(p['barcode'])):
            products.append(p)
            if len(products) >= 20: break

    data = [
        {
            'id': p['id'],
            'name': p['name'],
            'price': float(p['selling_price']),
            'volume': p['volume'],
            'stock': p['stock_quantity'],
            'image': f"{settings.MEDIA_URL}{p['image']}" if p['image'] else (p['image_url'] if p['image_url'] else '')
        }
        for p in products
    ]
    return JsonResponse(data, safe=False)

@login_required
def customer_search_api(request):
    """Busca clientes de forma eficiente para o PDV via API."""
    q = request.GET.get('q', '')
    customers = Customer.objects.filter(name__icontains=q).values('id', 'name')[:10]
    return JsonResponse(list(customers), safe=False)

@login_required
@csrf_exempt
def save_sale(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            with transaction.atomic():
                # 1. Cria a Venda
                sale = Sale.objects.create(
                    customer_id=data.get('customer_id') or None,
                    payment_method=data.get('payment_method'),
                    status=data.get('status', 'completed'),
                    total=0 # Será atualizado abaixo
                )
                
                total_sale = 0
                
                # 2. Cria os Itens e Baixa Estoque
                for item in data.get('items', []):
                    product = Product.objects.get(id=item['id'])
                    qty = int(item['quantity'])
                    price = float(item['price'])
                    
                    SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=qty,
                        price=price
                    )
                    
                    total_sale += price * qty
                    
                    # Baixa Estoque se a venda for finalizada
                    if sale.status == 'completed':
                        product.stock_quantity -= qty
                        product.save()
                
                # 3. Aplica Descontos e Taxas
                discount_val = float(data.get('discount_value', 0))
                discount_type = data.get('discount_type', 'fixed')
                tax_val = float(data.get('tax_value', 0))
                tax_type = data.get('tax_type', 'fixed')
                
                discount = discount_val if discount_type == 'fixed' else (total_sale * discount_val / 100)
                tax = tax_val if tax_type == 'fixed' else (total_sale * tax_val / 100)
                
                sale.total = total_sale - discount + tax
                sale.save()
                
            return JsonResponse({'status': 'success', 'sale_id': sale.id})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Método não permitido'})

@login_required
def download_report_file(request):
    report_type = request.GET.get('report_type', 'sales')
    file_format = request.GET.get('format', 'excel')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    title, headers, data, summary = _get_report_data(report_type, start_date, end_date)
    
    if file_format == 'excel':
        try:
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="relatorio_{report_type}.xlsx"'
            
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Relatório"
            
            ws.append([title])
            ws.append([f"Período: {start_date or 'Início'} a {end_date or 'Hoje'}"])
            ws.append([])
            ws.append(headers)
            
            for row in data:
                # Garante que os dados sejam strings para evitar erros de tipo no Excel
                ws.append([str(cell) if cell is not None else "" for cell in row])
                
            ws.append([])
            for k, v in summary.items():
                ws.append([k.replace('_', ' ').title(), str(v)])
                
            wb.save(response)
            return response
        except Exception as e:
            return HttpResponse(f"Erro ao gerar Excel: {str(e)}", status=500)

    elif file_format == 'pdf':
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="relatorio_{report_type}.pdf"'
        
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        
        doc = SimpleDocTemplate(response, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()
        
        elements.append(Paragraph(title, styles['Title']))
        elements.append(Paragraph(f"Período: {start_date or 'Início'} a {end_date or 'Hoje'}", styles['Normal']))
        elements.append(Spacer(1, 12))
        
        table_data = [headers] + data
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
        ]))
        elements.append(t)
        
        elements.append(Spacer(1, 12))
        for k, v in summary.items():
            elements.append(Paragraph(f"<b>{k.replace('_', ' ').title()}:</b> {v}", styles['Normal']))
            
        doc.build(elements)
        return response

    return redirect('reports_dashboard')

def _get_report_data(report_type, start_date, end_date):
    data = []
    headers = []
    title = ""
    summary = {}

    # CORREÇÃO DO ERRO: Tratamento para datas "None" ou vazias
    if start_date in ['None', '', None]: start_date = None
    if end_date in ['None', '', None]: end_date = None

    if report_type == 'sales':
        qs = Sale.objects.all().select_related('customer').order_by('-created_at')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
        title = "Relatório Geral de Vendas"
        headers = ['ID', 'Data', 'Cliente', 'Status', 'Pagamento', 'Total']
        for s in qs:
            data.append([s.id, s.created_at.strftime('%d/%m/%Y %H:%M'), s.customer.name if s.customer else 'Consumidor Final', s.get_status_display(), s.get_payment_method_display(), f"R$ {s.total:.2f}"])
        summary['total_vendas'] = f"R$ {sum(s.total for s in qs):.2f}"

    elif report_type == 'pending':
        qs = Sale.objects.filter(status='pending').select_related('customer').prefetch_related('items__product').order_by('-created_at')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
        title = "Relatório de Vendas Pendentes / Orçamentos"
        headers = ['ID', 'Data', 'Cliente', 'Produtos', 'Qtd. Total', 'Valor Total']
        for s in qs:
            products_list = [f"{item.product.name} ({item.quantity})" for item in s.items.all()]
            products_str = "; ".join(products_list)
            total_qty = sum(item.quantity for item in s.items.all())
            data.append([s.id, s.created_at.strftime('%d/%m/%Y %H:%M'), s.customer.name if s.customer else 'Consumidor Final', products_str, total_qty, f"R$ {s.total:.2f}"])
        summary['total_pendente'] = f"R$ {sum(s.total for s in qs):.2f}"

    elif report_type == 'inventory':
        qs = Product.objects.all().order_by('name')
        title = "Relatório de Estoque e Valoração"
        headers = ['Produto', 'Marca', 'Estoque', 'Custo Unit.', 'Venda Unit.', 'Total Custo', 'Total Venda']
        total_cost = 0
        total_sale = 0
        for p in qs:
            t_cost = p.stock_quantity * p.cost_price
            t_sale = p.stock_quantity * p.selling_price
            total_cost += t_cost
            total_sale += t_sale
            data.append([p.name, p.brand.name if p.brand else '-', p.stock_quantity, f"R$ {p.cost_price:.2f}", f"R$ {p.selling_price:.2f}", f"R$ {t_cost:.2f}", f"R$ {t_sale:.2f}"])
        summary['custo_total'] = f"R$ {total_cost:.2f}"
        summary['venda_total'] = f"R$ {total_sale:.2f}"
        summary['lucro_potencial'] = f"R$ {total_sale - total_cost:.2f}"

    elif report_type == 'best_sellers':
        qs = SaleItem.objects.filter(sale__status='completed')
        if start_date: qs = qs.filter(sale__created_at__date__gte=start_date)
        if end_date: qs = qs.filter(sale__created_at__date__lte=end_date)
        qs = qs.values('product__name').annotate(total_qty=Sum('quantity'), total_rev=Sum(F('quantity') * F('price'))).order_by('-total_qty')
        title = "Produtos Mais Vendidos"
        headers = ['Produto', 'Qtd. Vendida', 'Receita Total']
        for item in qs:
            data.append([item['product__name'], item['total_qty'], f"R$ {item['total_rev']:.2f}"])

    elif report_type == 'sales_by_customer':
        qs = Sale.objects.filter(status='completed')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
        qs = qs.values('customer__name').annotate(total_spent=Sum('total'), count=Count('id')).order_by('-total_spent')
        title = "Vendas por Cliente"
        headers = ['Cliente', 'Qtd. Compras', 'Total Gasto']
        for item in qs:
            name = item['customer__name'] if item['customer__name'] else 'Consumidor Final'
            data.append([name, item['count'], f"R$ {item['total_spent']:.2f}"])

    elif report_type == 'sales_by_brand':
        qs = SaleItem.objects.filter(sale__status='completed')
        if start_date: qs = qs.filter(sale__created_at__date__gte=start_date)
        if end_date: qs = qs.filter(sale__created_at__date__lte=end_date)
        qs = qs.values('product__brand__name').annotate(total_sold=Sum(F('quantity') * F('price')), qty=Sum('quantity')).order_by('-total_sold')
        title = "Vendas por Marca"
        headers = ['Marca', 'Qtd. Itens', 'Total Vendido']
        for item in qs:
            brand = item['product__brand__name'] if item['product__brand__name'] else 'Sem Marca'
            data.append([brand, item['qty'], f"R$ {item['total_sold']:.2f}"])

    elif report_type == 'sales_by_user':
        qs = Sale.objects.filter(status='completed')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
        qs = qs.values('salesperson__username').annotate(total_sold=Sum('total'), count=Count('id')).order_by('-total_sold')
        title = "Vendas por Vendedor"
        headers = ['Vendedor', 'Qtd. Vendas', 'Total Vendido']
        for item in qs:
            user = item['salesperson__username'] if item['salesperson__username'] else 'Sistema'
            data.append([user, item['count'], f"R$ {item['total_sold']:.2f}"])

    elif report_type == 'sales_by_payment':
        qs = Sale.objects.filter(status='completed')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
        qs = qs.values('payment_method').annotate(total=Sum('total'), count=Count('id')).order_by('-total')
        title = "Vendas por Forma de Pagamento"
        headers = ['Forma de Pagamento', 'Qtd. Vendas', 'Total']
        payment_map = {'pix': 'PIX', 'credit': 'Crédito', 'debit': 'Débito', 'cash': 'Dinheiro'}
        for item in qs:
            method = payment_map.get(item['payment_method'], item['payment_method'])
            data.append([method, item['count'], f"R$ {item['total']:.2f}"])

    elif report_type == 'profit_by_product':
        qs = SaleItem.objects.filter(sale__status='completed').select_related('product')
        if start_date: qs = qs.filter(sale__created_at__date__gte=start_date)
        if end_date: qs = qs.filter(sale__created_at__date__lte=end_date)
        
        # Agrupamento em Python pois o custo está no produto
        product_stats = {}
        for item in qs:
            pid = item.product.id
            if pid not in product_stats:
                product_stats[pid] = {'name': item.product.name, 'qty': 0, 'revenue': 0, 'cost': 0}
            
            product_stats[pid]['qty'] += item.quantity
            product_stats[pid]['revenue'] += item.price * item.quantity
            # Nota: Usa o custo atual do produto
            product_stats[pid]['cost'] += item.product.cost_price * item.quantity
            
        title = "Relatório de Lucro por Produto"
        headers = ['Produto', 'Qtd Vendida', 'Receita Total', 'Custo Total', 'Lucro Bruto', 'Margem %']
        
        total_profit = 0
        sorted_stats = sorted(product_stats.values(), key=lambda x: x['revenue'] - x['cost'], reverse=True)
        
        for p in sorted_stats:
            profit = p['revenue'] - p['cost']
            margin = (profit / p['revenue'] * 100) if p['revenue'] > 0 else 0
            total_profit += profit
            data.append([p['name'], p['qty'], f"R$ {p['revenue']:.2f}", f"R$ {p['cost']:.2f}", f"R$ {profit:.2f}", f"{margin:.1f}%"])
            
        summary['lucro_total_produtos'] = f"R$ {total_profit:.2f}"

    elif report_type == 'profit_by_sale':
        qs = Sale.objects.filter(status='completed').prefetch_related('items__product').order_by('-created_at')
        if start_date: qs = qs.filter(created_at__date__gte=start_date)
        if end_date: qs = qs.filter(created_at__date__lte=end_date)
        
        title = "Relatório de Lucro por Venda"
        headers = ['ID Venda', 'Data', 'Cliente', 'Total Venda', 'Custo Produtos', 'Lucro', 'Margem %']
        
        total_profit_period = 0
        for s in qs:
            cost = sum(item.product.cost_price * item.quantity for item in s.items.all())
            profit = s.total - cost
            margin = (profit / s.total * 100) if s.total > 0 else 0
            total_profit_period += profit
            data.append([s.id, s.created_at.strftime('%d/%m/%Y'), s.customer.name if s.customer else 'Consumidor', f"R$ {s.total:.2f}", f"R$ {cost:.2f}", f"R$ {profit:.2f}", f"{margin:.1f}%"])
            
        summary['lucro_liquido_periodo'] = f"R$ {total_profit_period:.2f}"

    elif report_type == 'cash_flow':
        qs = Transaction.objects.all().order_by('-payment_date')
        if start_date: qs = qs.filter(payment_date__gte=start_date)
        if end_date: qs = qs.filter(payment_date__lte=end_date)
        
        title = "Movimento do Caixa (Entradas e Saídas)"
        headers = ['Data', 'Descrição', 'Tipo', 'Valor', 'Status']
        
        balance = 0
        for t in qs:
            val_str = f"R$ {t.value:.2f}"
            if t.transaction_type == 'expense':
                val_str = f"- R$ {t.value:.2f}"
                if t.status == 'paid': balance -= t.value
            elif t.status == 'paid':
                balance += t.value
                
            data.append([t.payment_date.strftime('%d/%m/%Y'), t.description, t.get_transaction_type_display(), val_str, t.get_status_display()])
            
        summary['saldo_periodo'] = f"R$ {balance:.2f}"

    elif report_type == 'financial_expenses':
        qs = Transaction.objects.filter(transaction_type='expense').order_by('due_date')
        if start_date: qs = qs.filter(due_date__gte=start_date)
        if end_date: qs = qs.filter(due_date__lte=end_date)
        
        title = "Relatório de Despesas"
        headers = ['Vencimento', 'Descrição', 'Valor', 'Status']
        total_exp = sum(t.value for t in qs)
        for t in qs:
            data.append([t.due_date.strftime('%d/%m/%Y'), t.description, f"R$ {t.value:.2f}", t.get_status_display()])
        summary['total_despesas'] = f"R$ {total_exp:.2f}"

    elif report_type == 'balance_sheet':
        # Balanço Simplificado
        stock_val = Product.objects.aggregate(val=Sum(F('stock_quantity') * F('cost_price')))['val'] or 0
        receivables = Transaction.objects.filter(transaction_type='income', status='pending').aggregate(Sum('value'))['value__sum'] or 0
        payables = Transaction.objects.filter(transaction_type='expense', status='pending').aggregate(Sum('value'))['value__sum'] or 0
        cash_balance = (Transaction.objects.filter(transaction_type='income', status='paid').aggregate(Sum('value'))['value__sum'] or 0) - \
                       (Transaction.objects.filter(transaction_type='expense', status='paid').aggregate(Sum('value'))['value__sum'] or 0)

        title = "Balanço Patrimonial Simplificado (Posição Atual)"
        headers = ['Conta', 'Tipo', 'Valor']
        data = [
            ['Estoque (Custo)', 'Ativo', f"R$ {stock_val:.2f}"],
            ['Contas a Receber', 'Ativo', f"R$ {receivables:.2f}"],
            ['Saldo em Caixa', 'Ativo', f"R$ {cash_balance:.2f}"],
            ['Contas a Pagar', 'Passivo', f"R$ {payables:.2f}"],
            ['Patrimônio Líquido Estimado', 'Resultado', f"R$ {stock_val + receivables + cash_balance - payables:.2f}"]
        ]
        summary['ativo_total'] = f"R$ {stock_val + receivables + cash_balance:.2f}"

    return title, headers, data, summary

@login_required
def export_dashboard(request):
    return render(request, 'reports/export.html')

@login_required
def export_data(request, model_name, file_format):
    # 1. Preparação dos Dados (Queryset e Headers)
    if model_name == 'products':
        queryset = Product.objects.all().select_related('brand')
        filename = 'produtos'
        headers = [
            'ID', 'Nome', 'Marca', 'Linha', 'Tipo', 'Gênero', 'Família Olfativa',
            'Notas de Saída', 'Notas de Corpo', 'Notas de Fundo', 'Descrição',
            'Volume', 'Código de Barras', 'Lote', 'Validade', 'Preço de Custo',
            'Preço de Venda', 'Qtd. em Estoque', 'Estoque Mínimo', 'URL da Imagem'
        ]
        def get_row(obj):
            return [
                str(obj.id),
                obj.name,
                obj.brand.name if obj.brand else '',
                obj.line,
                obj.get_product_type_display(),
                obj.get_gender_display(),
                obj.olfactory_family.name if obj.olfactory_family else '',
                obj.top_notes,
                obj.heart_notes,
                obj.base_notes,
                obj.description,
                obj.volume,
                obj.barcode,
                obj.batch_code,
                obj.expiration_date.strftime('%Y-%m-%d') if obj.expiration_date else '',
                f"{obj.cost_price:.2f}".replace('.', ','),
                f"{obj.selling_price:.2f}".replace('.', ','),
                str(obj.stock_quantity),
                str(obj.min_stock),
                obj.image_url if obj.image_url else ''
            ]
            
    elif model_name == 'sales':
        queryset = Sale.objects.all()
        filename = 'vendas'
        headers = ['ID', 'Data', 'Total', 'Status', 'Pagamento']
        def get_row(obj):
            return [str(obj.id), obj.created_at.strftime('%d/%m/%Y %H:%M'), str(obj.total), obj.get_status_display(), obj.payment_method]
            
    elif model_name == 'customers':
        queryset = Customer.objects.all()
        filename = 'clientes'
        headers = ['ID', 'Nome', 'Email', 'Telefone']
        def get_row(obj):
            return [str(obj.id), obj.name, obj.email, obj.phone]
            
    elif model_name == 'financial':
        queryset = Sale.objects.filter(status='completed').prefetch_related('items__product')
        filename = 'relatorio_financeiro_lucros'
        headers = ['ID Venda', 'Data', 'Total Venda', 'Custo Produtos', 'Lucro Bruto', 'Margem %']
        def get_row(obj):
            cost = sum(item.product.cost_price * item.quantity for item in obj.items.all())
            revenue = obj.total
            profit = revenue - cost
            margin = (profit / revenue * 100) if revenue > 0 else 0
            return [str(obj.id), obj.created_at.strftime('%d/%m/%Y %H:%M'), f"{revenue:.2f}", f"{cost:.2f}", f"{profit:.2f}", f"{margin:.2f}"]
    else:
        return JsonResponse({'status': 'error', 'message': 'Modelo inválido'})

    # 2. Geração da Lista de Dados
    data_rows = []
    for obj in queryset:
        data_rows.append(get_row(obj))

    # 3. Renderização por Formato
    if file_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerows(data_rows)
        return response

    elif file_format == 'excel':
        try:
            import openpyxl
        except ImportError:
            return HttpResponse("Erro: Biblioteca 'openpyxl' não instalada. Instale com: pip install openpyxl", status=500)
            
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Dados"
        ws.append(headers)
        for row in data_rows:
            ws.append(row)
        wb.save(response)
        return response

    elif file_format == 'pdf':
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
        except ImportError:
            return HttpResponse("Erro: Biblioteca 'reportlab' não instalada. Instale com: pip install reportlab", status=500)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
        
        doc = SimpleDocTemplate(response, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()
        
        elements.append(Paragraph(f"Relatório: {filename.replace('_', ' ').title()}", styles['Title']))
        
        table_data = [headers] + data_rows
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(t)
        doc.build(elements)
        return response
        
    elif file_format == 'json':
        json_data = [dict(zip(headers, row)) for row in data_rows]
        return JsonResponse(json_data, safe=False, encoder=DjangoJSONEncoder)

    return JsonResponse({'status': 'error', 'message': 'Formato não suportado'})

@login_required
def import_data(request):
    # --- Lógica de Importação de Arquivos ---
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        filename = uploaded_file.name.lower()
        model_type = request.POST.get('model') # Captura o tipo selecionado (se houver)
        
        try:
            data_list = []
            
            # 1. Parse File
            if filename.endswith('.csv'):
                # Wrapper para ler bytes como texto (utf-8-sig lida com BOM do Excel)
                file_file = TextIOWrapper(uploaded_file.file, encoding='utf-8-sig')
                # Tenta detectar se usa ponto e vírgula (comum no Excel Brasil) ou vírgula
                sample = file_file.read(2048)
                file_file.seek(0)
                delimiter = ';' if sample.count(';') > sample.count(',') else ','
                reader = csv.DictReader(file_file, delimiter=delimiter)
                data_list = list(reader)
            elif filename.endswith('.json'):
                data_list = json.load(uploaded_file)
            elif filename.endswith('.xlsx'):
                wb = openpyxl.load_workbook(uploaded_file)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))
                if rows:
                    # 1. Busca inteligente da linha de cabeçalho (ignora linhas vazias ou títulos no topo)
                    header_row_index = 0
                    for i, row in enumerate(rows[:20]): # Verifica as primeiras 20 linhas
                        row_values = [str(cell).lower().strip() for cell in row if cell is not None]
                        # Palavras-chave para identificar se é um cabeçalho válido
                        keywords = ['nome', 'name', 'código', 'codigo', 'barcode', 'preço', 'price', 'estoque', 'stock', 'email', 'telefone']
                        if any(k in row_values for k in keywords):
                            header_row_index = i
                            break
                    
                    # 2. Mapeia as colunas baseadas no cabeçalho encontrado
                    raw_headers = rows[header_row_index]
                    header_map = {i: str(h).lower().strip() for i, h in enumerate(raw_headers) if h is not None and str(h).strip()}
                    
                    # 3. Processa os dados
                    for row in rows[header_row_index + 1:]:
                        row_dict = {}
                        has_data = False
                        for i, cell in enumerate(row):
                            if i in header_map:
                                val = str(cell) if cell is not None else ''
                                # Remove .0 de números inteiros (comum no Excel)
                                if val.endswith('.0'): val = val[:-2]
                                row_dict[header_map[i]] = val.strip()
                                if val.strip(): has_data = True
                        if has_data:
                            data_list.append(row_dict)
            else:
                messages.error(request, 'Formato inválido. Use .csv, .json ou .xlsx')
                return render(request, 'reports/import.html')
            
            if not data_list:
                messages.warning(request, 'O arquivo está vazio.')
                return render(request, 'reports/import.html')

            # 2. Identify Model based on headers (heuristic)
            first_row = {k.lower().strip(): v for k, v in data_list[0].items()}
            keys = first_row.keys()
            
            success_count = 0
            errors = []
            model_name = ""

            # Lógica para Produtos (busca por colunas típicas)
            # Verifica se foi selecionado 'products' OU se os cabeçalhos indicam produtos
            if model_type == 'products' or (not model_type and any(k in keys for k in ['estoque', 'stock', 'stock_quantity', 'preço', 'price', 'selling_price'])):
                model_name = "Produtos"
                for row in data_list:
                    try:
                        row_lower = {k.lower().strip(): v for k, v in row.items()}
                        
                        pk = row_lower.get('id')
                        barcode = row_lower.get('código de barras') or row_lower.get('codigo de barras') or row_lower.get('barcode')
                        
                        if barcode:
                            barcode = str(barcode).strip()
                            if not barcode: barcode = None
                        else:
                            barcode = None

                        name = row_lower.get('nome') or row_lower.get('name')
                        
                        if not name:
                            errors.append(f"Linha ignorada por não conter 'Nome': {row}")
                            continue

                        # --- Lógica de Relacionamentos (Foreign Keys) ---
                        brand_obj = None
                        brand_name = row_lower.get('marca') or row_lower.get('brand')
                        if brand_name:
                            brand_obj, _ = Brand.objects.get_or_create(name__iexact=brand_name.strip(), defaults={'name': brand_name.strip()})

                        olfactory_family_obj = None
                        olfactory_family_name = row_lower.get('família olfativa') or row_lower.get('familia olfativa')
                        if olfactory_family_name:
                            olfactory_family_obj, _ = OlfactoryFamily.objects.get_or_create(name__iexact=olfactory_family_name.strip(), defaults={'name': olfactory_family_name.strip()})
                        
                        # --- Busca o produto existente ---
                        product = None
                        if pk and Product.objects.filter(pk=pk).exists():
                            product = Product.objects.get(pk=pk)
                        elif barcode and Product.objects.filter(barcode=barcode).exists():
                            product = Product.objects.get(barcode=barcode)
                        elif name:
                            # Busca por nome e marca para ser mais preciso
                            search_filter = {'name__iexact': name}
                            if brand_obj:
                                search_filter['brand'] = brand_obj
                            product = Product.objects.filter(**search_filter).first()
                        
                        # --- Prepara os dados ---
                        product_data = {
                            'name': name,
                            'line': row_lower.get('linha'),
                            'product_type': row_lower.get('tipo'),
                            'gender': (row_lower.get('gênero') or row_lower.get('genero') or '').upper(),
                            'olfactory_family': olfactory_family_obj,
                            'top_notes': row_lower.get('notas de saída'),
                            'heart_notes': row_lower.get('notas de corpo'),
                            'base_notes': row_lower.get('notas de fundo'),
                            'description': row_lower.get('descrição') or row_lower.get('descricao'),
                            'volume': row_lower.get('volume'),
                            'barcode': barcode,
                            'batch_code': row_lower.get('lote'),
                            'expiration_date': row_lower.get('validade') or None,
                            'cost_price': row_lower.get('preço de custo') or row_lower.get('preco de custo') or row_lower.get('custo'),
                            'selling_price': row_lower.get('preço de venda') or row_lower.get('preco de venda') or row_lower.get('preço') or row_lower.get('price'),
                            'stock_quantity': row_lower.get('qtd. em estoque') or row_lower.get('qtd em estoque') or row_lower.get('estoque'),
                            'min_stock': row_lower.get('estoque mínimo') or row_lower.get('estoque minimo'),
                            'image_url': row_lower.get('url da imagem') or row_lower.get('imagem')
                        }
                        if brand_obj:
                            product_data['brand'] = brand_obj

                        # --- Limpa e Converte os Tipos ---
                        if product_data['cost_price']: product_data['cost_price'] = Decimal(str(product_data['cost_price']).replace(',', '.'))
                        if product_data['selling_price']: product_data['selling_price'] = Decimal(str(product_data['selling_price']).replace(',', '.'))
                        if product_data['stock_quantity']: product_data['stock_quantity'] = int(float(str(product_data['stock_quantity']).replace(',', '.')))
                        if product_data['min_stock']: product_data['min_stock'] = int(float(str(product_data['min_stock']).replace(',', '.')))
                        if not product_data['expiration_date']: del product_data['expiration_date']

                        # Filtra valores nulos/vazios para não sobrescrever dados existentes com nada
                        update_data = {k: v for k, v in product_data.items() if v is not None and v != ''}
                        
                        if product: # Atualiza
                            for key, value in update_data.items():
                                setattr(product, key, value)
                            product.save()
                            success_count += 1
                        elif name and update_data.get('selling_price'): # Cria
                            # Garante campos obrigatórios para criação
                            if 'brand' not in update_data:
                                default_brand, _ = Brand.objects.get_or_create(name="Geral")
                                update_data['brand'] = default_brand
                            if 'cost_price' not in update_data:
                                update_data['cost_price'] = 0
                            if 'volume' not in update_data:
                                update_data['volume'] = 'N/A'
                            
                            Product.objects.create(**update_data)
                            success_count += 1
                    except Exception as e:
                        errors.append(f"Erro na linha {row}: {str(e)}")

            # Lógica para Clientes
            # Verifica se foi selecionado 'customers' OU se os cabeçalhos indicam clientes
            elif model_type == 'customers' or (not model_type and any(k in keys for k in ['email', 'telefone', 'phone'])):
                model_name = "Clientes"
                for row in data_list:
                    try:
                        row_lower = {k.lower().strip(): v for k, v in row.items()}
                        pk = row_lower.get('id')
                        defaults = {
                            'name': row_lower.get('nome') or row_lower.get('name'),
                            'email': row_lower.get('email'),
                            'phone': row_lower.get('telefone') or row_lower.get('phone')
                        }
                        # Remove chaves vazias
                        defaults = {k: v for k, v in defaults.items() if v}
                        
                        if pk:
                            Customer.objects.update_or_create(pk=pk, defaults=defaults)
                        elif defaults.get('email'):
                            Customer.objects.update_or_create(email=defaults['email'], defaults=defaults)
                        elif defaults.get('name'):
                            Customer.objects.update_or_create(name=defaults['name'], defaults=defaults)
                        success_count += 1
                    except Exception as e:
                        errors.append(f"Erro na linha {row}: {str(e)}")
            
            else:
                messages.error(request, 'Não foi possível identificar o tipo de dados (Produtos ou Clientes). Verifique os cabeçalhos.')
                return render(request, 'reports/import.html')

            if success_count > 0:
                messages.success(request, f'{success_count} registros de {model_name} processados com sucesso!')
            
            if errors:
                for err in errors[:3]: messages.warning(request, err)
                if len(errors) > 3: messages.warning(request, f'E mais {len(errors)-3} erros.')

        except Exception as e:
            messages.error(request, f'Erro ao processar arquivo: {str(e)}')

        return redirect('export_dashboard')

    # --- Lógica Fiscal: Listar Vendas Recentes ---
    recent_sales = Sale.objects.filter(status__in=['completed', 'pending']).select_related('customer').order_by('-created_at')[:10]

    return render(request, 'reports/import.html', {'sales': recent_sales})

@login_required
def download_fiscal(request, sale_id, doc_type):
    sale = get_object_or_404(Sale, pk=sale_id)
    
    # Busca dados da empresa
    try:
        company = CompanySettings.objects.first()
    except (OperationalError, ProgrammingError):
        company = None
    company_name = company.name if company else "Perfume ERP Ltda"
    company_cnpj = company.cnpj if company else "00.000.000/0001-91"
    
    if doc_type == 'cupom':
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="cupom_{sale.id}.pdf"'
        
        # Gera PDF estilo Cupom Térmico (80mm largura) - Layout Moderno
        width = 80*mm
        height = 250*mm # Altura maior para garantir que caibam os itens
        p = canvas.Canvas(response, pagesize=(width, height))
        
        # Coordenadas e Configurações
        y = 240*mm 
        left_x = 5*mm
        center_x = 40*mm
        right_x = 75*mm
        line_height = 4*mm
        
        # --- Cabeçalho da Empresa ---
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(center_x, y, company_name.upper())
        y -= line_height + 1*mm
        
        p.setFont("Helvetica", 8)
        p.drawCentredString(center_x, y, f"CNPJ: {company_cnpj}")
        y -= line_height
        
        if company:
            if company.address:
                p.drawCentredString(center_x, y, company.address[:45]) # Trunca para caber
                y -= line_height
            if company.phone:
                p.drawCentredString(center_x, y, f"Tel: {company.phone}")
                y -= line_height
        
        y -= 2*mm
        p.setLineWidth(0.5)
        p.line(left_x, y, right_x, y)
        y -= line_height + 2*mm
        
        # --- Dados da Venda ---
        p.setFont("Helvetica-Bold", 9)
        p.drawCentredString(center_x, y, "CUPOM NÃO FISCAL")
        y -= line_height
        
        p.setFont("Helvetica", 8)
        p.drawCentredString(center_x, y, f"Venda Nº {sale.id:06d}")
        y -= line_height
        p.drawCentredString(center_x, y, sale.created_at.strftime('%d/%m/%Y %H:%M:%S'))
        y -= line_height + 2*mm
        
        p.line(left_x, y, right_x, y)
        y -= line_height + 2*mm
        
        # --- Itens ---
        p.setFont("Helvetica-Bold", 8)
        p.drawString(left_x, y, "ITEM")
        p.drawRightString(right_x, y, "TOTAL")
        y -= line_height
        
        p.setFont("Helvetica", 8)
        for item in sale.items.all():
            # Nome do Produto
            name = item.product.name
            if len(name) > 30: name = name[:30] + "..."
            p.drawString(left_x, y, name)
            y -= line_height
            
            # Detalhes
            details = f"{item.quantity} x R$ {item.price:.2f}"
            total_item = item.quantity * item.price
            
            p.setFont("Helvetica", 7)
            p.drawString(left_x + 2*mm, y, details)
            p.drawRightString(right_x, y, f"R$ {total_item:.2f}")
            p.setFont("Helvetica", 8)
            y -= line_height + 1*mm
            
        y -= 2*mm
        p.line(left_x, y, right_x, y)
        y -= line_height + 2*mm
        
        # --- Totais ---
        p.setFont("Helvetica-Bold", 12)
        p.drawString(left_x, y, "TOTAL A PAGAR")
        p.drawRightString(right_x, y, f"R$ {sale.total:.2f}")
        y -= line_height + 4*mm
        
        p.setFont("Helvetica", 8)
        p.drawString(left_x, y, "Forma de Pagamento:")
        p.drawRightString(right_x, y, sale.get_payment_method_display())
        y -= line_height + 2*mm
        
        # --- Cliente ---
        if sale.customer:
            p.line(left_x, y, right_x, y)
            y -= line_height + 2*mm
            p.setFont("Helvetica-Bold", 8)
            p.drawString(left_x, y, "CLIENTE")
            y -= line_height
            p.setFont("Helvetica", 8)
            p.drawString(left_x, y, sale.customer.name[:35])
            y -= line_height
            if sale.customer.cpf_cnpj:
                p.drawString(left_x, y, f"CPF/CNPJ: {sale.customer.cpf_cnpj}")
                y -= line_height
        
        # --- Rodapé ---
        y -= 10*mm
        p.setFont("Helvetica-Oblique", 8)
        p.drawCentredString(center_x, y, "Obrigado pela preferência!")
        y -= line_height
        p.setFont("Helvetica", 6)
        p.drawCentredString(center_x, y, "Gerado por Perfume ERP")

        # --- QR Code ---
        y -= 5*mm
        qr_data = "https://www.seusite.com.br" # Substitua pelo seu site
        qr_code = qr.QrCodeWidget(qr_data)
        bounds = qr_code.getBounds()
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        d = Drawing(45, 45, transform=[45/width,0,0,45/height,0,0])
        d.add(qr_code)
        renderPDF.draw(d, p, center_x - 8*mm, y - 18*mm)

        p.showPage()
        p.save()
        return response

    elif doc_type == 'nfe':
        # Gera XML Simulado de NF-e
        response = HttpResponse(content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="nfe_{sale.id}.xml"'
        
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
    <NFe>
        <infNFe Id="NFe{sale.id}">
            <ide>
                <nNF>{sale.id}</nNF>
                <dhEmi>{sale.created_at.isoformat()}</dhEmi>
                <tpNF>1</tpNF>
                <natOp>Venda de Mercadoria</natOp>
            </ide>
            <emit>
                <xNome>{company_name}</xNome>
                <CNPJ>{company_cnpj}</CNPJ>
            </emit>
            <dest>
                <xNome>{sale.customer.name if sale.customer else 'Consumidor Final'}</xNome>
                <CPF>{sale.customer.cpf_cnpj if sale.customer and sale.customer.cpf_cnpj else ''}</CPF>
            </dest>
            <det nItem="1">
                <prod>
                    <xProd>Venda de Perfumes e Cosmeticos</xProd>
                    <vProd>{sale.total}</vProd>
                </prod>
            </det>
            <total>
                <ICMSTot>
                    <vNF>{sale.total}</vNF>
                </ICMSTot>
            </total>
        </infNFe>
    </NFe>
</nfeProc>"""
        response.write(xml_content)
        return response
        
    elif doc_type == 'danfe':
        # Gera PDF estilo DANFE (Simplificado A4)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="danfe_{sale.id}.pdf"'
        
        # Configuração A4 (210mm x 297mm)
        width, height = 210*mm, 297*mm
        p = canvas.Canvas(response, pagesize=(width, height))
        
        # --- Cabeçalho ---
        p.setLineWidth(1)
        p.rect(10*mm, height - 40*mm, 190*mm, 30*mm)
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(15*mm, height - 20*mm, "DANFE - Documento Auxiliar da Nota Fiscal Eletrônica")
        
        p.setFont("Helvetica", 10)
        p.drawString(15*mm, height - 25*mm, company_name)
        p.drawString(15*mm, height - 30*mm, f"CNPJ: {company_cnpj}")
        
        p.drawString(120*mm, height - 20*mm, f"Nº: {sale.id}")
        p.drawString(120*mm, height - 25*mm, "Série: 1")
        p.drawString(120*mm, height - 30*mm, f"Emissão: {sale.created_at.strftime('%d/%m/%Y')}")
        
        # --- Destinatário ---
        y = height - 50*mm
        p.rect(10*mm, y - 25*mm, 190*mm, 25*mm)
        p.setFont("Helvetica-Bold", 10)
        p.drawString(12*mm, y - 5*mm, "DESTINATÁRIO / REMETENTE")
        
        p.setFont("Helvetica", 9)
        customer_name = sale.customer.name if sale.customer else 'Consumidor Final'
        customer_doc = sale.customer.cpf_cnpj if sale.customer and sale.customer.cpf_cnpj else ''
        
        p.drawString(15*mm, y - 12*mm, f"Nome/Razão Social: {customer_name}")
        p.drawString(130*mm, y - 12*mm, f"CNPJ/CPF: {customer_doc}")
        
        # --- Itens ---
        y = height - 85*mm
        p.setFont("Helvetica-Bold", 9)
        p.drawString(10*mm, y, "DADOS DOS PRODUTOS / SERVIÇOS")
        y -= 5*mm
        p.line(10*mm, y, 200*mm, y)
        y -= 5*mm
        
        p.setFont("Helvetica", 9)
        for item in sale.items.all():
            line_text = f"{item.product.name[:50]} | Qtd: {item.quantity} | Unit: R$ {item.price:.2f} | Total: R$ {item.quantity * item.price:.2f}"
            p.drawString(12*mm, y, line_text)
            y -= 5*mm
            
        # --- Totais ---
        y -= 5*mm
        p.line(10*mm, y, 200*mm, y)
        y -= 8*mm
        p.setFont("Helvetica-Bold", 11)
        p.drawString(140*mm, y, f"VALOR TOTAL: R$ {sale.total:.2f}")
        
        p.showPage()
        p.save()
        return response

    return redirect('import_data')

@login_required
def download_db_backup(request):
    db_settings = settings.DATABASES['default']
    
    # Verifica se é SQLite
    if db_settings['ENGINE'] != 'django.db.backends.sqlite3':
        return JsonResponse({'status': 'error', 'message': 'Backup automático disponível apenas para SQLite'})
        
    db_path = db_settings['NAME']
    if os.path.exists(db_path):
        with open(db_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/x-sqlite3")
            response['Content-Disposition'] = 'attachment; filename="backup_db.sqlite3"'
            return response
            
    return JsonResponse({'status': 'error', 'message': 'Arquivo do banco de dados não encontrado'})

@login_required
def pending_sales(request):
    sales = Sale.objects.filter(status='pending').select_related('customer').prefetch_related('items__product', 'transactions').order_by('-created_at')
    
    for sale in sales:
        # Calcula o total já pago somando as transações de receita vinculadas à venda
        paid = sum(t.value for t in sale.transactions.all() if t.transaction_type == 'income')
        sale.amount_paid = paid
        sale.remaining = sale.total - paid
        
    return render(request, 'reports/pending_sales.html', {'sales': sales})

@login_required
def finalize_sale(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    if sale.status == 'pending':
        with transaction.atomic():
            sale.status = 'completed'
            sale.save()
            # Estoque já foi baixado na criação da venda pendente via StockMovement
            sale.finalize() # Gera registro de movimentação
            messages.success(request, f'Venda #{sale.id} efetivada com sucesso! Estoque atualizado.')
    return redirect('pending_sales')

@login_required
def delete_sale(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    if sale.status == 'pending':
        # Devolve os itens ao estoque antes de excluir
        for item in sale.items.all():
            StockMovement.objects.create(
                product=item.product,
                quantity=item.quantity,
                movement_type='E',
                reason=f'Cancelamento Venda Pendente #{sale.id}'
            )
        sale.delete()
        messages.success(request, f'Orçamento #{sale.id} excluído.')
    return redirect('pending_sales')

@login_required
def register_payment(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    if request.method == 'POST':
        try:
            amount_str = request.POST.get('amount', '0').replace(',', '.')
            amount = Decimal(amount_str)
            payment_method = request.POST.get('payment_method', 'cash')
            
            if amount > 0:
                Transaction.objects.create(
                    description=f"Pagamento Venda #{sale.id}",
                    transaction_type='income',
                    value=amount,
                    due_date=date.today(),
                    payment_date=date.today(),
                    status='paid',
                    sale=sale
                )
                messages.success(request, f'Pagamento de R$ {amount:.2f} registrado com sucesso.')
            else:
                messages.warning(request, 'Valor inválido.')
        except Exception as e:
            messages.error(request, f'Erro ao registrar pagamento: {str(e)}')
            
    return redirect('pending_sales')