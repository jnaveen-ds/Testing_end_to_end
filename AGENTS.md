# Repository working instructions

## Documentation maintenance (required)

Whenever you change application code, configuration, or infrastructure, also
update both of these files in the same change so they never drift from reality:

1. `docs/ARCHITECTURE.md` — component diagram, request lifecycle, file map,
   config table, local↔Azure mapping.
2. `docs/INTERVIEW_NOTES.md` — design-decision rationales (why queue + job row,
   idempotency guard, provider seam, failure handling) with file/function refs.

What counts as a change requiring a docs update:

- Backend: `backend/app/**` (routes, models, tasks, LLM providers, config)
- Frontend: `frontend/src/**`
- CI/CD: `.github/workflows/**`
- Infra: `docker-compose.yml`, `Dockerfile`s, Terraform (when added)
- Tests: add/update the doc references if tests demonstrate new behavior

Small comment/typo fixes don't require doc updates; anything that changes
behavior, topology, configuration, or a documented tradeoff does.

## Project conventions

- All config via environment variables (`backend/app/config.py`); never commit
  real secrets — `.env` is gitignored, `.env.example` documents the shape.
- Default LLM provider is `fake` (deterministic, $0). Azure OpenAI only when
  `LLM_PROVIDER=azure`.
- Tests must not require Docker, Redis, or network: SQLite + fake provider +
  stubbed broker.
- Keep docs claims tied to real files/functions so they stay verifiable.
