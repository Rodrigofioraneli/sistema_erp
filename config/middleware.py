from django.shortcuts import redirect
from django.urls import reverse
import threading
from reports.models import CompanySettings

# Armazenamento local para thread
_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # --- ÁREA DE PERSONALIZAÇÃO VISUAL (Dinâmica do Banco de Dados) ---
        try:
            # Tenta buscar as configurações salvas
            settings = CompanySettings.objects.first()
            if settings:
                request.theme = {
                    'primary_color': settings.primary_color,
                    'secondary_color': settings.secondary_color,
                    'background_color': settings.background_color,
                    'card_bg': '#ffffff',
                    'text_color': '#333333',
                    'font_family': f"'{settings.font_family}', sans-serif",
                    'font_size': f"{settings.font_size}px"
                }
            else:
                raise Exception("Sem configuração")
        except:
            # Tema Padrão (Caso ocorra erro ou não tenha config)
            request.theme = {
                'primary_color': '#3498db', 'secondary_color': '#2c3e50',
                'background_color': '#f4f6f9', 'card_bg': '#ffffff',
                'text_color': '#333333', 'font_family': "'Poppins', sans-serif", 'font_size': '14px'
            }

        # Armazena o usuário atual na thread para uso em signals (logs)
        _thread_locals.user = getattr(request, 'user', None)

        # 1. Se o usuário já está logado, deixa passar
        if request.user.is_authenticated:
            return self.get_response(request)

        # 2. Define a URL de login
        try:
            login_url = reverse('login')
        except Exception:
            login_url = '/accounts/login/'

        # 3. Lista de caminhos que NÃO precisam de senha (exceções)
        # O próprio login, o painel admin (que tem login próprio) e arquivos de estilo/imagens
        current_path = request.path
        
        if current_path.startswith(login_url):
            return self.get_response(request)
            
        if current_path.startswith('/admin/'):
            return self.get_response(request)
            
        if current_path.startswith('/static/') or current_path.startswith('/media/'):
            return self.get_response(request)

        # Permite acesso à página inicial (Home/Welcome) sem login
        if current_path == '/':
            return self.get_response(request)

        # 4. Se não for nenhuma exceção, manda para o login
        return redirect(f'{login_url}?next={current_path}')