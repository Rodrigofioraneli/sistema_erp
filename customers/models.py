from django.db import models

class FragranceFamily(models.Model):
    name = models.CharField("Família Olfativa", max_length=50, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Família Olfativa"
        verbose_name_plural = "Famílias Olfativas"

class Customer(models.Model):
    CLASSIFICATION_CHOICES = [
        ('novo', 'Novo'),
        ('recorrente', 'Recorrente'),
        ('vip', 'VIP'),
    ]

    name = models.CharField("Nome Completo", max_length=255)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=20, unique=True, blank=True, null=True)
    phone = models.CharField("Telefone / WhatsApp", max_length=20)
    email = models.EmailField("E-mail", blank=True, null=True)
    birth_date = models.DateField("Data de Nascimento", blank=True, null=True)
    
    # Endereço Detalhado
    zip_code = models.CharField("CEP", max_length=10, blank=True)
    street = models.CharField("Logradouro", max_length=100, blank=True)
    number = models.CharField("Número", max_length=10, blank=True)
    complement = models.CharField("Complemento", max_length=50, blank=True)
    neighborhood = models.CharField("Bairro", max_length=50, blank=True)
    city = models.CharField("Cidade", max_length=50, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    
    # Preferências e CRM
    fragrance_preferences = models.ManyToManyField(FragranceFamily, blank=True, verbose_name="Preferências Olfativas")
    favorite_brands = models.TextField("Marcas Favoritas", blank=True, help_text="Ex: Chanel, Dior (separado por vírgula)")
    
    # Fidelidade
    loyalty_points = models.IntegerField("Pontos de Fidelidade", default=0)
    classification = models.CharField("Classificação", max_length=20, choices=CLASSIFICATION_CHOICES, default='novo')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"