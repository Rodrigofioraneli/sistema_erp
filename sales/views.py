import json
import unicodedata
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from decimal import Decimal
from .models import Sale, SaleItem
from products.models import Product, StockMovement
from customers.models import Customer

def normalize_str(s):
    """Remove acentos e coloca em minúsculo para busca robusta"""
    if s is None: return ''
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn').lower()

@login_required
def pos_view(request):
    """Renderiza a tela de Ponto de Venda (PDV)"""
    return render(request, 'sales/pos.html')

@login_required
def product_search_api(request):
    """API para buscar produtos pelo nome ou código de barras"""
    query = request.GET.get('q', '')
    query_norm = normalize_str(query)
    
    # Busca Python-side para suportar acentos (SQLite não tem unaccent nativo)
    all_products = Product.objects.prefetch_related('components__component').all()
    products = []
    for p in all_products:
        if query_norm in normalize_str(p.name) or (p.barcode and query_norm in normalize_str(p.barcode)):
            products.append(p)
            if len(products) >= 20: break
    
    results = []
    for p in products:
        components_list = []
        if p.product_type in ['kit', 'combo']:
            for comp in p.components.all():
                qty = int(comp.quantity) if comp.quantity % 1 == 0 else float(comp.quantity)
                components_list.append(f"{qty}x {comp.component.name}")

        results.append({
            'id': p.id,
            'name': p.name,
            'price': float(p.selling_price),
            'image': p.image.url if p.image else (p.image_url if p.image_url else ''),
            'stock': p.stock_quantity,
            'volume': p.volume,
            'components': components_list
        })
    return JsonResponse(results, safe=False)

@login_required
def customer_search_api(request):
    """API para buscar clientes pelo nome ou CPF"""
    query = request.GET.get('q', '')
    query_norm = normalize_str(query)
    
    all_customers = Customer.objects.all()
    customers = []
    for c in all_customers:
        if query_norm in normalize_str(c.name) or (c.cpf_cnpj and query_norm in normalize_str(c.cpf_cnpj)):
            customers.append(c)
            if len(customers) >= 10: break
    
    results = []
    for c in customers:
        results.append({'id': c.id, 'name': c.name, 'cpf': c.cpf_cnpj})
            
    return JsonResponse(results, safe=False)

@login_required
def save_sale(request):
    """API para salvar a venda enviada pelo Javascript"""
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            with transaction.atomic():
                # Helper para converter valores monetários com segurança
                def to_decimal(val):
                    if not val: return Decimal('0')
                    return Decimal(str(val).replace(',', '.'))

                # Lógica para Cliente: ID ou Nome Avulso (Sem Cadastro Prévio)
                customer_id = data.get('customer_id')
                customer_name = data.get('customer_name')
                customer_obj = None

                if customer_id:
                    customer_obj = Customer.objects.get(pk=customer_id)
                elif customer_name:
                    # Cria um cliente rápido apenas com o nome se não existir
                    customer_obj, _ = Customer.objects.get_or_create(
                        name=customer_name.strip(),
                        defaults={'cpf_cnpj': None, 'email': '', 'phone': ''}
                    )

                sale = Sale.objects.create(
                    salesperson=request.user,
                    customer=customer_obj,
                    payment_method=data.get('payment_method'),
                    installments=data.get('installments', 1),
                    discount_value=to_decimal(data.get('discount_value')),
                    discount_type=data.get('discount_type', 'fixed'),
                    tax_value=to_decimal(data.get('tax_value')),
                    tax_type=data.get('tax_type', 'fixed'),
                    status=data.get('status', 'pending')
                )
                
                items = data.get('items', [])
                for item in items:
                    SaleItem.objects.create(
                        sale=sale,
                        product_id=item['id'],
                        quantity=item['quantity'],
                        price=to_decimal(item['price'])
                    )
                    
                sale.save() # Recalcula totais e comissão
                
                if sale.status == 'completed':
                    sale.finalize() # Baixa o estoque apenas se finalizada
                elif sale.status == 'pending':
                    # Para vendas pendentes, baixamos o estoque imediatamente (reserva) ou componentes
                    for item in items:
                        product = Product.objects.get(pk=item['id'])
                        
                        # Verifica se é Kit para baixar componentes
                        if product.product_type == 'kit' or product.product_type == 'combo':
                            components = product.components.all()
                            if components.exists():
                                for comp in components:
                                    StockMovement.objects.create(
                                        product=comp.component,
                                        quantity=comp.quantity * item['quantity'],
                                        movement_type='S',
                                        reason=f'Venda Kit Pendente #{sale.id} ({product.name})'
                                    )
                                continue # Pula a baixa do produto pai se tiver componentes
                        
                        # Baixa normal se não for kit ou kit vazio
                        StockMovement.objects.create(
                            product=product,
                            quantity=item['quantity'],
                            movement_type='S',
                            reason=f'Venda Pendente #{sale.id}'
                        )
                
                return JsonResponse({'status': 'success', 'sale_id': sale.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=400)