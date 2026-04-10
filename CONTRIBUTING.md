# Contributing to Kaizen

Thank you for your interest in contributing to Kaizen! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Podman or Docker
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Local Development

```bash
git clone https://github.com/YOUR_USERNAME/kaizen.git
cd kaizen
cp .env.example .env

# Start infrastructure
podman-compose up -d postgres redis

# Install Python dependencies
uv sync

# Run API locally
uvicorn src.api.main:app --reload --port 8000

# Run worker
celery -A src.worker.celery_app worker -l info

# Dashboard
cd dashboard && npm install && npm run dev

# Docs
cd docs && npm install && npm run dev
```

### Running Tests

```bash
# Python tests
uv run pytest

# With coverage
uv run pytest --cov=src
```

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/YOUR_USERNAME/kaizen/issues)
- Include steps to reproduce, expected behavior, and actual behavior
- For security vulnerabilities, please email directly instead of opening a public issue

### Pull Requests

1. Fork the repository
2. Create a feature branch from `main`: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `uv run pytest`
5. Run linting: `ruff check src/`
6. Commit with a descriptive message
7. Push to your fork and open a PR against `main`

### Commit Messages

We follow conventional commits:

```
feat: add new evaluator type
fix: resolve trailing slash redirect issue
docs: update SDK quickstart guide
chore: update dependencies
```

### Code Style

- Python: [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- TypeScript: Prettier + ESLint (dashboard)
- No unnecessary comments or docstrings on obvious code
- Tests for new features

## Architecture Overview

```
src/
  api/          # FastAPI REST endpoints
  models/       # SQLAlchemy ORM models
  services/     # Git providers, prompt file handling, auto-PR
  worker/       # Celery tasks, DSPy optimization pipeline
  sdk/          # kaizen_sdk Python package
  utils/        # Crypto, PR templates
dashboard/      # Next.js web UI
docs/           # Nextra documentation site
```

## Areas for Contribution

- New git providers (GitLab support)
- Additional evaluator types
- Dashboard improvements
- Documentation and tutorials
- Performance optimization
- Testing coverage

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
