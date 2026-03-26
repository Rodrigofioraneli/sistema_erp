from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from customers.models import Customer
from products.models import Product, StockMovement
from decimal import Decimal
import json
from django.forms.models import model_to_dict
from datetime import datetime, date

# Helper para serializar datas e decimais para JSON
class AuditEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Criação'),
        ('UPDATE', 'Alteração'),
        ('DELETE', 'Exclusão'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Usuário")
    model_name = models.CharField("Módulo", max_length=50)
    object_id = models.CharField("ID Objeto", max_length=50)
    object_repr = models.CharField("Descrição", max_length=255)
    action = models.CharField("Ação", max_length=10, choices=ACTION_CHOICES)
    changes = models.TextField("Alterações", blank=True)
    timestamp = models.DateTimeField("Data/Hora", auto_now_add=True)

    class Meta:
        verbose_name = "Log de Auditoria"
        verbose_name_plural = "Logs de Auditoria"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.action} - {self.model_name}"

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
    amount_paid = models.DecimalField("Valor Pago", max_digits=10, decimal_places=2, default=0)
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
            if self.total < Decimal('0'): self.total = Decimal('0')
            
            # Cálculo de comissão (Ex: 5% sobre o total)
            self.commission = self.total * Decimal('0.05')
            
        super().save(*args, **kwargs)

    def finalize(self):
        """Finaliza a venda e gera a saída no estoque automaticamente"""
        if self.status == 'completed':
            # Verifica se já existem movimentações (seja Finalizada ou Pendente) para evitar duplicidade
            # Isso evita que o estoque seja baixado duas vezes se a venda veio de "Pendente"
            # Alterado para contains para pegar também 'Venda Kit Pendente...' e variações
            already_deducted = StockMovement.objects.filter(
                reason__contains=f"#{self.pk}"
            ).exists()
            
            if not already_deducted:
                for item in self.items.all():
                    # Verifica se é Kit/Combo para baixar os componentes
                    if item.product.product_type in ['kit', 'combo']:
                        components = item.product.components.all()
                        if components.exists():
                            for comp in components:
                                StockMovement.objects.create(
                                    product=comp.component,
                                    quantity=comp.quantity * item.quantity,
                                    movement_type='S',
                                    reason=f"Venda Kit #{self.pk} ({item.product.name})"
                                )
                    else:
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
    price = models.DecimalField("Preço Unit.", max_digits=10, decimal_places=2)
    subtotal = models.DecimalField("Subtotal", max_digits=10, decimal_places=2, editable=False)

    def save(self, *args, update_sale_total=True, **kwargs):
        # Pega o preço de venda do produto apenas na criação do item,
        # se nenhum preço for fornecido explicitamente.
        if not self.pk and self.price is None:
            self.price = self.product.selling_price
        
        self.subtotal = self.price * self.quantity
        super().save(*args, **kwargs)
        if update_sale_total:
            self.sale.save() # Atualiza o total da venda pai

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

    def delete(self, *args, **kwargs):
        sale = self.sale
        super().delete(*args, **kwargs)
        # Garante que o total da venda seja recalculado após a exclusão de um item
        sale.save()

# --- SINAIS PARA LOG AUTOMÁTICO ---
from config.middleware import get_current_user

@receiver(pre_save, sender=Sale)
@receiver(pre_save, sender=Product)
@receiver(pre_save, sender=Customer)
def audit_log_pre_save(sender, instance, **kwargs):
    """Captura o estado original do objeto antes de salvar para comparação"""
    if instance.pk:
        try:
            old_obj = sender.objects.get(pk=instance.pk)
            instance._old_state = model_to_dict(old_obj)
        except sender.DoesNotExist:
            instance._old_state = {}

@receiver(post_save, sender=Sale)
@receiver(post_save, sender=Product)
@receiver(post_save, sender=Customer)
def audit_log_save(sender, instance, created, **kwargs):
    user = get_current_user()
    if not user or not user.is_authenticated:
        return # Ignora ações do sistema sem usuário logado

    action = 'CREATE' if created else 'UPDATE'
    model_name = sender._meta.verbose_name.title()
    
    changes_desc = ""
    if action == 'UPDATE' and hasattr(instance, '_old_state'):
        new_state = model_to_dict(instance)
        diffs = []
        for field, new_val in new_state.items():
            old_val = instance._old_state.get(field)
            # Compara convertendo para string para evitar erros entre tipos (ex: Decimal vs Float)
            if str(old_val) != str(new_val):
                diffs.append(f"{field}: {old_val} ➔ {new_val}")
        changes_desc = ", ".join(diffs) if diffs else "Atualização sem alterações visíveis"
    
    AuditLog.objects.create(
        user=user,
        model_name=model_name,
        object_id=str(instance.pk),
        object_repr=str(instance),
        action=action,
        changes=changes_desc
    )

@receiver(post_delete, sender=Sale)
@receiver(post_delete, sender=Product)
@receiver(post_delete, sender=Customer)
def audit_log_delete(sender, instance, **kwargs):
    user = get_current_user()
    if not user or not user.is_authenticated:
        return

    AuditLog.objects.create(
        user=user,
        model_name=sender._meta.verbose_name.title(),
        object_id=str(instance.pk),
        object_repr=str(instance),
        action='DELETE',
        changes=''
    )