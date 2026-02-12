from django.db import models
from datetime import date

class Category(models.Model):
    name = models.CharField("Categoria", max_length=100, unique=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"

class Supplier(models.Model):
    name = models.CharField("Nome / Razão Social", max_length=255)
    cnpj_cpf = models.CharField("CNPJ/CPF", max_length=20, blank=True)
    phone = models.CharField("Telefone", max_length=20, blank=True)
    email = models.EmailField("Email", blank=True)
    
    def __str__(self):
        return self.name
        
    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"

class Brand(models.Model):
    name = models.CharField("Marca", max_length=100, unique=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Marca"
        verbose_name_plural = "Marcas"

class OlfactoryFamily(models.Model):
    name = models.CharField("Família Olfativa", max_length=100, unique=True)
    
    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Família Olfativa"
        verbose_name_plural = "Famílias Olfativas"

class Product(models.Model):
    GENDER_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('U', 'Unissex'),
    ]
    
    TYPE_CHOICES = [
        ('perfume', 'Perfume (Frasco)'),
        ('decant', 'Decant (Amostra)'),
        ('kit', 'Kit / Combo'),
        ('cosmetic', 'Cosmético'),
    ]

    # Dados Principais
    name = models.CharField("Nome do Produto", max_length=255)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Categoria")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Fornecedor Padrão")
    line = models.CharField("Linha", max_length=100, blank=True, help_text="Ex: Malbec, Acqua di Gio")
    product_type = models.CharField("Tipo", max_length=20, choices=TYPE_CHOICES, default='perfume')
    gender = models.CharField("Gênero", max_length=1, choices=GENDER_CHOICES, default='U')
    olfactory_family = models.ForeignKey(OlfactoryFamily, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Família Olfativa")
    
    # Pirâmide Olfativa
    top_notes = models.TextField("Notas de Saída", blank=True)
    heart_notes = models.TextField("Notas de Corpo", blank=True)
    base_notes = models.TextField("Notas de Fundo", blank=True)
    description = models.TextField("Descrição", blank=True)
    
    # Detalhes do Item
    volume = models.CharField("Volume", max_length=50, help_text="Ex: 100ml, 50ml, 5ml", blank=True)
    barcode = models.CharField("Código de Barras", max_length=100, unique=True, blank=True, null=True)
    batch_code = models.CharField("Lote", max_length=50, blank=True)
    expiration_date = models.DateField("Validade", blank=True, null=True)
    
    # Financeiro
    cost_price = models.DecimalField("Preço de Custo", max_digits=10, decimal_places=2, default=0, blank=True)
    selling_price = models.DecimalField("Preço de Venda", max_digits=10, decimal_places=2, default=0, blank=True)
    
    # Estoque
    stock_quantity = models.IntegerField("Qtd. em Estoque", default=0)
    min_stock = models.IntegerField("Estoque Mínimo", default=5)
    
    # Mídia
    image = models.ImageField("Imagem", upload_to='products/', blank=True, null=True)
    image_url = models.URLField("URL da Imagem", max_length=500, blank=True, null=True, help_text="Cole um link de imagem da internet (opcional)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def profit_margin(self):
        """Calcula a margem de lucro bruta (%)"""
        if self.cost_price > 0:
            margin = ((self.selling_price - self.cost_price) / self.cost_price) * 100
            return round(margin, 2)
        return 0

    @property
    def status_validity(self):
        if not self.expiration_date:
            return "Indefinido"
        today = date.today()
        if self.expiration_date < today:
            return "Vencido"
        elif (self.expiration_date - today).days <= 30:
            return "Vencendo em breve"
        return "Ok"

    def __str__(self):
        return f"{self.name} ({self.volume})"

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"

class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('E', 'Entrada'),
        ('S', 'Saída'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Produto")
    quantity = models.IntegerField("Quantidade")
    movement_type = models.CharField("Tipo", max_length=1, choices=MOVEMENT_TYPES)
    reason = models.CharField("Motivo", max_length=255, blank=True, null=True, help_text="Ex: Compra, Venda, Decant, Quebra")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Atualiza o estoque do produto automaticamente na criação
        if not self.pk:
            if self.movement_type == 'E':
                self.product.stock_quantity += self.quantity
            else:
                self.product.stock_quantity -= self.quantity
            self.product.save()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.product.name}"

    class Meta:
        verbose_name = "Movimentação de Estoque"
        verbose_name_plural = "Movimentações de Estoque"

class ProductComponent(models.Model):
    """Define quais produtos compõem um Kit"""
    kit = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='components', verbose_name="Kit Pai")
    component = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='used_in_kits', verbose_name="Produto Componente")
    quantity = models.DecimalField("Quantidade no Kit", max_digits=10, decimal_places=2, default=1)

    def __str__(self):
        return f"{self.quantity}x {self.component.name} em {self.kit.name}"

    class Meta:
        unique_together = ('kit', 'component')