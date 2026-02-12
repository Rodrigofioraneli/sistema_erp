from django.db import models

class CompanySettings(models.Model):
    name = models.CharField("Razão Social", max_length=255, default="Minha Empresa")
    cnpj = models.CharField("CNPJ", max_length=20, default="00.000.000/0000-00")
    state_registration = models.CharField("Inscrição Estadual", max_length=50, blank=True)
    address = models.CharField("Endereço Completo", max_length=255, blank=True)
    phone = models.CharField("Telefone", max_length=20, blank=True)
    email = models.EmailField("Email", blank=True)
    website = models.URLField("Site / Instagram", blank=True)
    logo = models.ImageField("Logo da Empresa", upload_to='company_logo/', blank=True, null=True)
    
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