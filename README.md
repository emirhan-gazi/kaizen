<p align="center">
  <img src="assets/kaizen.png" alt="Kaizen" width="180" />
</p>

<h1 align="center">Kaizen</h1>

<p align="center">
  <strong>Continuous prompt optimization platform for AI applications.</strong><br/>
  Instrument LLM calls, collect user feedback, and let Kaizen refine your prompts automatically.
</p>

---

Kaizen is a self-hosted platform that ingests runtime traces and feedback from your AI application, runs DSPy-based prompt optimization (GEPA by default, MIPROv2 optional) in a background worker, versions the result, and — when configured — opens a pull request against your repository so the change can be reviewed like any other code.

The stack ships as a FastAPI service, a Celery worker, a Postgres + Redis backend, a Next.js dashboard, and a Python SDK that lives in `src/sdk/`.

## Tech Stack

- **Language**: Python 3.12 (`>=3.12,<3.13`)
- **API**: FastAPI 0.135, Uvicorn
- **Worker**: Celery 5.6 (Redis broker, Postgres result backend)
- **Optimization**: DSPy 3.1 + LiteLLM 1.80
- **ORM / Migrations**: SQLAlchemy 2.0 (async, `psycopg` driver) + Alembic 1.18
- **Database**: PostgreSQL 16
- **Cache / Queue**: Redis 7.4
- **Dashboard**: Next.js 14, TypeScript, Tailwind, TanStack Query, Radix UI, Recharts
- **Docs site**: Next.js 14 + Nextra 4.6
- **Package manager**: [uv](https://docs.astral.sh/uv/) (Python), npm (JS)

## Prerequisites

- Python **3.12** (3.13 is not supported by the pinned runtime)
- Node.js **20+** (dashboard and docs site)
- Docker / Podman with Compose plugin
- [uv](https://docs.astral.sh/uv/) for local Python development
- An OpenAI-compatible LLM endpoint and API key (used by LiteLLM for teacher/judge models)
- A Git provider access token if you want auto-PR (GitHub, Bitbucket Server, or GitLab)

## Quick Start

### 1. Clone and configure environment

```bash
git clone <your-fork-url> kaizen
cd kaizen
cp .env.example .env
```

Then edit `.env` and set at minimum:

| Variable | Purpose |
|----------|---------|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Postgres credentials used by the `postgres` service |
| `DATABASE_URL` | Async SQLAlchemy URL (e.g. `postgresql+psycopg://postgres:postgres@postgres:5432/continuous_tune`) |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Redis/Celery wiring (defaults in `.env.example` match the compose network) |
| `OPENAI_API_KEY` | LLM provider key used by LiteLLM |
| `GIT_TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting stored Git tokens — generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### 2. Start the full stack

```bash
docker compose up -d      # or: podman-compose up -d
```

This boots:

| Service   | Port | Description                                |
|-----------|------|--------------------------------------------|
| api       | 8000 | FastAPI app (runs `alembic upgrade head` on start) |
| dashboard | 3000 | Next.js web UI                             |
| docs      | 4000 | Nextra documentation site                  |
| worker    | —    | Celery worker running DSPy optimizations   |
| beat      | —    | Celery beat scheduler                      |
| flower    | 5555 | Celery monitoring UI                       |
| postgres  | 5432 | PostgreSQL 16                              |
| redis     | 6379 | Redis 7.4                                  |

### 3. Create an API key

On first run, bootstrap a key through the dashboard at [http://localhost:3000](http://localhost:3000), or from the command line:

```bash
docker compose exec api python -m src create-key --label "my-team"
```

Use the returned `kaizen_...` key as the `X-API-Key` header on all API requests.

### 4. Instrument your application

The SDK is not published to PyPI yet. Install it directly from this repo:

```bash
pip install ./src/sdk                # from a checkout of this repo
# or:
pip install "git+https://github.com/<your-fork>/kaizen.git#subdirectory=src/sdk"
```

Minimal usage:

```python
import kaizen_sdk as kaizen

kaizen.init(
    api_key="kaizen_...",
    base_url="http://localhost:8000",
    feedback_threshold=5,
    teacher_model="openai/gpt-4o",
    judge_model="openai/gpt-4o-mini",
    # Optional — enables auto-PR:
    git_provider="github",            # github | bitbucket_server | gitlab
    git_repo="your-org/your-repo",
    git_base_branch="main",
    git_token="ghp_...",
)

# Wrap an LLM call — the SDK records inputs/outputs into a per-request buffer
result = await kaizen.trace("summarize_ticket", chain.ainvoke, {"text": "..."})

# When the user rates the response, flush buffered traces with a score in [0, 1]
await kaizen.flush(score=0.85)

# Later, fetch the currently active optimized prompt for a task
prompt = await kaizen.get_prompt("summarize_ticket")
```

The public SDK surface is: `init`, `trace`, `trace_sync`, `flush`, `flush_sync`, `get_prompt`, `get_buffered_traces`, `reset_buffer`, `close`.

## Project Structure

```
kaizen/
├── src/
│   ├── api/          # FastAPI app, routes, auth, schemas
│   ├── models/       # SQLAlchemy ORM models
│   ├── services/     # Git providers (GitHub/Bitbucket/GitLab), auto-PR, prompt file IO
│   ├── worker/       # Celery app, DSPy pipeline, evaluators, cost estimator
│   ├── sdk/          # kaizen_sdk Python package (installable)
│   ├── utils/        # Crypto helpers, PR templates
│   ├── config.py     # pydantic-settings configuration
│   └── __main__.py   # `python -m src create-key` CLI
├── dashboard/        # Next.js 14 web UI
├── docs/             # Nextra documentation site
├── alembic/          # Database migrations
├── tests/            # Pytest suite (api, config, feedback loop)
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## API Endpoints

All endpoints live under `/api/v1/` and require an `X-API-Key` header except where noted. OpenAPI/Swagger is served at `http://localhost:8000/docs` while the API is running.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/health` | Liveness probe (no auth) |
| GET    | `/api/v1/keys/status` | Whether any API key exists (no auth) |
| POST   | `/api/v1/keys/` | Create an API key |
| DELETE | `/api/v1/keys/{id}` | Revoke an API key |
| POST   | `/api/v1/tasks/` | Create a task |
| GET    | `/api/v1/tasks/` | List tasks (cursor paginated) |
| GET    | `/api/v1/tasks/{id}` | Get a single task |
| DELETE | `/api/v1/tasks/{id}` | Delete a task and all related rows |
| POST   | `/api/v1/tasks/{id}/seed` | Upload a JSONL seed dataset |
| POST   | `/api/v1/feedback/` | Submit feedback (auto-creates task by name; auto-triggers optimization at threshold) |
| GET    | `/api/v1/feedback/` | List feedback entries |
| POST   | `/api/v1/traces/` | Ingest a trace |
| POST   | `/api/v1/optimize/{task_id}` | Manually trigger an optimization run |
| GET    | `/api/v1/jobs/{job_id}` | Get optimization job status |
| GET    | `/api/v1/prompts/{task_id}` | Get the active prompt for a task |

## Development

### Install dependencies

```bash
uv sync                         # installs project + dev deps from uv.lock
```

### Run the API locally

```bash
# Bring up only the infrastructure containers
docker compose up -d postgres redis

# Apply migrations
uv run alembic upgrade head

# Run the API with auto-reload
uv run uvicorn src.api.main:app --reload --port 8000

# In another shell: run the Celery worker
uv run celery -A src.worker.celery_app worker -l info
```

### Dashboard and docs

```bash
cd dashboard && npm install && npm run dev     # http://localhost:3000
cd docs      && npm install && npm run dev     # http://localhost:4000
```

### Tests

```bash
uv run pytest
```

`tests/` contains API, config, and end-to-end feedback-loop tests. `pytest-asyncio` is configured via `pyproject.toml`.

### Database migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic downgrade -1
```

The API container runs `alembic upgrade head` on startup, so no manual step is required in the Docker workflow.

## Deployment

The provided `Dockerfile` builds a single Python image (used by `api`, `worker`, and `beat`) via `uv sync --locked --no-dev`. The `dashboard/` and `docs/` directories have their own Dockerfiles.

```bash
docker compose build
docker compose up -d
```

Production considerations:

- Provide a long-lived `GIT_TOKEN_ENCRYPTION_KEY`. Rotating it invalidates previously encrypted Git tokens.
- Override `TEACHER_MODEL`, `JUDGE_MODEL`, `MAX_TRIALS_DEFAULT`, `COST_BUDGET_DEFAULT`, and `OPTIMIZATION_WALL_TIMEOUT` in `.env` to tune optimization behavior and spend.
- Set `SSL_VERIFY=false` only if you are pointing `OPENAI_API_BASE` at an internal, self-signed endpoint.
- `DEFAULT_OPTIMIZER` defaults to `gepa`; set it to `miprov2` to switch back to the MIPROv2 optimizer.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, commit conventions, and PR guidelines.

## License

[MIT](LICENSE)
