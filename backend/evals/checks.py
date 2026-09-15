"""Scoring for one eval case, kept free of the database and the model so it is
unit-tested in the offline lane (tests/test_eval_checks.py).

Test sets use the columns of the Vantion eval test set template
(github.com/vantionlabs/eval-test-set-template): `must_include` and
`must_not_include` hold terms separated by `|`, `context_ref` names the source
document an answer must come from, or `none` when the documents do not cover
the question and the right behaviour is to say so.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

SEVERITIES = ("critical", "high", "medium", "low")


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    input: str
    context_ref: str
    expected_behaviour: str
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...]
    grading: str
    severity: str

    @property
    def expects_no_answer(self) -> bool:
        return self.context_ref.strip().lower() in ("", "none")


@dataclass
class Outcome:
    """What the pipeline did for one case."""

    answer: str
    insufficient_evidence: bool
    grounded: bool
    retrieved_filenames: set[str]


@dataclass
class Score:
    case_id: str
    severity: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    rubric_pending: bool = False


def _terms(value: str) -> tuple[str, ...]:
    return tuple(t.strip() for t in value.split("|") if t.strip())


def load_cases(path: Path) -> list[Case]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    cases = []
    for row in rows:
        severity = row["severity"].strip().lower()
        if severity not in SEVERITIES:
            raise ValueError(f"{row['id']}: severity must be one of {SEVERITIES}")
        cases.append(
            Case(
                id=row["id"].strip(),
                category=row["category"].strip(),
                input=row["input"],
                context_ref=row.get("context_ref", "").strip(),
                expected_behaviour=row.get("expected_behaviour", ""),
                must_include=_terms(row.get("must_include", "")),
                must_not_include=_terms(row.get("must_not_include", "")),
                grading=row.get("grading", "deterministic").strip().lower(),
                severity=severity,
            )
        )
    return cases


def score(case: Case, outcome: Outcome) -> Score:
    """Deterministic checks. Rubric grading of `expected_behaviour` needs a model
    judge and is flagged as pending rather than silently counted as a pass."""
    failures: list[str] = []
    answer = outcome.answer.lower()

    if case.expects_no_answer:
        if not outcome.insufficient_evidence:
            failures.append("answered a question the documents do not cover")
    else:
        if outcome.insufficient_evidence:
            failures.append("reported insufficient evidence for a covered question")
        if not outcome.grounded:
            failures.append("citations did not verify")
        ref = Path(case.context_ref).name
        if ref and ref not in outcome.retrieved_filenames:
            failures.append(f"expected source {ref} was not retrieved")
        missing = [t for t in case.must_include if t.lower() not in answer]
        if missing:
            failures.append(f"missing required terms: {', '.join(missing)}")

    forbidden = [t for t in case.must_not_include if t.lower() in answer]
    if forbidden:
        failures.append(f"contains forbidden terms: {', '.join(forbidden)}")

    return Score(
        case_id=case.id,
        severity=case.severity,
        passed=not failures,
        failures=failures,
        rubric_pending=case.grading in ("rubric", "both"),
    )


@dataclass
class GateResult:
    passed: bool
    pass_rate: float
    failed_critical: list[str]


def gate(scores: list[Score], threshold: float) -> GateResult:
    """Fail on any critical failure, or when the pass rate drops below the threshold."""
    total = len(scores)
    passed = sum(s.passed for s in scores)
    rate = passed / total if total else 0.0
    critical = [s.case_id for s in scores if s.severity == "critical" and not s.passed]
    return GateResult(
        passed=not critical and rate >= threshold, pass_rate=rate, failed_critical=critical
    )
