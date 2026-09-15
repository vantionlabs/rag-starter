# Evals

A regression gate for the RAG pipeline: run it before you ship a change to a
prompt, a model, chunking or retrieval, and in CI.

## Run

Needs a real Postgres with pgvector and an LLM key, because it runs the whole
pipeline: retrieval, the grounded agent and citation validation.

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run python -m evals.run_eval                    # exits 1 on a regression
uv run python -m evals.run_eval --threshold 0.9
```

It ingests `fixtures/*.md` for a throwaway user, runs every case in
`test-set.csv`, prints a line per case and writes a JSON report to
`evals/reports/`.

## The test set

`test-set.csv` uses the columns of the free
[eval test set template](https://github.com/vantionlabs/eval-test-set-template):

| Column | Used for |
| --- | --- |
| `context_ref` | The fixture an answer must come from, or `none` when the documents do not cover the question and the answer must say so |
| `must_include` | Terms the answer must contain, separated by `\|`. Use `[1]` to require a citation |
| `must_not_include` | Terms that must never appear |
| `severity` | `critical` failures fail the run regardless of the pass rate |
| `grading` | `deterministic`, `rubric` or `both`. Rubric grading of `expected_behaviour` needs a model judge and is reported as pending |

A case passes when the checks in `checks.py` all hold: a covered question is
answered, its citations verify, its source was retrieved and the required
terms are there; an uncovered question is declined; no forbidden term appears.
The run fails on any critical failure or when the pass rate drops below the
threshold.

## Extend

- Replace `fixtures/` with your own documents and write cases against them.
  Add a row for every wrong answer you see in real use, then fix it.
- For model-graded rubric scoring, baselines per category and cost tracking,
  use the Vantion eval harness.
