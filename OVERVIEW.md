# OVERVIEW — Kaizen

A detailed architectural overview of the Kaizen repository.

---

## 1. Project Summary

Kaizen is a **self-hosted continuous prompt-optimization platform** for teams running LLM-powered applications. Its purpose is to close the feedback → optimization → deployment loop for prompts without requiring engineers to manage DSPy programs, training scripts, or prompt-hosting infrastructure by hand.

Functionally, the repository provides:

1. A **Python SDK** (`src/sdk/kaizen_sdk/`) that an application imports to buffer per-request LLM traces and ship them to the Kaizen API together with a user-provided score.
2. A **FastAPI HTTP API** (`src/api/`) that ingests feedback, auto-creates or resolves tasks, and enforces an auto-trigger threshold that dispatches optimization jobs.
3. A **Celery worker** (`src/worker/`) that runs DSPy-based optimization pipelines (GEPA by default, MIPROv2 optional), produces a dual score (dataset metric + independent LLM judge), and versions the resulting prompt.
4. A **Git-provider abstraction** (`src/services/`) that, when configured, commits the optimized prompt back into the caller's repository and opens a pull request on GitHub, Bitbucket Server, or GitLab (GitLab is a stub).
5. A **Next.js dashboard** (`dashboard/`) for task/job inspection, prompt version diffs, and API-key management.
6. A **Nextra documentation site** (`docs/`) deployed to GitHub Pages via `.github/workflows/docs.yml`.

Domain responsibilities inferred from the code: prompt lifecycle management (draft → active), feedback ingestion with rolling-window thresholds, cost-bounded optimization runs, dual-score prompt evaluation, encrypted Git-token storage, and per-task Git-provider configuration.

---

## 2. Technology Stack

Sources: `pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`, `dashboard/package.json`, `docs/package.json`, `alembic.ini`, `.github/workflows/docs.yml`.

### Backend (Python)

| Layer | Component | Version | Role |
|-------|-----------|---------|------|
| Language | Python | `>=3.12,<3.13` | Primary runtime; 3.13 explicitly excluded |
| Web API | FastAPI | 0.135.1 | HTTP interface, dependency injection, OpenAPI |
| ASGI server | Uvicorn | 0.42.0 | Production/dev ASGI host |
| Async HTTP | httpx | ≥0.27 | Outbound calls (SDK, test client) |
| ORM | SQLAlchemy | 2.0.48 (async) | Database access, declarative models |
| DB driver | psycopg[binary] | 3.3.3 | Async and sync PostgreSQL driver (`psycopg_async` in `database.py`) |
| Migrations | Alembic | 1.18.4 | 15 migrations under `alembic/versions/` |
| Settings | pydantic-settings | 2.13.1 | `.env`-backed configuration (`src/config.py`) |
| Validation | Pydantic v2 | (via pydantic-settings) | Request/response schemas in `src/api/schemas.py` |
| Queue | Celery | 5.6.3 | Background optimization jobs |
| Broker | Redis | ≥7.4.0 | Celery broker + prompt cache + threshold lock |
| Result backend | PostgreSQL (via `db+...`) | — | Durable Celery result storage |
| LLM routing | LiteLLM | 1.80.12 | Unified client for OpenAI-compatible endpoints |
| Optimization | DSPy | 3.1.3 | GEPA and MIPROv2 optimizers |
| Crypto | cryptography | 42.0.5 | Fernet symmetric encryption for Git tokens |
| GitHub SDK | PyGithub | 2.3.0 | Used by `GitHubProvider` |
| File uploads | python-multipart | ≥0.0.22 | Seed dataset uploads |

### SDK (`src/sdk/`)

A separately-packaged distribution (`hatchling` build backend, `pyproject.toml` at `src/sdk/`) that only depends on `httpx` and `pydantic`. It supports Python 3.10+, i.e. a wider range than the server, so that consumers on older runtimes can integrate.

### Frontend (`dashboard/`)

| Component | Version | Role |
|-----------|---------|------|
| Next.js | 14.2.21 (App Router) | UI framework |
| React | 18.3.1 | Rendering |
| TanStack Query | 5.62.0 | Server-state caching, polling |
| Radix UI | 1.x | Accessible dialog/slot primitives |
| Tailwind CSS | 3.4.17 | Styling |
| class-variance-authority, clsx, tailwind-merge | — | shadcn/ui-style className composition |
| Recharts | 2.15.0 | Score trend charts |
| lucide-react | 0.469.0 | Icon set |
| TypeScript | 5.7 | Typing |

### Documentation site (`docs/`)

- Next.js 14 + Nextra 4.6 + `nextra-theme-docs` 4.6
- Runs on port 4000; deployed to GitHub Pages via `.github/workflows/docs.yml` (Node 20, static export)

### Dev tooling

- **uv** (Astral) as the Python package manager, pinned via `uv.lock` and consumed in the Dockerfile (`uv sync --locked --no-dev`)
- **pytest 9** + **pytest-asyncio 1.3** for tests (configured in `pyproject.toml`)
- No Ruff/Black/Prettier/ESLint configuration is committed; `dashboard/package.json` exposes `next lint` only
- `.github/workflows/docs.yml` is the only CI workflow in the repo

### External integrations

- **OpenAI-compatible LLM endpoints** via LiteLLM (configurable base URL — supports corporate/self-signed endpoints through `SSL_VERIFY=false`)
- **GitHub, Bitbucket Server, GitLab** via `src/services/*_provider.py`
- **GitHub webhook signature secret** (`GITHUB_WEBHOOK_SECRET`) is defined in settings but no webhook route is registered under `src/api/routes/`

---

## 3. Repository Structure

```
kaizen/
├── src/                              # Backend Python package
│   ├── __init__.py
│   ├── __main__.py                   # CLI: `python -m src create-key --label ...`
│   ├── config.py                     # pydantic-settings Settings class
│   ├── database.py                   # Async SQLAlchemy engine + Redis client
│   ├── api/
│   │   ├── main.py                   # FastAPI app, CORS, router registration
│   │   ├── auth.py                   # X-API-Key dependency, SHA-256 hashing
│   │   ├── errors.py                 # Exception handlers
│   │   ├── schemas.py                # Pydantic request/response models
│   │   └── routes/                   # feedback, jobs, keys, optimize, prompts, seed, tasks, traces
│   ├── models/
│   │   └── base.py                   # Task, FeedbackEntry, PromptVersion,
│   │                                 # OptimizationJob, Trace, ApiKey
│   ├── services/
│   │   ├── git_provider.py           # GitProvider ABC + factory
│   │   ├── github_provider.py        # PyGithub-backed implementation
│   │   ├── bitbucket_provider.py     # Bitbucket Server REST via httpx
│   │   ├── gitlab_provider.py        # Stub (44 lines)
│   │   ├── github_pr.py              # Legacy GitHub PR path (still in tree)
│   │   ├── auto_pr.py                # Provider-agnostic orchestrator with retry
│   │   └── prompt_file.py            # Python AST / YAML / JSON / text IO
│   ├── worker/
│   │   ├── celery_app.py             # Celery config (Redis broker, PG result backend)
│   │   ├── tasks.py                  # run_optimization Celery task
│   │   ├── pipeline.py               # 956-line DSPy pipeline state machine
│   │   ├── evaluators.py             # judge / exact_match / custom_fn / composite
│   │   ├── cost_estimator.py         # Pre-dispatch USD estimate
│   │   └── logging_config.py
│   ├── sdk/                          # Installable kaizen-sdk package
│   │   ├── pyproject.toml            # Hatchling build; httpx+pydantic only
│   │   ├── kaizen_sdk/               # Public module
│   │   │   ├── core.py               # New minimal API: init/trace/flush/get_prompt
│   │   │   ├── async_client.py       # Legacy AsyncCTClient
│   │   │   ├── client.py             # Legacy CTClient
│   │   │   ├── instrument.py         # Legacy instrument() helper
│   │   │   ├── detect.py             # Prompt-source detection (AST)
│   │   │   ├── models.py             # Pydantic result types
│   │   │   ├── exceptions.py         # CT* exception hierarchy
│   │   │   └── cache.py
│   │   └── tests/                    # SDK-only unit tests
│   └── utils/
│       ├── crypto.py                 # Fernet encrypt/decrypt for Git tokens
│       └── pr_template.py            # PR title + body builders
├── dashboard/                        # Next.js 14 web UI
│   ├── src/app/                      # App Router pages (login, tasks/[taskId], settings)
│   ├── src/components/               # Feature components + ui/ primitives
│   ├── src/lib/                      # api.ts (fetch client), hooks.ts (react-query),
│   │                                 # auth.tsx, providers.tsx, utils.ts
│   └── public/                       # Own copy of kaizen.png
├── docs/                             # Nextra 4.6 documentation site
│   └── content/                      # getting-started, api, sdk, tutorials (mdx)
├── alembic/
│   ├── env.py
│   └── versions/                     # 15 migrations (001–015)
├── tests/
│   ├── conftest.py                   # Mock DB session, authed/unauthed ASGI clients
│   ├── test_api.py                   # 390 lines — route-level tests
│   ├── test_feedback_loop.py         # 416 lines — end-to-end feedback flow
│   ├── test_config.py
│   └── fixtures/gepa_kwr_analyze_test.json
├── assets/                           # kaizen.png, idea.png, idea.excalidraw
├── .github/workflows/docs.yml        # GitHub Pages deploy (docs site only)
├── alembic.ini
├── docker-compose.yml                # 8 services
├── Dockerfile                        # Backend image (api, worker, beat share it)
├── pyproject.toml
├── uv.lock
├── .env.example
├── CONTRIBUTING.md
├── README.md
└── LICENSE                           # MIT, 2026 Emirhan Gazi
```

### Architectural patterns

- **Layered backend**: `routes` → `services` / `worker` → `models` → database. Dependency direction is strict: `models` never imports `api` or `worker`; `services` stays unaware of FastAPI.
- **Ports-and-adapters for Git**: `git_provider.GitProvider` ABC is implemented once per host (`github_provider.py`, `bitbucket_provider.py`, `gitlab_provider.py`) and selected via `get_git_provider(provider_type, ...)`. Higher layers depend only on the interface.
- **Pipeline state machine**: the optimization pipeline in `worker/pipeline.py` is expressed as an explicit `PENDING → RUNNING → EVALUATING → COMPILING → SUCCESS / FAILURE / PR_FAILED` progression with a `progress_step` string at each sub-phase (`loading_data`, `building_trainset`, `configuring_dspy`, `running_gepa` / `running_miprov2`, `saving_compiled_state`, `judge_evaluation`, `completed` / `error` / `pr_creation_failed`).
- **Async API / sync worker split**: the API uses `sqlalchemy.ext.asyncio` + `psycopg_async`; the Celery pipeline explicitly creates a separate sync engine because async engines cannot be used inside Celery tasks (an inline comment calls this out as "Pitfall 7").

---

## 4. Core Architecture Components

### 4.1 API layer (`src/api/`)

`main.py` constructs a single `FastAPI(title="Kaizen")` app, registers `CORSMiddleware(allow_origins=["*"])`, mounts an exception-handler set from `errors.py`, exposes a public `/health`, and includes eight routers:

| Router | Prefix | Purpose |
|--------|--------|---------|
| `tasks` | `/api/v1/tasks` | Create / list / get / delete tasks; `TaskSummary` joins feedback counts, last optimization, and active-prompt score via three subqueries |
| `feedback` | `/api/v1/feedback` | Ingest feedback, auto-create tasks by name, run the auto-trigger check |
| `prompts` | `/api/v1/prompts` | Read the active prompt for a task (Redis cache, 5-min TTL) |
| `jobs` | `/api/v1/jobs` | Return job status from Postgres, retry-PR |
| `optimize` | `/api/v1/optimize` | Manually trigger an optimization job |
| `seed` | `/api/v1/tasks/{id}/seed` | JSONL upload to bootstrap cold-start tasks (seeds do not count toward auto-trigger) |
| `traces` | `/api/v1/traces` | Trace ingestion and scoring |
| `keys` | `/api/v1/keys` | Create / list / revoke API keys; public `status` endpoint for bootstrap UX |

All authenticated routes depend on `require_api_key` (`auth.py`), which SHA-256-hashes the incoming `X-API-Key` header and looks it up in `api_keys` where `revoked_at IS NULL`.

### 4.2 Data model (`src/models/base.py`)

Six tables, all with UUID primary keys and timezone-aware `created_at`:

| Table | Purpose | Notable columns |
|-------|---------|----------------|
| `tasks` | One per optimizable task | `name` (unique), `schema_json` (JSONB), `feedback_threshold`, `evaluator_config`, `optimizer_type` (default `'gepa'`), `gepa_config`, `mode` (`optimize_only` / `auto_pr` / `pr_preview`), `git_*` columns, `prompt_file`, `prompt_locator`, `existing_prompt_text`, legacy `github_*` aliases |
| `feedback_entries` | Scored examples | `inputs`, `output`, `score`, `source` (`sdk` / `user_rating` / `auto_eval` / `seed`), indexed on `(task_id, created_at)` |
| `prompt_versions` | Optimization output | `version_number`, `prompt_text`, `original_prompt`, `dspy_state_json`, `eval_score`, `judge_score`, `status` (`draft` / `active`), `optimizer`, `dspy_version` |
| `optimization_jobs` | One per run | `status` (7-state FSM), `triggered_by`, `progress_step`, `pr_url`, `error_message`, `job_metadata` (JSONB for cost, tokens, versions) |
| `traces` | Raw LLM traces | `prompt_text`, `response_text`, `model`, `tokens`, `latency_ms`, `source_file`, `source_variable`, `score`, `scored_by` |
| `api_keys` | Key registry | `key_hash` (SHA-256, unique), `label`, `revoked_at` |

The 15 Alembic migrations record the evolution: evaluator config (002), job metadata (003), prompt-store versioning (004), GitHub-PR config (005), traces table (006), prompt-file columns (007), auto-eval flags (008), provider-agnostic Git columns (009), judge score (010), task mode (011), original prompt (012), optimizer type (013 + 014 flipping default to GEPA), and SDK-captured prompt text (015).

### 4.3 Optimization pipeline (`src/worker/pipeline.py`)

The core subsystem. Public entry point: `run_optimization_pipeline(task_id: str, job_id: str) -> dict`, called from the `run_optimization` Celery task.

Sequence:

1. **Create a sync SQLAlchemy engine** against the same `DATABASE_URL` (psycopg sync driver). Load `Task` and `OptimizationJob` rows.
2. **Transition to `RUNNING` / `loading_data`**. If `task.feedback_source == 'traces'`, load from the `traces` table (and optionally auto-evaluate unscored rows via `batch_evaluate_traces`); otherwise load from `feedback_entries`.
3. Build `dspy.Example` objects shaped by `task.schema_json` (input fields) plus a `response` output field.
4. **20/80 train/val split** (20% train, 80% validation — this is explicitly the chosen split).
5. **Configure DSPy** with `dspy.LM(teacher_model, api_key=..., api_base=..., timeout=LLM_TIMEOUT)`. Seed the signature's `instructions` with the existing prompt loaded from the repo (via the Git provider) or, as a fallback, from the latest DB version / SDK-captured text.
6. Pick the module type (`dspy.Predict` or `dspy.ChainOfThought`) from `task.module_type`.
7. Build the metric function via `create_evaluator(task, settings)`.
8. Select optimizer by `task.optimizer_type` (falling back to `settings.DEFAULT_OPTIMIZER`, currently `gepa`):
   - **GEPA**: wraps the evaluator to return `ScoreWithFeedback`, passes `auto` level and `reflection_lm=teacher_lm`, `track_stats=True`.
   - **MIPROv2**: `num_candidates=MAX_TRIALS_DEFAULT`, `max_bootstrapped_demos=1`, `max_labeled_demos=1`, minibatch validation.
9. Save compiled state as **JSON only** (`save_program=False` — never pickled) into a temp file, then load it into `dspy_state_json`.
10. **Dual scoring**: `dataset_score` from `optimizer.best_score` (or sampled re-evaluation), plus an **independent LLM-judge** pass over up to 10 validation examples, returning `judge_score` in `[0, 1]`.
11. Insert `PromptVersion(status='draft')` with `optimizer`, `dspy_version`, scores, and the full DSPy state.
12. Update the job with cost/tokens/duration captured by a litellm success-callback cost tracker (`_CostTracker`), then transition `SUCCESS / completed`.
13. **Post-success routing** based on `task.mode`:
    - `optimize_only` — stop; prompt stays in `draft`.
    - `pr_preview` — build PR title/body + actual file diff through the Git provider, store preview data in `job_metadata['pr_preview']`.
    - `auto_pr` — low-quality gate (skip if both scores < 0.3), otherwise call `create_optimization_pr(...)` with retry/backoff; on PR failure mark `PR_FAILED` but preserve the PromptVersion.

### 4.4 Background jobs and scheduling

- `src/worker/celery_app.py` configures Celery with `broker_transport_options={"visibility_timeout": 7200}`, `task_time_limit=5400`, `task_soft_time_limit=5100`, JSON serializer, UTC.
- `src/worker/tasks.py` declares `run_optimization` with `acks_late=True`, `reject_on_worker_lost=True`, and `time_limit = OPTIMIZATION_WALL_TIMEOUT + 60` (= 1860 s) as a hard kill. The task body imports the pipeline lazily to avoid circular imports.
- `docker-compose.yml` also runs `celery ... beat` as a `beat` service, sharing the same image, but the codebase does not currently declare scheduled (periodic) tasks — the beat process has no tasks to dispatch by itself.

### 4.5 LLM abstraction layer

All LLM traffic funnels through LiteLLM:

- `dspy.LM(model, api_key, api_base, timeout, extra_body={...})` for teacher models.
- `litellm.completion(model=judge_model, ...)` for judge evaluation.
- `litellm.success_callback` is appended with a per-run `_CostTracker.success_callback` that aggregates `usage.total_tokens` and `_hidden_params['response_cost']` into `job_metadata`.
- When `SSL_VERIFY=false`, `litellm.ssl_verify` is disabled and `litellm.client_session` is replaced with `httpx.Client(verify=False)` — enabling use against corporate / self-signed endpoints.

### 4.6 Git-provider adapters (`src/services/`)

`GitProvider` (ABC) exposes five operations: `validate_access`, `read_file(path, ref) -> FileContent`, `create_branch`, `commit_file(..., sha=None)`, `create_pr(title, body, head, base) -> PRResult`, `find_open_pr(head, base)`.

- `GitHubProvider` uses PyGithub.
- `BitbucketServerProvider` hits the Bitbucket Data Center REST API directly via httpx, with SSL verification controlled by `ssl_verify`.
- `GitLabProvider` is present but is a 44-line stub — calling it will surface a `GitProviderError` for most operations.
- `auto_pr.create_optimization_pr` orchestrates retries (`MAX_RETRIES=3`, exponential backoff capped at `BACKOFF_MAX=30s`) and deduplicates against an already-open PR.

Prompt file IO is decoupled in `prompt_file.py`: format auto-detected from extension (`.py` → AST, `.yaml/.yml` → PyYAML, `.json` → dot-path traversal, `.txt` → whole file). Python replacement operates on byte offsets from the AST node, so surrounding code and formatting are preserved.

### 4.7 Python SDK (`src/sdk/kaizen_sdk/`)

Two concentric APIs:

1. **Minimal API (`core.py`)** — the current surface promoted by the server:
   - `init(api_key, base_url, *, git_provider, git_base_url, git_token, git_project, git_repo, git_base_branch, feedback_threshold, teacher_model, judge_model, mode, optimizer_type, gepa_config)` — module-level state.
   - `trace(name, fn, inputs, **overrides) -> Any` and `trace_sync(...)` — run `fn(inputs)`, extract text output (handles strings, objects with `.content`, OpenAI-style `choices[0].message.content`), and append a `BufferedTrace` to a `ContextVar` per request.
   - `flush(score) / flush_sync(score)` — POST each buffered trace to `/api/v1/feedback/`, merging per-task overrides and optionally attaching the prompt text read locally via the same AST-based `detect._parse_file_assignments`.
   - `get_prompt(name)` — look up the task by name, then fetch the active prompt.
   - `get_buffered_traces() / reset_buffer() / close()`.
2. **Legacy client API**: `CTClient`, `AsyncCTClient`, `instrument()`, `detect_prompt_source()`, and Pydantic result models (`Task`, `Prompt`, `Job`, `PromptVersion`, `FeedbackResult`, `CostEstimate`, `OptimizeResult`, `TraceResult`). Kept in tree for backward compatibility; covered by the SDK's own `src/sdk/tests/`.

### 4.8 UI layer (`dashboard/`)

Next.js 14 App Router. The home view shows activity feed, jobs table, and score charts; `tasks/[taskId]/` hosts prompt history, prompt-diff, and a PR-preview modal. Server state is managed by TanStack Query with a `Providers` wrapper. The API client (`lib/api.ts`) reads the API key from `localStorage.ct_api_key` and sends it as `X-API-Key`; `API_BASE` switches between `NEXT_PUBLIC_CT_API_URL` (browser) and `CT_API_URL` (server-side, defaults to `http://api:8000` inside the compose network).

### 4.9 Request lifecycle

End-to-end feedback path:

```
App ──kaizen.trace()─▶ SDK buffer (ContextVar per request)
App ──kaizen.flush(score)─▶ POST /api/v1/feedback/
        │
        ▼
FastAPI  ──_resolve_task──▶ Task (auto-create by name if missing)
        ├─ insert FeedbackEntry
        └─ _check_auto_trigger
              ├─ count live (source != 'seed') entries since last SUCCESS
              ├─ acquire Redis lock  lock:optimize:{task_id}  nx=True ex=300
              ├─ check no active OptimizationJob (PENDING/RUNNING/EVALUATING/COMPILING)
              ├─ insert OptimizationJob(status='PENDING', triggered_by='auto_threshold')
              └─ run_optimization.delay(task_id, job_id)
                      │
                      ▼
              Celery worker ──▶ pipeline (sync engine)
                      ├─ state machine + dual scoring
                      ├─ insert PromptVersion(status='draft')
                      └─ if mode in (auto_pr, pr_preview): GitProvider → PR
```

---

## 5. Key Features

Inferred from the code rather than advertised:

- **Auto-trigger with rolling window**: feedback counts reset after each `SUCCESS` completion, so the threshold is "new entries since last optimization", not lifetime count.
- **Duplicate-dispatch protection**: a Redis `SET NX EX 300` lock on `lock:optimize:{task_id}` plus an active-status query prevents two workers from racing at the threshold boundary.
- **Cold-start seeding**: JSONL upload at `/api/v1/tasks/{id}/seed`; seeds are stored with `source='seed'` and deliberately do not count toward the auto-trigger threshold but do populate the training set.
- **Dual-score evaluation**: dataset metric score + independent judge score, each stored on `PromptVersion` and surfaced to the PR body.
- **Evaluator variety**: `judge` (LLM-as-judge with 3-call majority vote and anti-verbosity instruction), `exact_match`, `custom_fn` (imported Python function), `composite` (weighted combination). Defaults to `judge`.
- **Conservative seeded optimization**: the compiled DSPy signature inherits the project's existing prompt as `instructions`, and MIPROv2 is called with `max_bootstrapped_demos=1`, `max_labeled_demos=1`.
- **Prompt-version drafting**: every optimization run creates a `draft`. Promotion to `active` is the gating step — either by merging the PR or by flipping status via the API.
- **Prompt-file format pluralism**: `.py` / `.yaml` / `.json` / `.txt` all supported for read and write. Python uses AST + byte-offset replacement to preserve surrounding code.
- **Multiple run modes**: `optimize_only` (no PR), `pr_preview` (preview bundled into `job_metadata`), `auto_pr` (real PR).
- **Cost tracking**: pre-dispatch estimate via `cost_estimator.py` + per-run actuals via litellm success callback; both land in `job_metadata`.
- **Per-request buffering in the SDK**: the SDK uses `ContextVar` so concurrent requests don't mix traces, and `get_buffered_traces()` enables SSE streaming UIs.
- **Backwards-compatible migrations**: `Task` keeps `github_repo` / `github_base_branch` / `github_token_encrypted` alongside the provider-agnostic `git_*` columns.

---

## 6. Configuration & Environment Management

### `.env.example` (root)

Establishes the Docker-Compose-friendly defaults:

```
POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/continuous_tune
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=db+postgresql+psycopg://postgres:postgres@postgres:5432/continuous_tune
API_HOST=0.0.0.0
API_PORT=8000
OPENAI_API_KEY=sk-placeholder
GIT_TOKEN_ENCRYPTION_KEY=
```

### `Settings` class (`src/config.py`)

A single `pydantic-settings` class loads `.env` with `case_sensitive=False` and `extra="ignore"`. Notable groups:

| Group | Variables |
|-------|-----------|
| Storage | `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| API | `API_HOST`, `API_PORT`, `PROMPT_CACHE_TTL=300`, `FEEDBACK_RETENTION_LIMIT=1000` |
| LLM | `OPENAI_API_KEY`, `OPENAI_API_BASE`, `SSL_VERIFY=true` |
| Webhooks | `GITHUB_WEBHOOK_SECRET` (declared but no route consumes it) |
| Seeding | `SEED_SIZE_LIMIT=1000` |
| Optimization | `TEACHER_MODEL=gpt-4o`, `JUDGE_MODEL=gpt-4o-mini`, `COST_BUDGET_DEFAULT=5.0`, `MAX_TRIALS_DEFAULT=15`, `LLM_TIMEOUT=120`, `OPTIMIZATION_WALL_TIMEOUT=1800`, `DEFAULT_OPTIMIZER=gepa`, `GEPA_AUTO=medium` |
| Git | `GIT_PROVIDER=github`, `GIT_BASE_URL`, `GIT_TOKEN`, `GIT_PROJECT`, `GIT_REPO`, `GIT_BASE_BRANCH=main`, `GIT_TOKEN_ENCRYPTION_KEY` |
| Legacy Git | `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BASE_BRANCH`, `GITHUB_TOKEN_ENCRYPTION_KEY` (fallbacks) |

### Dynamic / per-task config

Task-level overrides live in the `tasks` table itself: `optimizer_type`, `gepa_config` (JSONB), `teacher_model`, `judge_model`, `cost_budget`, `evaluator_config`, plus the full Git set. The SDK forwards them on first feedback so a task is created with its own defaults.

### Feature flags

- `task.mode` (`optimize_only` / `auto_pr` / `pr_preview`) acts as a per-task runtime flag controlling post-optimization behavior.
- `task.auto_eval` gates automatic scoring of unscored traces at load time.
- `SSL_VERIFY` toggles LiteLLM SSL verification.

### Secrets

- Git tokens are never stored in clear: the API encrypts them with `cryptography.Fernet` (`src/utils/crypto.py`) before writing `git_token_encrypted`. The Fernet key itself comes from `GIT_TOKEN_ENCRYPTION_KEY` (or the legacy `GITHUB_TOKEN_ENCRYPTION_KEY`).
- API keys are stored as SHA-256 hashes only; the raw value is returned exactly once on creation.
- Pydantic `Field(..., repr=False)` is used on raw-token fields (`git_token_raw`, `github_token_raw`) to keep them out of `repr()` / logs.

---

## 7. Deployment & Operations

### Dockerfile (backend)

- Base: `python:3.12-slim`.
- Copies the `ghcr.io/astral-sh/uv:0.8` binary into the image for reproducible installs.
- Two-stage dep install: `uv sync --locked --no-install-project --no-dev` first (cacheable layer), then the full project.
- Adds `curl` for healthchecks.
- Default `CMD` runs `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`, overridden per service in compose.

### `docker-compose.yml` services

| Service | Build | Command | Notes |
|---------|-------|---------|-------|
| `postgres` | `postgres:16` | default | Healthcheck via `pg_isready`; published on 5432 |
| `redis` | `redis:7.4-alpine` | default | Healthcheck via `redis-cli ping`; published on 6379 |
| `api` | root `Dockerfile` | `alembic upgrade head && uvicorn ...` | HTTP healthcheck on `/health`; depends on healthy pg+redis |
| `worker` | root `Dockerfile` | `celery -A src.worker.celery_app worker -l info -Ofair` | Ping-based healthcheck; depends on healthy api |
| `beat` | root `Dockerfile` | `celery -A src.worker.celery_app beat -l info` | Depends on healthy worker |
| `flower` | `mher/flower:2.0` | `celery --broker=... flower --port=5555` | Celery UI on 5555; `restart: unless-stopped` |
| `dashboard` | `./dashboard/Dockerfile` | default | Published on 3000; `CT_API_URL=http://api:8000` in env |
| `docs` | `./docs/Dockerfile` | default | Published on 4000 |

Volumes: `pgdata` persists Postgres.

### CI / CD

Only `.github/workflows/docs.yml` is present. It builds the Nextra site on pushes touching `docs/**` and publishes to GitHub Pages (Node 20, `npm ci`, `npm run build`, static export). No backend CI, linting, or test workflow exists in-repo.

### Runtime / scaling

- **Horizontally scalable** components: `api`, `worker`, `dashboard`, `docs`. Postgres and Redis are single-instance in the compose file.
- **Bounded optimization wall-time**: `task_time_limit=5400 s` in Celery + `OPTIMIZATION_WALL_TIMEOUT=1800 s` hard limit inside `run_optimization` (`time_limit = OPTIMIZATION_WALL_TIMEOUT + 60`).
- **`acks_late=True` + `reject_on_worker_lost=True`** — in-flight jobs are redelivered if a worker dies mid-run, provided the broker's visibility timeout (set to 7200 s) hasn't already elapsed.
- **Prompt cache** in Redis with a 5-minute TTL (`PROMPT_CACHE_TTL=300`) offloads hot prompt reads from Postgres.

### Security posture (see §11 for details)

- API keys hashed, Git tokens Fernet-encrypted, raw tokens `repr=False`.
- `CORSMiddleware(allow_origins=["*"])` is permissive — suitable for dev, requires tightening for production.
- `SSL_VERIFY=false` is available for corporate self-signed LLM endpoints but applies globally to LiteLLM.

---

## 8. Testing Strategy

### Layout

- `tests/conftest.py` — central fixtures: a mock async session (`mock_db`), a fixed test API key (`TEST_API_KEY = "ct_test-key-for-unit-tests"`) hashed into `TEST_API_KEY_ROW`, an authed `client` fixture that overrides `require_api_key` with `_mock_require_api_key`, and an `unauthed_client` that mocks `get_db` but keeps real auth so 401 paths can be exercised.
- `tests/test_config.py` — small sanity test on `Settings`.
- `tests/test_api.py` — 390 lines, route-level behavior with mocked DB.
- `tests/test_feedback_loop.py` — 416 lines, covers the end-to-end feedback → threshold → dispatch logic.
- `tests/fixtures/gepa_kwr_analyze_test.json` — sample payload for GEPA analyze flows.
- `src/sdk/tests/` — SDK-only unit tests (`test_client.py`, `test_async_client.py`, `test_cache.py`, `test_exceptions.py`, `test_models.py`, `test_client_smoke.py`).

### Frameworks

- `pytest 9` + `pytest-asyncio 1.3` (declared in `pyproject.toml` / `src/sdk/pyproject.toml`).
- HTTP-level tests use `httpx.AsyncClient(transport=ASGITransport(app))` — no real HTTP socket.

### Mocking strategy

- Heavy use of `unittest.mock.AsyncMock` and `MagicMock` for `AsyncSession`.
- `app.dependency_overrides` replaces `require_api_key` and `get_db` per fixture, so routes can be tested without Postgres.
- The conftest sets `DATABASE_URL`, `REDIS_URL`, and Celery URLs to a `_test` database before any application import, so configuration loading doesn't depend on the host `.env`.

### What is validated

- Route contract: status codes, shape of responses, auth errors.
- Feedback ingestion: auto-creation of tasks, prompt-metadata backfill, schema-validation paths.
- Auto-trigger: threshold accounting with `source != 'seed'` and rolling-window semantics.

No coverage tooling is wired up in `pyproject.toml` (no `pytest-cov` dep, no `.coveragerc`).

---

## 9. UI Components

### Web dashboard (`dashboard/src/`)

- **App Router routes**: `/` (home), `/login`, `/settings`, `/tasks/[taskId]/`.
- **Feature components**: `app-shell.tsx`, `sidebar.tsx`, `activity-feed.tsx`, `jobs-table.tsx`, `status-badge.tsx`, `task-card.tsx`, `threshold-bar.tsx`, `prompt-history.tsx`, `prompt-diff.tsx`, `pr-preview-modal.tsx`, `score-chart.tsx`.
- **UI primitives**: `src/components/ui/` — shadcn/ui-style wrappers on Radix primitives.
- **Library**:
  - `api.ts` — typed `fetch` wrapper that reads `ct_api_key` from `localStorage` and sends `X-API-Key`; `API_BASE` depends on whether it runs in the browser (uses `NEXT_PUBLIC_CT_API_URL`) or the Node runtime (uses `CT_API_URL`).
  - `hooks.ts` — TanStack Query hooks for tasks/jobs/prompts.
  - `auth.tsx` + `providers.tsx` — auth context + query-client provider.
- **Styling**: Tailwind 3.4 with `class-variance-authority` / `clsx` / `tailwind-merge` for component variants.

### Documentation site (`docs/`)

Nextra-themed Next.js site with content authored in MDX under `docs/content/{getting-started,api,sdk,tutorials}` and a global `_meta.js` per section.

---

## 10. Performance & Scalability

Evidence-based observations:

- **Async I/O end-to-end in the API**: `create_async_engine` + `async_sessionmaker(expire_on_commit=False)` in `database.py`; all route handlers are `async def`; Redis is accessed via `redis.asyncio`.
- **Sync isolation in the worker**: `_get_sync_engine()` uses `pool_pre_ping=True`; async engines are deliberately not shared to avoid event-loop cross-contamination with DSPy.
- **Redis caching**: `prompts.py` caches the active prompt JSON for `PROMPT_CACHE_TTL` (5 min). Invalidated wherever the active prompt changes (cache-key `prompt:active:{task_id}`).
- **Cursor-based pagination**: `GET /api/v1/tasks/` accepts a `cursor` of `created_at` and bounds `limit` to `[1, 200]`, avoiding offset scans.
- **Indexed hot paths**: `ix_feedback_entries_task_created` and `ix_traces_task_created` back the most common queries (per-task time-ordered scans).
- **Bounded optimization runs**: `MAX_TRIALS_DEFAULT=15`, wall timeout 1800 s, judge evaluation capped at 10 validation examples. These directly constrain cost.
- **Celery fair scheduling**: worker started with `-Ofair`, so long tasks don't starve shorter ones within a single worker.
- **Cost metadata captured per run** via `_CostTracker` — enables operators to observe trend and decide when to scale up teacher/judge models.
- **Single-tenant by design**: there is no `organization_id` or tenant scoping in the schema or auth layer. All API-key holders see the same task/feedback universe.

---

## 11. Security Considerations

- **API key auth** (`src/api/auth.py`): keys are generated as `kaizen_ + secrets.token_hex(16)`, stored only as SHA-256 hashes, and checked with `revoked_at IS NULL` at every request. The raw key is returned exactly once by `POST /api/v1/keys/` or the CLI.
- **Bootstrap UX**: `GET /api/v1/keys/status` is unauthenticated and returns only a boolean/count so the dashboard can show a first-run screen without exposing keys.
- **Git token encryption at rest**: Fernet symmetric encryption in `src/utils/crypto.py`. The key is required (`ValueError` raised if unset). Decrypt happens only where the token is needed (pipeline / retry-PR).
- **Input validation**: Pydantic v2 enforces types, regex patterns (e.g. `optimizer_type=r"^(miprov2|gepa)$"`, `git_provider=r"^(github|bitbucket_server|gitlab)$"`), and bounds (`score ∈ [0, 1]`, `feedback_threshold ≥ 1`).
- **Task schema enforcement**: `feedback` route rejects inputs whose field set doesn't exactly match `task.schema_json` (422 on missing or extra fields), with an explicit carve-out for auto-created tasks where the schema is inferred.
- **SQL injection protections**: every DB access goes through SQLAlchemy Core / ORM with parameterized queries; no string-built SQL.
- **CORS**: permissive `allow_origins=["*"]` in `main.py`. Acceptable for development, should be restricted in production deployments.
- **Container surface**: the Dockerfile installs `--no-dev` and runs as the default (non-root not explicitly set); an explicit `USER` directive would harden the image further.
- **Dependency pinning**: both Python (`uv.lock`) and the dashboard (`package-lock.json`) pin exact versions. No Dependabot/renovate config is committed.
- **Repr-safe secrets**: raw tokens are declared with `Field(..., repr=False)` in schemas so they don't leak via `repr()` or Pydantic debug output.

Areas to watch, based on what is present or absent:

- No rate limiting on the API.
- No audit log for key usage.
- `GITHUB_WEBHOOK_SECRET` is declared but unused — no webhook consumer exists in the codebase.
- `SSL_VERIFY=false` affects all LiteLLM traffic globally when enabled.

---

## 12. Integration Points

### External services

| Service | Component | Wiring |
|---------|-----------|--------|
| OpenAI-compatible LLM provider | `dspy.LM(...)` + `litellm.completion(...)` in `worker/pipeline.py` and `worker/evaluators.py` | `OPENAI_API_KEY`, `OPENAI_API_BASE`, per-model prefixes like `openai/gpt-4o` |
| GitHub.com / GitHub Enterprise | `services/github_provider.py` (PyGithub) | `git_provider='github'`, optional `git_base_url` for GHES |
| Bitbucket Server / Data Center | `services/bitbucket_provider.py` (httpx REST) | `git_provider='bitbucket_server'`, `git_base_url`, `git_project` |
| GitLab | `services/gitlab_provider.py` (stub) | `git_provider='gitlab'` — interface only |
| PostgreSQL | `src/database.py` (async), `worker/pipeline.py::_get_sync_engine` (sync) | `DATABASE_URL` |
| Redis | `redis.asyncio` (`src/database.py`) for API; Celery broker | `REDIS_URL`, `CELERY_BROKER_URL` |

### Internal wiring

- **API → DB**: FastAPI dependency `get_db` yields an `AsyncSession`; `session.commit()` in the finally block, `rollback()` on exception.
- **API → Queue**: `feedback.py` and `optimize.py` call `run_optimization.delay(task_id, job_id)`. The API is producer-only; the worker consumes.
- **API → Redis**: Prompt cache reads/writes in `prompts.py`; auto-trigger lock in `feedback.py`.
- **Worker → DB**: its own sync `Session`, independent of API event loop.
- **Worker → LLM → Git provider**: pipeline invokes LiteLLM for completions, then the `GitProvider` facade for source-repo mutations.
- **SDK → API**: a thin httpx client posting to `/api/v1/feedback/` and reading from `/api/v1/tasks/` + `/api/v1/prompts/`. The SDK does not talk to the worker or queue directly.
- **Dashboard → API**: browser-side fetch with `X-API-Key` from `localStorage`, routed through `NEXT_PUBLIC_CT_API_URL`. TanStack Query handles caching and invalidation.

### Protocols

All external communication is plain HTTPS/HTTP(S) REST. There is no MCP server, gRPC service, or message-bus integration in the repo beyond the Celery/Redis broker and the Postgres result backend.

---

*This document is generated from repository evidence only. When code changes, this file should be regenerated or revised to match.*
