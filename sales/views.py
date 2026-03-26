# Importações de bibliotecas padrão e do Django
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
    """
    Função Auxiliar: Remove acentos e caracteres especiais de um texto.
    Exemplo: 'João' vira 'joao'. Útil para buscas no banco de dados.
    """
    if s is None: return ''
    # Normaliza (separa acento da letra) e filtra apenas o que não é marca de acento ('Mn')
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn').lower()

@login_required
def pos_view(request):
    """
    View Principal: Renderiza (mostra) a tela de Ponto de Venda (PDV).
    @login_required garante que só usuários logados acessem.
    """
    return render(request, 'sales/pos.html')

@login_required
def product_search_api(request):
    """
    API de Busca de Produtos: Otimizada para o PDV.
    Utiliza normalização para permitir que 'Perfume' e 'perfume' ou 'Joao' e 'João' coincidam.
    Usada pelo Javascript do PDV para preencher a lista de pesquisa.
    """
    # Pega o termo digitado na URL (?q=perfume)
    query = request.GET.get('q', '')

    # Otimização Profissional: Deixamos o Banco de Dados (SQL) fazer o trabalho pesado.
    # O uso de Q objects com icontains é significativamente mais rápido que loops em Python.
    products = Product.objects.select_related('brand').prefetch_related('components__component').filter(
        Q(name__icontains=query) | 
        Q(barcode__icontains=query) |
        Q(brand__name__icontains=query)
    )[:20]
    
    results = []
    for p in products:
        components_list = []
        # Lógica especial para Kits: Monta a lista de itens que compõem o kit
        if p.product_type in ['kit', 'combo']:
            for comp in p.components.all():
                # Formata quantidade (tira .0 se for inteiro)
                qty = int(comp.quantity) if comp.quantity % 1 == 0 else float(comp.quantity)
                components_list.append(f"{qty}x {comp.component.name}")

        # Monta o dicionário de dados para enviar ao Frontend
        results.append({
            'id': p.id,
            # Adiciona alerta visual se estiver sem estoque (exceto Kits que são virtuais)
            'name': p.name + (" (ESGOTADO ⚠️)" if p.stock_quantity <= 0 and p.product_type not in ['kit', 'combo'] else ""),
            'price': float(p.selling_price),
            'cost_price': float(p.cost_price),
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
    """
    API Principal de Venda: Recebe o carrinho completo via JSON, 
    valida estoque, salva no banco e gera movimentações.
    """
    if request.method == 'POST':
        # Lê os dados enviados pelo Javascript
        # O formato esperado é um JSON contendo itens, cliente, pagamento e descontos.
        data = json.loads(request.body)
        try:
            # transaction.atomic() garante que tudo seja salvo ou nada seja salvo (evita venda pela metade)
            with transaction.atomic():
                # Helper para converter valores monetários com segurança
                def to_decimal(val):
                    if not val: return Decimal('0')
                    # Remove R$ e espaços, troca vírgula por ponto
                    clean_val = str(val).replace('R$', '').replace(' ', '').replace(',', '.')
                    try:
                        return Decimal(clean_val)
                    except:
                        return Decimal('0')

                # Lógica para Cliente: ID ou Nome Avulso (Sem Cadastro Prévio)
                customer_id = data.get('customer_id')
                customer_name = data.get('customer_name')
                customer_obj = None

                if customer_id:
                    # Busca cliente existente
                    customer_obj = Customer.objects.get(pk=customer_id)
                elif customer_name:
                    # Se digitou um nome novo, cria um cadastro rápido automaticamente
                    customer_obj, _ = Customer.objects.get_or_create(
                        name=customer_name.strip(),
                        # Define valores padrão para campos obrigatórios
                        defaults={'cpf_cnpj': None, 'email': '', 'phone': ''}
                    )

                # Validação de Estoque (Impede a venda se não houver saldo)
                items_check = data.get('items', [])
                for item in items_check:
                    # TRAVA DE BANCO (Lock): select_for_update bloqueia esse registro
                    # enquanto esta venda está sendo processada, evitando venda duplicada do mesmo item.
                    prod_check = Product.objects.select_for_update().get(pk=item['id'])
                    
                    # Se não for kit e estoque for menor que o pedido, lança erro
                    if prod_check.product_type not in ['kit', 'combo'] and prod_check.stock_quantity < item['quantity']:
                        raise Exception(f"Produto '{prod_check.name}' insuficiente! Estoque atual: {prod_check.stock_quantity}")

                # --- Validação de Regras de Pagamento ---
                payment_method = data.get('payment_method')
                installments = int(data.get('installments') or 1)
                status = data.get('status', 'pending')

                # 1. Parcelamento permitido apenas no cartão
                # Regra de negócio: Dinheiro e PIX são apenas à vista para evitar problemas de conciliação.
                if installments > 1 and payment_method not in ['credit', 'debit']:
                    raise Exception("Vendas parceladas são permitidas apenas para pagamentos via Cartão (Crédito/Débito).")
                
                # 2. Pendências permitidas apenas no cartão
                # Garante que 'fiados' ou orçamentos tenham uma garantia de método de pagamento.
                if status == 'pending' and payment_method not in ['credit', 'debit']:
                    raise Exception("Vendas com status 'Pendente' exigem a seleção de Cartão como forma de pagamento.")

                # Cria o objeto Venda (Cabeçalho)
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
                
                # Cria os Itens da Venda
                items = data.get('items', [])
                for item in items:
                    SaleItem.objects.create(
                        sale=sale,
                        product_id=item['id'],
                        quantity=item['quantity'],
                        price=to_decimal(item['price'])
                    )
                    
                sale.save() # Chama o método .save() do modelo para recalcular totais
                
                if sale.status == 'completed':
                    # Se a venda foi finalizada, chama a função que dá baixa no estoque
                    if hasattr(sale, 'finalize'):
                        sale.finalize()
                elif sale.status == 'pending':
                    # Lógica para Venda Pendente (Reserva de Estoque)
                    for item in items:
                        product = Product.objects.get(pk=item['id'])
                        
                        # Se for Kit, precisa baixar os componentes internos
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
                                continue # Pula, pois o produto 'Kit' não tem estoque físico próprio
                        
                        # Baixa normal de produto simples
                        StockMovement.objects.create(
                            product=product,
                            quantity=item['quantity'],
                            movement_type='S',
                            reason=f'Venda Pendente #{sale.id}'
                        )
                
                # Retorna sucesso para o Javascript
                return JsonResponse({'status': 'success', 'sale_id': sale.id})
        except Exception as e:
            # Em caso de erro, retorna mensagem e status 400 (Bad Request)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=400)