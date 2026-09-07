# Zdravý Projekt

Full-stack web application with Django backend and React frontend, containerized with Docker.

## 🏗️ Architecture

- **Backend**: Django 5.0 + Django REST Framework + PostgreSQL
- **Frontend**: React 18 + Vite + Tailwind CSS + TypeScript
- **Reverse Proxy**: Traefik (managed by Dokploy)
- **Containerization**: Docker + Docker Compose
- **CI/CD**: GitHub Actions

## 🤝 Contributing

**Commit Message Format:**

```
<type>(<scope>): <subject>
```

**Príklady:**

- `feat(backend): add user authentication`
- `fix(frontend): resolve navbar issues`
- `docs: update setup instructions`

Commit messages sú automaticky validované pri každom PR.

## 📋 Prerequisites

- Docker & Docker Compose
- Git
- (Optional) Python 3.11+ and Node.js 20+ for local development without Docker

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone <repository-url>
cd zdravy-projekt
```

### 2. Set up environment variables

```bash
cp env/dev.example .env.dev
```

Edit `.env.dev` and configure the variables (database, secrets, etc.).

### 3. Start development environment

```bash
docker compose --env-file .env.dev -f compose/dev.yml up --build
```

The application will be available at:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Django Admin: http://localhost:8000/admin

### 4. Run initial migrations

```bash
docker compose --env-file .env.dev -f compose/dev.yml exec backend python manage.py migrate
docker compose --env-file .env.dev -f compose/dev.yml exec backend python manage.py createsuperuser
```

## 🧪 Testing

### Backend Tests

```bash
# Run all tests
docker compose --env-file .env.dev -f compose/dev.yml exec backend pytest

# Run with coverage (terminal + HTML report)
docker compose --env-file .env.dev -f compose/dev.yml exec backend pytest --cov=api --cov=app --cov-report=term-missing --cov-report=html

# Enforce minimum backend coverage (60%)
docker compose --env-file .env.dev -f compose/dev.yml exec backend pytest --cov=api --cov=app --cov-fail-under=60

# Run specific test file
docker compose --env-file .env.dev -f compose/dev.yml exec backend pytest api/tests/integration/test_order_api.py
```

> **`pytest` is the only supported backend test runner.** Bare `pytest` already
> covers both `tests/` and `api/tests/` (see `testpaths` in `pytest.ini`), so run
> it without a path argument before pushing — passing a single directory hides
> failures in the other. The suite runs with `--nomigrations`, so tables are built
> straight from the models and reference data (portion types, diets…) is **not**
> seeded; tests that need it create it themselves. `python manage.py test` is
> **not** supported: it applies the data migrations, and the seeded rows then
> collide with the fixtures.

**Local testing without Docker:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pytest
```

### Frontend Tests

```bash
# Run all tests
docker compose --env-file .env.dev -f compose/dev.yml exec frontend npm test

# Watch mode
docker compose --env-file .env.dev -f compose/dev.yml exec frontend npm run test:watch
```

**Local testing without Docker:**

```bash
cd frontend
npm install
npm test
```

## 📂 Project Structure

```
zdravy-projekt/
├── backend/                    # Django backend
│   ├── app/                    # Main Django app
│   │   ├── settings/           # Environment-specific settings
│   │   │   ├── base.py         # Shared settings
│   │   │   ├── dev.py          # Development settings
│   │   │   ├── staging.py      # Staging settings
│   │   │   └── prod.py         # Production settings
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── tests/                  # Legacy + broad backend tests
│   ├── api/tests/              # Structured API test layers
│   │   ├── conftest.py
│   │   ├── factories.py
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── pytest.ini
│
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── components/         # Reusable components
│   │   ├── pages/              # Page components
│   │   ├── api/                # API client utilities
│   │   ├── __tests__/          # Test files
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── Dockerfile
│   └── nginx.conf
├── .github/                    # GitHub Actions workflows
│   └── workflows/
│       ├── commit-lint.yml     # PR title commit format check
│       ├── pr.yml              # PR checks
│       ├── staging.yml         # Staging image build
│       └── production.yml      # Production image build
│
├── compose/                    # Docker Compose files
│   ├── dev.yml                 # Development environment
│   ├── staging.yml             # Dokploy staging app stack
│   ├── prod.yml                # Dokploy production app stack
│   └── observability.yml       # Alloy observability stack
├── env/                        # Environment variable templates
│   ├── dev.example
│   ├── staging.example
│   ├── prod.example
│   └── observability.example
├── observability/
│   └── alloy/
│       └── config.alloy
├── .gitignore
└── README.md
```

## 📚 Documentation

- [Architektura a dolezite flows](docs/ARCHITECTURE_AND_FLOWS.md) - modulova mapa, Mermaid diagramy, datovy model, objednavkove/report/push/Celery flows a poznamky k rizikovym miestam.

## 🔧 Development

### Backend Development

The backend uses Django with environment-specific settings:

```bash
# Run development server
docker compose --env-file .env.dev -f compose/dev.yml exec backend python manage.py runserver 0.0.0.0:8000

# Create migrations
docker compose --env-file .env.dev -f compose/dev.yml exec backend python manage.py makemigrations

# Apply migrations
docker compose --env-file .env.dev -f compose/dev.yml exec backend python manage.py migrate

# Create superuser
docker compose --env-file .env.dev -f compose/dev.yml exec backend python manage.py createsuperuser

# Django shell
docker compose --env-file .env.dev -f compose/dev.yml exec backend python manage.py shell
```

### Frontend Development

The frontend uses React with Vite for fast development:

```bash
# Install new package
docker compose --env-file .env.dev -f compose/dev.yml exec frontend npm install <package-name>

# Build for production
docker compose --env-file .env.dev -f compose/dev.yml exec frontend npm run build

# Lint code
docker compose --env-file .env.dev -f compose/dev.yml exec frontend npm run lint
```

### Code Quality

Pre-commit hooks enforce formatting and linting automatically on every commit.

**Setup (once per clone):**

```bash
pip install pre-commit   # or: brew install pre-commit
pre-commit install       # installs both the pre-commit and commit-msg hooks
git config commit.template .gitmessage   # shows the commit format as a template on `git commit`
```

**Run against all files manually:**

```bash
pre-commit run --all-files
```

**Hooks configured** (versions must match `backend/requirements.txt` — see the
comment at the top of `.pre-commit-config.yaml`):

| Hook                 | Tool         | What it does                                                                                                     |
| -------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------ |
| `black`              | black 26.3.1 | Formats Python code                                                                                              |
| `isort`              | isort 8.0.1  | Sorts imports (black-compatible)                                                                                 |
| `flake8`             | flake8 7.3.0 | Lints for style/logic errors                                                                                     |
| `mypy`               | mypy 2.3.1   | Static type checking                                                                                             |
| `gramage-css-sync`   | —            | Keeps the on-screen and PDF gramáž table CSS identical                                                          |
| `commit-msg-format`  | —            | Rejects a commit message that isn't Conventional Commits — see `.gitmessage`; feeds release-please's changelog |

**Via Docker (without local Python):**

```bash
# Backend: Format code with black
docker compose --env-file .env.dev -f compose/dev.yml exec backend black .

# Backend: Sort imports
docker compose --env-file .env.dev -f compose/dev.yml exec backend isort .

# Backend: Lint with flake8
docker compose --env-file .env.dev -f compose/dev.yml exec backend flake8 .

# Frontend: Lint
docker compose --env-file .env.dev -f compose/dev.yml exec frontend npm run lint
```

## 🌍 Environments

### Development

```bash
docker compose --env-file .env.dev -f compose/dev.yml up
```

- DEBUG mode enabled
- Hot reload for both backend and frontend
- CORS allows all origins
- Fast password hasher
- Console email backend

### Staging

```bash
docker compose -f compose/staging.yml up -d
```

- Production-like environment
- SSL/TLS enabled
- Mirrors production settings

### Production

Deployment is managed by Dokploy (Traefik + Compose stack).

- DEBUG disabled
- SSL/TLS required
- Security headers enabled
- Gunicorn WSGI server
- Optimized static file serving

## 🔐 Environment Variables

See [env/dev.example](env/dev.example), [env/staging.example](env/staging.example), [env/prod.example](env/prod.example), and [env/observability.example](env/observability.example) for available environment variables.

Key variables:

- `DJANGO_SECRET_KEY`: Django secret key (generate for production)
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: Database credentials
- `POSTGRES_HOST`: Dokploy-managed Postgres hostname for staging/production
- `REDIS_URL`: Dokploy-managed Redis internal URL for staging/production; Celery uses DB 0 and Django cache uses DB 1
- `REGISTRY_USERNAME`: Docker registry namespace used by the deployed image names
- `PROD_IMAGE_TAG`: immutable production image tag from the production workflow, for example `prod-597a02c9e2afa618f4c1cf24a64923a09721e57c`
- `EMAIL_HOST`, `EMAIL_HOST_PASSWORD`: SMTP settings required by staging/production
- `DJANGO_SETTINGS_MODULE`: Settings module (`app.settings.dev/staging/prod`)

## 🚢 Deployment

### Staging Deployment (Dokploy)

Staging deploy flow:

1. GitHub Actions builds and pushes Docker images on push to `develop`
2. Dokploy pulls fresh images and deploys `compose/staging.yml`

Required setup:

- GitHub Secrets: `REGISTRY_USERNAME`, `REGISTRY_PASSWORD`
- Dokploy app envs: `REGISTRY_USERNAME`, `DJANGO_SECRET_KEY`, `POSTGRES_*`, `REDIS_URL`, `EMAIL_HOST`, `EMAIL_HOST_PASSWORD`, `STAGING_HOST`/`PROD_HOST`, `FRONTEND_URL`, etc.
- Dokploy network available as `dokploy-network`

### Rolling Updates And Limits

The staging and production compose files include Swarm `deploy` settings for
rolling updates, rollback behavior, replicas, and CPU/RAM limits. These settings
are honored when the stack is deployed through Swarm-compatible deployment
(`docker stack deploy`); plain `docker compose up` may ignore the rolling-update
fields.

Defaults:

- Production runs `BACKEND_REPLICAS=2`, `FRONTEND_REPLICAS=2`, `CELERY_REPLICAS=1`, and one fixed `celery-beat`.
- Staging runs one replica per service by default.
- `backend` and `frontend` use `start-first` rolling updates.
- `celery-beat` uses `stop-first` and `replicas: 1` to avoid duplicate scheduled tasks.
- CPU/RAM limits can be changed with variables such as `BACKEND_CPU_LIMIT`, `BACKEND_MEMORY_LIMIT`, `FRONTEND_CPU_LIMIT`, and `CELERY_MEMORY_LIMIT`.

### CI/CD Pipeline

GitHub Actions automatically:

1. Runs tests on every pull request
2. Checks code quality (linting, formatting)
3. Builds staging images on push to `develop` branch
4. Builds production images on push to `main` branch

### Production Deployment

Production deployment is handled via Dokploy similarly to staging:

1. GitHub Actions builds and pushes immutable `prod-<git-sha>` Docker images on push to `main`
2. GitHub Actions calls the Dokploy API, writes that exact tag to the Compose env as `PROD_IMAGE_TAG`, and triggers `compose.deploy`
3. Dokploy performs the deployment through its configured Git/SSH key and Swarm integration
4. Backend, celery, celery-beat, and frontend all use that same immutable tag
5. Dokploy owns the public route/Traefik configuration for the production stack

The production stack intentionally has no `:prod` fallback. Mutable tags can be
resolved to an old digest by Swarm/Dokploy, leaving production on stale backend
or frontend code even after a successful image build. Rollbacks use the same
mechanism: set `PROD_IMAGE_TAG` back to a previous `prod-<git-sha>` tag and
redeploy.

Production deploy requires these GitHub Environment `production` secrets:

- `REGISTRY_USERNAME`, `REGISTRY_PASSWORD`: Docker registry credentials
- `DOKPLOY_API_KEY`: Dokploy API key with permission to update and deploy the production Compose service

Production deploy also requires these GitHub Environment `production` variables:

- `DOKPLOY_URL`: base URL of the Dokploy instance, for example `https://dokploy.example.com`
- `DOKPLOY_COMPOSE_ID`: production Docker Compose service id from Dokploy

The workflow does not SSH into the Docker host. Dokploy remains the deployment
owner; GitHub only publishes images and asks Dokploy to deploy the matching
immutable tag.

### Observability

Observability runs as a separate Alloy stack:

```bash
docker compose -f compose/observability.yml up -d
```

Configure the stack from [env/observability.example](env/observability.example).
Alloy tails Docker logs and discovers Django backend replicas to scrape, both
through the Docker socket — no static scrape target to configure.

See [observability/README.md](observability/README.md) for the full production
setup checklist, the importable Grafana dashboard
(`observability/grafana/dashboards/backend-overview.json`), and the
recommended alert rules.

## 🐛 Troubleshooting

### Database connection issues

```bash
# Check database status
docker compose --env-file .env.dev -f compose/dev.yml ps db

# View database logs
docker compose --env-file .env.dev -f compose/dev.yml logs db

# Reset database
docker compose --env-file .env.dev -f compose/dev.yml down -v
docker compose --env-file .env.dev -f compose/dev.yml up -d
```

### Frontend build issues

```bash
# Clear node_modules and reinstall
docker compose --env-file .env.dev -f compose/dev.yml exec frontend rm -rf node_modules
docker compose --env-file .env.dev -f compose/dev.yml exec frontend npm install
```

### View logs

```bash
# All services
docker compose --env-file .env.dev -f compose/dev.yml logs -f

# Specific service
docker compose --env-file .env.dev -f compose/dev.yml logs -f backend
docker compose --env-file .env.dev -f compose/dev.yml logs -f frontend
```

## 📚 Additional Resources

- [Django Documentation](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [React Documentation](https://react.dev/)
- [Vite Documentation](https://vitejs.dev/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Docker Compose](https://docs.docker.com/compose/)
