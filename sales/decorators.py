from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib import messages

def admin_required(view_func):
    """
    Decorador que verifica se o usuário é um Superusuário (Admin).
    Se não for, redireciona para o PDV com uma mensagem de erro.
    """
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, '⛔ Acesso Negado: Apenas administradores podem acessar esta área.')
        return redirect('pos_view')
    return _wrapped_view