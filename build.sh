#!/usr/bin/env bash
# exit on error
set -o errexit

echo "--> [BUILD] Iniciando script de build..."
pip install --upgrade pip
pip install -r requirements.txt
echo "--> [BUILD] Dependências instaladas com sucesso."

# Coleta arquivos estáticos para o WhiteNoise servir
python manage.py collectstatic --no-input

# Aplica as migrações no banco de dados (PostgreSQL no Render)
python manage.py migrate

# Cria o superusuário de forma segura, se ele não existir
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='${ADMIN_USER:-admin}').exists() or User.objects.create_superuser('${ADMIN_USER:-admin}', '${ADMIN_EMAIL:-admin@example.com}', '${ADMIN_PASS:-admin123}')"