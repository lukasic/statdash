.PHONY: backend frontend mcp-server install-backend install-frontend install-mcp migrate make-migration create-user

backend:
	cd backend && PYENV_VERSION=statdash uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

mcp-server:
	cd mcp-server && PYENV_VERSION=statdash-mcp python server.py

install-backend:
	PYENV_VERSION=statdash pip install -r backend/requirements.txt

install-frontend:
	cd frontend && npm install

install-mcp:
	PYENV_VERSION=statdash-mcp pip install -r mcp-server/requirements.txt

migrate:
	cd backend && PYENV_VERSION=statdash alembic upgrade head

make-migration:
	cd backend && PYENV_VERSION=statdash alembic revision --autogenerate -m "$(name)"

create-user:
	cd backend && PYENV_VERSION=statdash python -m scripts.create_user --email=$(email) --password=$(password) $(if $(superuser),--superuser,)
