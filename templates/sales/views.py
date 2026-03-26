from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from .models import Expense

@login_required
def expense_list(request):
    """Lista despesas e permite adicionar novas"""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            Expense.objects.create(
                description=request.POST.get('description'),
                category=request.POST.get('category'),
                amount=request.POST.get('amount').replace('.', '').replace(',', '.'), # Formata moeda BR
                date=request.POST.get('date'),
                paid=request.POST.get('paid') == 'on'
            )
            messages.success(request, 'Despesa lançada com sucesso!')
            
        elif action == 'delete':
            pk = request.POST.get('expense_id')
            Expense.objects.filter(pk=pk).delete()
            messages.success(request, 'Despesa removida.')
            
        return redirect('expense_list')

    expenses = Expense.objects.all().order_by('-date')
    total = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    
    return render(request, 'finance/expense_list.html', {'expenses': expenses, 'total': total})