"""Run the eval test set through the real pipeline and gate on the result.

Each case goes through retrieval, the grounded agent and citation validation,
exactly as a chat turn does, and is scored by `evals/checks.py`:

  - a covered question must be answered, cite, verify, retrieve its source
    document and contain the `must_include` terms
  - a question the documents do not cover (`context_ref` = none) must be
    declined, not answered
  - no answer may contain a `must_not_include` term

The run fails (exit code 1) on any critical failure or when the pass rate is
below `--threshold`, so it works as a CI gate. A JSON report is written to
`evals/reports/`.

Needs real services (Postgres with pgvector and an LLM key):

    uv run python -m evals.run_eval
    uv run python -m evals.run_eval --test-set evals/test-set.csv --threshold 0.9

Cases graded `rubric` or `both` are scored on their deterministic checks here;
model-graded rubric scoring comes from the Vantion eval harness.
"""

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.agent.agent import run_turn
from app.agent.deps import AgentDeps
from app.db.engine import SessionLocal
from app.db.models import DocumentChunk, DocumentStatus, SourceDocument, User
from app.grounding.turn_registry import TurnRegistry
from app.grounding.validator import validate
from app.ingestion.chunking import chunk_text
from app.observability.tracing import configure_tracing, flush_tracing
from app.retrieval.embeddings import embed_batch
from evals.checks import Outcome, gate, load_cases, score

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
REPORTS = HERE / "reports"


def seed_corpus(db, user_id: uuid.UUID) -> None:
    """Ingest the fixture documents directly (no R2, no Celery) so the run is
    self-contained."""
    for path in sorted(FIXTURES.glob("*.md")):
        doc = SourceDocument(
            user_id=user_id,
            filename=path.name,
            r2_key=f"eval/{user_id}/{path.name}",
            content_type="text/markdown",
            status=DocumentStatus.processing,
        )
        db.add(doc)
        db.flush()
        chunks = chunk_text(path.read_text(encoding="utf-8"))
        vectors = embed_batch([c.content for c in chunks])
        db.add_all(
            DocumentChunk(
                document_id=doc.id,
                user_id=user_id,
                chunk_index=c.index,
                content=c.content,
                embedding=v,
            )
            for c, v in zip(chunks, vectors, strict=True)
        )
        doc.status = DocumentStatus.ready
    db.commit()


def run(test_set: Path, threshold: float) -> int:
    configure_tracing()
    cases = load_cases(test_set)
    eval_user = uuid.uuid4()

    with SessionLocal() as db:
        # A throwaway user owns the eval corpus, so runs never mix with real data.
        db.add(User(id=eval_user, email=f"eval+{eval_user}@example.com", hashed_password="x"))
        db.commit()
        seed_corpus(db, eval_user)

    scores = []
    for case in cases:
        registry = TurnRegistry()
        deps = AgentDeps(user_id=eval_user, registry=registry)
        answer = run_turn(case.input, [], deps)
        validation = validate(answer, registry, eval_user)
        outcome = Outcome(
            answer=answer.answer,
            insufficient_evidence=answer.insufficient_evidence,
            grounded=validation.ok,
            # What the agent actually retrieved this turn, not a separate search.
            retrieved_filenames={c.filename for c in registry.chunks.values()},
        )
        result = score(case, outcome)
        scores.append(result)
        mark = "pass" if result.passed else "FAIL"
        print(f"{mark:4}  {case.id:10} {case.severity:8} {case.input[:60]}")
        for failure in result.failures:
            print(f"        - {failure}")

    verdict = gate(scores, threshold)
    pending = sum(s.rubric_pending for s in scores)
    print(
        f"\npass rate {verdict.pass_rate:.0%} (threshold {threshold:.0%}), "
        f"critical failures: {len(verdict.failed_critical)}, "
        f"rubric checks pending: {pending}"
    )

    REPORTS.mkdir(exist_ok=True)
    report = REPORTS / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    report.write_text(
        json.dumps(
            {
                "test_set": str(test_set),
                "threshold": threshold,
                "pass_rate": verdict.pass_rate,
                "passed": verdict.passed,
                "failed_critical": verdict.failed_critical,
                "cases": [s.__dict__ for s in scores],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"report: {report}")
    flush_tracing()
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the eval test set and gate on the result.")
    parser.add_argument("--test-set", type=Path, default=HERE / "test-set.csv")
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    raise SystemExit(run(args.test_set, args.threshold))
