from django.shortcuts import redirect
from django.urls import reverse

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Se o usuário já está logado, deixa passar
        if request.user.is_authenticated:
            return self.get_response(request)

        # 2. Define a URL de login
        try:
            login_url = reverse('login')
        except:
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