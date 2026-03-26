from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db.models import Q, F
from .forms import ProductForm, StockMovementForm
from .models import Product, OlfactoryFamily, Brand, StockMovement, ProductComponent
from datetime import date, timedelta
import unicodedata
from sales.decorators import admin_required

def normalize_str(s):
    if s is None: return ''
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn').lower()

def get_common_context(request):
    # Garante famílias olfativas padrão
    if not OlfactoryFamily.objects.exists():
        for name in ['Floral', 'Amadeirado', 'Oriental', 'Cítrico', 'Fougère', 'Chipre', 'Gourmand']:
            OlfactoryFamily.objects.create(name=name)
            
    # Garante uma marca de teste
    if not Brand.objects.exists():
        Brand.objects.create(name='Marca Genérica')

    search_query = request.GET.get('q', '')
    if search_query:
        products = Product.objects.select_related('brand').filter(
            Q(name__icontains=search_query) |
            Q(brand__name__icontains=search_query) |
            Q(barcode__icontains=search_query)
        ).order_by('name')
    else:
        products = Product.objects.all().select_related('brand').order_by('-created_at')
    return products

@login_required
def product_list(request):
    q = request.GET.get('q', '')
    # Otimização: Buscamos apenas o que é necessário.
    # Usamos o banco para filtrar, o que é muito mais rápido que filtrar em Python.
    queryset = Product.objects.select_related('brand').all()

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) | 
            Q(barcode__icontains=q) | 
            Q(brand__name__icontains=q)
        ).order_by('name')
    else:
        queryset = queryset.order_by('name')
    
    context = {
        'products': queryset,
        'search_query': q
    }
    return render(request, 'products/list.html', context)

def product_create(request):
    products = get_common_context(request)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Produto cadastrado com sucesso! 🧴')
            return redirect('product_create')
    else:
        form = ProductForm()
    
    return render(request, 'products/product_form.html', {'form': form, 'products': products})

def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    products = get_common_context(request)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Produto atualizado com sucesso! ✨')
            return redirect('product_create')
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'products/product_form.html', {'form': form, 'products': products})

def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    products = get_common_context(request)
    form = ProductForm(instance=product, readonly=True)
    return render(request, 'products/product_form.html', {'form': form, 'products': products, 'readonly': True})

@admin_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.success(request, 'Produto excluído com sucesso! 🗑️')
    return redirect('product_create')

@login_required
def stock_purchase(request):
    """
    Gestão de Entradas: Focada em compras de fornecedores.
    O diferencial técnico aqui é a atualização automática do custo médio do produto.
    Calcula automaticamente o preço médio.
    """
    # Verifica se veio um ID de produto da lista (atalho)
    product_id = request.GET.get('product_id')
    initial_data = {'movement_type': 'E'}
    selected_product = None

    if product_id:
        product = get_object_or_404(Product, pk=product_id)
        initial_data['product'] = product.pk
        initial_data['entry_cost'] = product.cost_price # Sugere o custo atual
        selected_product = product

    if request.method == 'POST':
        form = StockMovementForm(request.POST)
        if form.is_valid():
            movement = form.save(commit=False)
            movement.movement_type = 'E' # Força Entrada
            if not movement.reason:
                movement.reason = "Compra / Entrada de Estoque"
            
            # Lógica de Gatilho (Trigger): O cálculo de Preço Médio e atualização de saldo
            # está encapsulado no Model. Isso é uma excelente prática (Fat Models, Thin Views).
            movement.save() 
            
            product = movement.product
            product.refresh_from_db() # Recarrega o produto para mostrar os valores atualizados
            
            messages.success(request, f'Entrada de {movement.quantity} un. registrada! Estoque atual: {product.stock_quantity}. Novo custo médio: R$ {product.cost_price:.2f}')
            return redirect('stock_purchase')
    else:
        form = StockMovementForm(initial=initial_data)

    return render(request, 'products/stock_purchase.html', {
        'form': form, 
        'selected_product': selected_product
    })

def stock_manage(request):
    # Histórico de Movimentações (últimas 50)
    movements = StockMovement.objects.all().select_related('product').order_by('-created_at')[:50]
    
    # Alertas
    # 1. Estoque Baixo (Quantidade <= Estoque Mínimo)
    low_stock = Product.objects.filter(stock_quantity__lte=F('min_stock'))
    
    # 2. Validade Próxima (Vence nos próximos 30 dias ou já venceu)
    today = date.today()
    expiring = Product.objects.filter(expiration_date__lte=today + timedelta(days=30))

    if request.method == 'POST':
        form = StockMovementForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Movimentação registrada com sucesso! 📉📈')
            return redirect('stock_manage')
    else:
        form = StockMovementForm()
    
    return render(request, 'products/stock_manage.html', {
        'form': form, 
        'movements': movements,
        'low_stock': low_stock,
        'expiring': expiring
    })

@login_required
def kit_manage(request):
    """
    Lógica de Kits: Kits não possuem estoque físico próprio, mas sim 'virtual'.
    A baixa de estoque ocorre nos componentes individuais no momento da venda.
    """
    if request.method == 'POST' and 'kit_action' in request.POST:
        action = request.POST.get('kit_action')
        
        if action == 'create_kit':
            kit_name = request.POST.get('kit_name')
            kit_price = request.POST.get('kit_price', '0').replace(',', '.')
            if kit_name:
                # Cria um produto do tipo KIT
                Product.objects.create(
                    name=kit_name,
                    selling_price=kit_price,
                    product_type='kit',
                    stock_quantity=0, # Estoque virtual
                    min_stock=0
                )
                messages.success(request, f'Kit "{kit_name}" criado! Agora adicione os produtos.')

        elif action == 'add_component':
            kit_id = request.POST.get('kit_id')
            component_id = request.POST.get('component_id')
            qty = request.POST.get('quantity', 1)
            
            if kit_id and component_id:
                ProductComponent.objects.get_or_create(
                    kit_id=kit_id,
                    component_id=component_id,
                    defaults={'quantity': qty}
                )
                messages.success(request, 'Produto adicionado ao Kit!')
                return redirect(f"{reverse('kit_manage')}?editing_kit={kit_id}")

        elif action == 'remove_component':
            comp_id = request.POST.get('component_pk')
            ProductComponent.objects.filter(pk=comp_id).delete()
            messages.success(request, 'Produto removido do Kit.')
            
        elif action == 'update_kit':
            kit_id = request.POST.get('kit_id')
            kit_name = request.POST.get('kit_name')
            kit_price = request.POST.get('kit_price', '0').replace(',', '.')
            
            kit = get_object_or_404(Product, pk=kit_id, product_type='kit')
            kit.name = kit_name
            kit.selling_price = kit_price
            kit.save()
            messages.success(request, 'Dados do Kit atualizados!')

        elif action == 'delete_kit':
            kit_id = request.POST.get('kit_id')
            Product.objects.filter(pk=kit_id, product_type='kit').delete()
            messages.success(request, 'Kit excluído com sucesso!')
            return redirect('kit_manage')
            
        return redirect('kit_manage')

    kits = Product.objects.filter(product_type='kit').prefetch_related('components__component')
    all_products = Product.objects.exclude(product_type='kit').select_related('brand').order_by('name')

    # Verifica se há um kit sendo editado no momento
    editing_kit_id = request.GET.get('editing_kit')
    active_kit = None
    if editing_kit_id:
        active_kit = Product.objects.filter(pk=editing_kit_id).first()

    # Lógica de Busca (Igual ao cadastro de produtos)
    q = request.GET.get('q', '')
    products_search = []
    
    if q:
        # Otimização: Removemos o loop 'for p in all_products' que consome muita RAM.
        # O filtro abaixo é executado diretamente no SQL.
        products_search = Product.objects.exclude(product_type='kit').filter(
            Q(name__icontains=q) | 
            Q(barcode__icontains=q)
        ).select_related('brand').order_by('name')[:15]
    elif active_kit:
        # Se estiver editando um kit, mostra mais produtos para facilitar
        products_search = Product.objects.exclude(product_type='kit').select_related('brand').order_by('-created_at')[:10]
    else:
        # Mostra os 5 últimos cadastrados por padrão
        products_search = Product.objects.exclude(product_type='kit').select_related('brand').order_by('-created_at')[:5]

    return render(request, 'products/kit_manage.html', {
        'kits': kits,
        'all_products': all_products,
        'products_search': products_search,
        'search_query': q,
        'active_kit': active_kit
    })