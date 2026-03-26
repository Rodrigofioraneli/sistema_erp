from django.db import models
from django.utils import timezone

class CompanySettings(models.Model):
    name = models.CharField("Razão Social", max_length=255, default="Minha Empresa")
    cnpj = models.CharField("CNPJ", max_length=20, default="00.000.000/0000-00")
    state_registration = models.CharField("Inscrição Estadual", max_length=50, blank=True)
    address = models.CharField("Endereço Completo", max_length=255, blank=True)
    phone = models.CharField("Telefone", max_length=20, blank=True)
    email = models.EmailField("Email", blank=True)
    website = models.URLField("Site / Instagram", blank=True)
    logo = models.ImageField("Logo da Empresa", upload_to='company_logo/', blank=True, null=True)

    # --- Personalização Visual (Temas) ---
    primary_color = models.CharField("Cor Principal", max_length=20, default="#3498db") # Azul padrão
    secondary_color = models.CharField("Cor Secundária", max_length=20, default="#2c3e50") # Cinza escuro
    background_color = models.CharField("Cor de Fundo", max_length=20, default="#f4f6f9") # Cinza claro
    font_family = models.CharField("Fonte", max_length=50, default="Poppins")
    font_size = models.IntegerField("Tamanho da Fonte (px)", default=14)
    
    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Configuração da Empresa"
        verbose_name_plural = "Configurações da Empresa"

class PaymentMethod(models.Model):
    name = models.CharField("Forma de Pagamento", max_length=50)
    active = models.BooleanField("Ativo", default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"

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