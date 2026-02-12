from django.db import models
from django.contrib.auth.models import User
from customers.models import Customer
from products.models import Product, StockMovement
from decimal import Decimal

class Sale(models.Model):
    PAYMENT_CHOICES = [
        ('pix', 'PIX'),
        ('credit', 'Cartão de Crédito'),
        ('debit', 'Cartão de Débito'),
        ('cash', 'Dinheiro'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('completed', 'Finalizada'),
        ('canceled', 'Cancelada'),
    ]

    CALC_TYPE_CHOICES = [
        ('fixed', 'R$'),
        ('percent', '%'),
    ]

    salesperson = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vendedor")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Cliente")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data")
    payment_method = models.CharField("Pagamento", max_length=20, choices=PAYMENT_CHOICES, default='pix')
    installments = models.IntegerField("Parcelas", default=1)
    
    discount_value = models.DecimalField("Desconto", max_digits=10, decimal_places=2, default=0)
    discount_type = models.CharField("Tipo Desconto", max_length=10, choices=CALC_TYPE_CHOICES, default='fixed')
    tax_value = models.DecimalField("Acréscimo", max_digits=10, decimal_places=2, default=0)
    tax_type = models.CharField("Tipo Acréscimo", max_length=10, choices=CALC_TYPE_CHOICES, default='fixed')
    
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pending')
    commission = models.DecimalField("Comissão", max_digits=10, decimal_places=2, default=0, editable=False)

    def __str__(self):
        return f"Venda #{self.pk} - {self.created_at.strftime('%d/%m/%Y')}"

    def save(self, *args, **kwargs):
        # Recalcula o total se a venda já existir
        if self.pk:
            subtotal_items = sum(item.subtotal for item in self.items.all())
            
            # Cálculo do Desconto
            discount_amount = self.discount_value
            if self.discount_type == 'percent':
                discount_amount = subtotal_items * (self.discount_value / 100)
            
            # Cálculo do Acréscimo (Taxa)
            tax_amount = self.tax_value
            if self.tax_type == 'percent':
                tax_amount = subtotal_items * (self.tax_value / 100)

            self.total = subtotal_items - discount_amount + tax_amount
            if self.total < 0: self.total = 0
            
            # Cálculo de comissão (Ex: 5% sobre o total)
            self.commission = self.total * Decimal('0.05')
            
        super().save(*args, **kwargs)

    def finalize(self):
        """Finaliza a venda e gera a saída no estoque automaticamente"""
        if self.status == 'completed':
            # Verifica se já existem movimentações para evitar duplicidade
            if not StockMovement.objects.filter(reason=f"Venda #{self.pk}").exists():
                for item in self.items.all():
                    StockMovement.objects.create(
                        product=item.product,
                        quantity=item.quantity,
                        movement_type='S',
                        reason=f"Venda #{self.pk}"
                    )

    class Meta:
        verbose_name = "Venda"
        verbose_name_plural = "Vendas"

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="Produto")
    quantity = models.PositiveIntegerField("Qtd", default=1)
    price = models.DecimalField("Preço Unit.", max_digits=10, decimal_places=2, editable=False)
    subtotal = models.DecimalField("Subtotal", max_digits=10, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        # Pega o preço atual do produto automaticamente
        if not self.price:
            self.price = self.product.selling_price
        
        self.subtotal = self.price * self.quantity
        super().save(*args, **kwargs)
        self.sale.save() # Atualiza o total da venda pai

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"