# Contributing to Kaizen

Thanks for your interest in contributing! This guide covers local setup, the pull-request workflow, and the conventions used in this repo.

## Development Setup

### Prerequisites

- **Python 3.12** (3.13 is not supported — `pyproject.toml` pins `>=3.12,<3.13`)
- **Node.js 20+** (for the `dashboard/` and `docs/` apps)
- **Docker or Podman** with Compose
- [**uv**](https://docs.astral.sh/uv/) — Python package manager used by this repo

### Local Development

```bash
git clone <your-fork-url> kaizen
cd kaizen
cp .env.example .env
# edit .env — at minimum set OPENAI_API_KEY and GIT_TOKEN_ENCRYPTION_KEY

# Start infrastructure only
docker compose up -d postgres redis     # or: podman-compose up -d postgres redis

# Install Python dependencies from uv.lock
uv sync

# Apply database migrations
uv run alembic upgrade head

# Run the API with auto-reload
uv run uvicorn src.api.main:app --reload --port 8000

# In a second shell, run the Celery worker
uv run celery -A src.worker.celery_app worker -l info

# Dashboard (Next.js 14)
cd dashboard && npm install && npm run dev        # http://localhost:3000

# Docs site (Nextra)
cd docs && npm install && npm run dev             # http://localhost:4000
```

### Running Tests

```bash
uv run pytest
```

The suite lives under `tests/` and uses `pytest-asyncio`. Coverage tooling is not configured in this repo — if you want coverage locally, add `pytest-cov` to your own environment.

## How to Contribute

### Reporting Issues

- Open an issue on the GitHub repository with steps to reproduce, expected behavior, and actual behavior.
- For security vulnerabilities, please contact the maintainers privately rather than filing a public issue.

### Pull Requests

1. Fork the repository and create a feature branch from `main`: `git checkout -b feature/my-feature`
2. Make your changes, keeping the diff focused on a single concern.
3. Run the test suite: `uv run pytest`
4. For dashboard changes, run `npm run lint` inside `dashboard/` (uses `next lint`).
5. Commit with a descriptive message (see convention below).
6. Push to your fork and open a PR against `main`.

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new evaluator type
fix: resolve trailing slash redirect issue
docs: update SDK quickstart guide
chore: update dependencies
test: add GEPA analyze test fixture
```

### Code Style

- **Python**: follow the style of the surrounding code. No project-wide linter/formatter is wired into CI yet — keep diffs tidy and avoid unnecessary churn.
- **TypeScript (dashboard)**: `npm run lint` (Next.js ESLint defaults). No Prettier config is committed; match the existing style of the files you touch.
- Prefer clear names over comments. Don't add docstrings on obvious code.
- Add or update tests alongside behavior changes.

## Repository Layout

```
src/
  api/          # FastAPI app, routes, auth, schemas
  models/       # SQLAlchemy ORM models
  services/     # Git providers (GitHub / Bitbucket Server / GitLab), auto-PR, prompt file IO
  worker/       # Celery app, DSPy pipeline, evaluators, cost estimator
  sdk/          # kaizen_sdk Python package (installable)
  utils/        # Crypto helpers, PR templates
  config.py     # pydantic-settings configuration
  __main__.py   # `python -m src create-key` CLI
dashboard/      # Next.js 14 web UI
docs/           # Nextra documentation site
alembic/        # Database migrations
tests/          # Pytest suite
assets/         # Logo and architecture diagram sources
```

## Areas for Contribution

- Additional evaluator types (see `src/worker/evaluators.py`)
- Hardening the GitLab and Bitbucket Server providers (see `src/services/`)
- Dashboard UX improvements
- Expanded test coverage, especially around the optimization pipeline
- Documentation and tutorials in `docs/content/`

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
