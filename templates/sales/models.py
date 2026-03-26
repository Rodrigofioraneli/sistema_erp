from django.db import models
from django.utils import timezone

class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('fixed', 'Despesa Fixa (Água, Luz, Aluguel)'),
        ('purchase', 'Compra de Mercadoria/Estoque'),
        ('personnel', 'Pessoal / Salários'),
        ('marketing', 'Marketing / Anúncios'),
        ('taxes', 'Impostos / Taxas'),
        ('other', 'Outros'),
    ]

    description = models.CharField("Descrição", max_length=200, help_text="Ex: Conta de Luz Março")
    category = models.CharField("Categoria", max_length=20, choices=CATEGORY_CHOICES, default='other')
    amount = models.DecimalField("Valor (R$)", max_digits=10, decimal_places=2)
    date = models.DateField("Data do Pagamento", default=timezone.now)
    paid = models.BooleanField("Pago?", default=True)
    
    def __str__(self):
        return f"{self.description} - R$ {self.amount}"

    class Meta:
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"