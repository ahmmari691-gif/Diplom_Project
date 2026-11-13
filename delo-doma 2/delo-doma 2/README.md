# Delo Doma

Web platform for micro and small businesses: business storefronts, catalogues, customer orders, private order tracking, reference-file uploads, inventory, and platform administration and analytics.

## Technology

- Python / Django backend and SQLite for local development.
- React, TypeScript and Vite frontend.
- Optional Google Gemini integration; local ordering works without an API key.
- Russian, Kazakh and English interface.

## Run locally

Install Python 3.12+ and Node.js 22.12+ (or a newer supported Node release).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
cd frontend
npm install
npm run build
cd ..
python run.py
```

On Windows, activate the environment with `.venv\Scripts\activate` and copy `.env.example` to `.env` using your file manager or shell.

Open http://127.0.0.1:8000/ and register your own business. The launcher applies migrations before starting Django. The first local launch generates local secret files in `.local/`.

To create optional demo records:

```bash
python run.py --demo
```

To create your own administrator account:

```bash
python manage.py createsuperuser
```

Django administration is available at http://127.0.0.1:8000/django-admin/. Platform managers use an invitation issued by a platform administrator.

## Optional Gemini configuration

Edit your private `.env` file: set `DELO_AI_MODE=gemini`, provide your own `GEMINI_API_KEY`, and set `GEMINI_MODEL` to a model available to your Google project. The example model is configurable; provider availability and quotas depend on your account. Business and customer consent controls also apply to external AI requests.

Never upload `.env`, `.local/`, API keys, databases, customer information or uploaded private documents to GitHub. The supplied archive excludes these files.

## Project structure

- `core/`: backend logic, models, migrations, tests and management commands.
- `config/`: Django settings and URLs.
- `frontend/src/`: React components, styling and translations.
- `requirements.txt`: Python dependencies.
- `.env.example`: configuration template without credentials.
- `run.py`: local launcher.

## Development checks

Build the frontend before running these commands:

```bash
python manage.py check
python manage.py test
```

## Deployment

`run.py` starts the local development server. Public deployment requires production configuration, a WSGI server such as Gunicorn (`config.wsgi:application`), HTTPS, private secrets, database and backup configuration, allowed hosts, CSRF origins and collected static files. GitHub stores the source code; GitHub Pages alone cannot run the Django backend.


## Render deployment

The repository root render.yaml deploys this subdirectory using Docker and PostgreSQL. In Render select New > Blueprint and connect the repository. Both services select Free. This is a temporary preview: the free database expires after 30 days and the web service sleeps when idle. Review plans before deploying.

Render generates independent server secrets. Keep DATA_ENCRYPTION_SECRET unchanged while using the same database. No local customer data or API credentials are migrated. The first release uses local assistance; Gemini can be configured separately through private environment variables. Administrator creation uses `python manage.py createsuperuser` from a trusted deployment environment. The Django admin URL is `/django-admin/`.


### Temporary inventory switch

Inventory is hidden and its API returns 404 by default. Automatic order stock deductions are paused; existing items, recipes and history are retained. Set `DELO_INVENTORY_ENABLED=1` on the server and restart to restore access and future deductions. Orders completed while disabled are not deducted retroactively.

## Учебный запуск без внешней базы

Для трёх аккаунтов (business, manager, admin) на любом компьютере используйте `python run.py --study` после установки зависимостей и сборки frontend. Настройки, локальные логины, пароли и инструкция Render находятся в [STUDY_MODE.md](STUDY_MODE.md). Учебный режим использует отдельную SQLite, автоматически создаёт недостающие аккаунты и не подключается к DATABASE_URL.
