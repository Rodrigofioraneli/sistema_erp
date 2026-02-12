# Perfume ERP

Sistema de gestão para loja de perfumes desenvolvido em Django.

## Funcionalidades

- **PDV**: Ponto de venda com busca rápida de produtos e clientes.
- **Estoque**: Controle de entrada e saída, alertas de estoque baixo e validade.
- **Relatórios**: Dashboards completos de vendas, financeiro e produtos.
- **Backup**: Exportação de dados e backup do banco de dados.

## Instalação

1. Instale as dependências: `pip install -r requirements.txt`
2. Configure o banco de dados: `python manage.py migrate`
3. Crie um superusuário: `python manage.py createsuperuser`
4. Rode o servidor: `python manage.py runserver`

## Deploy (Produção)

Para rodar online no Render:

1. Crie um novo **Web Service** no Render conectado ao seu repositório.
2. Em **Environment**, escolha "Python 3".
3. Em **Build Command**, insira: `./build.sh`
4. Em **Start Command**, insira: `gunicorn config.wsgi:application`
5. Adicione as seguintes **Environment Variables**:
   - `PYTHON_VERSION`: `3.11.0` (ou a versão que você usa)
   - `SECRET_KEY`: Gere uma chave aleatória segura.
   - `WEB_CONCURRENCY`: `2` (Opcional, para performance do Gunicorn)
6. Adicione um **PostgreSQL** no Render e linke ao seu serviço (o Render criará a variável `DATABASE_URL` automaticamente).

## Configuração de Mídia (Fotos)

O Render possui um sistema de arquivos efêmero (os arquivos são apagados ao reiniciar). Para que as fotos dos produtos permaneçam salvas em produção, é necessário configurar um serviço de armazenamento externo.

**Recomendação (Cloudinary):**
1. Instale o pacote: `pip install django-cloudinary-storage`
2. Adicione ao `INSTALLED_APPS` no `settings.py`: `'cloudinary_storage'`, `'cloudinary'`
3. Configure as credenciais (`CLOUDINARY_STORAGE`) e defina `DEFAULT_FILE_STORAGE` no `settings.py`.