# Contributing

Thanks for helping. This is a starter people fork and own, so the bar for a
change is: does it make the default better for most forks, without adding a
service or a concept they have to learn?

## Good contributions

- Bug fixes, especially in retrieval, grounding, ingestion and the event engine.
- Eval cases that catch a real failure (add them to `backend/evals/test-set.csv`).
- Docs that were wrong or missing when you set the starter up.
- Provider support that stays config-only (see `app/llm/providers.py`).

Open an issue before starting something larger, such as a new storage backend,
multi-tenancy or a different frontend, so we can agree it belongs in the
starter rather than in your fork.

## Making a change

1. Read [AGENTS.md](AGENTS.md). Its conventions apply to human and agent
   changes alike.
2. Run the checks before opening a pull request:

   ```bash
   cd backend
   uv run ruff check . && uv run ruff format --check .
   uv run pyright
   uv run pytest -m "not integration"

   cd ../frontend
   pnpm typecheck && pnpm build
   ```

3. If you changed a prompt, a model default or retrieval, run
   `uv run python -m evals.run_eval` and put the before and after pass rates in
   the pull request.
4. Keep pull requests to one change, and say why in the description.

Offline tests must stay offline: anything that needs Postgres, Redis or an LLM
is marked `@pytest.mark.integration`.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).
