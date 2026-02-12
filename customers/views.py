from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .forms import CustomerForm
from .models import Customer, FragranceFamily
import unicodedata

def normalize_str(s):
    """Remove acentos e coloca em minúsculo"""
    if s is None: return ''
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn').lower()

def get_common_context(request):
    """Helper para carregar a lista de clientes de forma eficiente."""
    # Lógica de Busca e Listagem
    search_query = request.GET.get('q', '')
    customers = Customer.objects.all()

    if search_query:
        # Filtra diretamente no banco de dados, que é muito mais rápido.
        # __icontains é case-insensitive (ignora maiúsculas/minúsculas).
        customers = customers.filter(
            Q(name__icontains=search_query) | Q(cpf_cnpj__icontains=search_query)
        )
    return customers.order_by('-created_at')

@login_required
def customer_list(request):
    customers = get_common_context(request)
    context = {
        'customers': customers,
        'search_query': request.GET.get('q', '')
    }
    return render(request, 'customers/list.html', context)

@login_required
def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente cadastrado com sucesso! 🎉')
            return redirect('customer_list')
    else:
        form = CustomerForm()
    
    return render(request, 'customers/customer_form.html', {'form': form})

@login_required
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente atualizado com sucesso! 🎉')
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'customers/customer_form.html', {'form': form})

@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerForm(instance=customer, readonly=True)
    return render(request, 'customers/customer_form.html', {'form': form, 'readonly': True})

@login_required
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        customer.delete()
        messages.success(request, 'Cliente excluído com sucesso! 🗑️')
    return redirect('customer_list')
