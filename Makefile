.PHONY: backend frontend install-backend install-frontend migrate make-migration create-user

backend:
	cd backend && PYENV_VERSION=statdash uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

install-backend:
	PYENV_VERSION=statdash pip install -r backend/requirements.txt

install-frontend:
	cd frontend && npm install

migrate:
	cd backend && PYENV_VERSION=statdash alembic upgrade head

make-migration:
	cd backend && PYENV_VERSION=statdash alembic revision --autogenerate -m "$(name)"

create-user:
	cd backend && PYENV_VERSION=statdash python -m scripts.create_user --email=$(email) --password=$(password) $(if $(superuser),--superuser,)
