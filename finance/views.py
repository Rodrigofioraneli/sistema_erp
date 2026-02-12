from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from .models import Transaction
from .forms import TransactionForm
from sales.models import Sale, SaleItem

def finance_dashboard(request):
    today = timezone.now().date()
    
    # Totais Gerais (Considerando apenas o que foi PAGO)
    total_income = Transaction.objects.filter(transaction_type='income', status='paid').aggregate(Sum('value'))['value__sum'] or 0
    total_expense = Transaction.objects.filter(transaction_type='expense', status='paid').aggregate(Sum('value'))['value__sum'] or 0
    balance = total_income - total_expense
    
    # Listas Operacionais
    payables = Transaction.objects.filter(transaction_type='expense', status='pending').order_by('due_date')
    receivables = Transaction.objects.filter(transaction_type='income', status='pending').order_by('due_date')
    
    # Inadimplência (Receitas pendentes vencidas)
    overdue = Transaction.objects.filter(transaction_type='income', status='pending', due_date__lt=today)
    
    return render(request, 'finance/dashboard.html', {
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'payables': payables,
        'receivables': receivables,
        'overdue': overdue,
    })

def transaction_create(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('finance_dashboard')
    else:
        form = TransactionForm()
    return render(request, 'finance/transaction_form.html', {'form': form})

def transaction_edit(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            return redirect('finance_dashboard')
    else:
        form = TransactionForm(instance=transaction)
    return render(request, 'finance/transaction_form.html', {'form': form})

def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    if request.method == 'POST':
        transaction.delete()
    return redirect('finance_dashboard')

def financial_reports(request):
    # 1. Ticket Médio
    sales_completed = Sale.objects.filter(status='completed')
    sales_count = sales_completed.count()
    sales_total = sales_completed.aggregate(Sum('total'))['total__sum'] or 0
    avg_ticket = sales_total / sales_count if sales_count > 0 else 0
    
    # 2. Lucro por Produto e Marca
    # Iteramos sobre os itens vendidos para calcular (Preço Venda - Preço Custo)
    items = SaleItem.objects.filter(sale__status='completed').select_related('product', 'product__brand')
    
    product_profit = {}
    brand_profit = {}
    
    for item in items:
        cost = item.product.cost_price
        revenue = item.price
        profit = (revenue - cost) * item.quantity
        
        # Agrupa por Produto
        prod_name = item.product.name
        product_profit[prod_name] = product_profit.get(prod_name, 0) + profit
        
        # Agrupa por Marca
        brand_name = item.product.brand.name if item.product.brand else "Sem Marca"
        brand_profit[brand_name] = brand_profit.get(brand_name, 0) + profit
            
    # Ordenar Top 10
    top_products = sorted(product_profit.items(), key=lambda x: x[1], reverse=True)[:10]
    top_brands = sorted(brand_profit.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return render(request, 'finance/reports.html', {
        'avg_ticket': avg_ticket,
        'top_products': top_products,
        'top_brands': top_brands
    })