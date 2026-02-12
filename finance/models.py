from django.db import models
from sales.models import Sale

class Transaction(models.Model):
    TYPE_CHOICES = [
        ('income', 'Receita'),
        ('expense', 'Despesa'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('paid', 'Pago'),
        ('overdue', 'Atrasado'),
    ]

    description = models.CharField("Descrição", max_length=255)
    transaction_type = models.CharField("Tipo", max_length=10, choices=TYPE_CHOICES)
    value = models.DecimalField("Valor", max_digits=10, decimal_places=2)
    due_date = models.DateField("Data de Vencimento")
    payment_date = models.DateField("Data de Pagamento", null=True, blank=True)
    status = models.CharField("Status", max_length=10, choices=STATUS_CHOICES, default='pending')
    
    # Vínculo opcional com uma venda (para rastreabilidade)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.description} ({self.value})"

    class Meta:
        verbose_name = "Lançamento Financeiro"
        verbose_name_plural = "Lançamentos Financeiros"
        ordering = ['due_date']