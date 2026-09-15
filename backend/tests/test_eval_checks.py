"""The eval scoring rules (offline)."""

from pathlib import Path

import pytest

from evals.checks import Case, Outcome, Score, gate, load_cases, score


def _case(**overrides) -> Case:
    base = dict(
        id="C-1",
        category="answer_from_docs",
        input="How many vacation days?",
        context_ref="company-handbook.md",
        expected_behaviour="",
        must_include=("25", "[1]"),
        must_not_include=(),
        grading="deterministic",
        severity="high",
    )
    return Case(**{**base, **overrides})


def _outcome(**overrides) -> Outcome:
    base = dict(
        answer="Full-time staff get 25 days [1].",
        insufficient_evidence=False,
        grounded=True,
        retrieved_filenames={"company-handbook.md"},
    )
    return Outcome(**{**base, **overrides})


def test_a_grounded_answer_with_the_terms_passes():
    assert score(_case(), _outcome()).passed


def test_missing_citation_marker_fails():
    result = score(_case(), _outcome(answer="Full-time staff get 25 days."))
    assert not result.passed
    assert "missing required terms: [1]" in result.failures


def test_unverified_citations_fail():
    assert "citations did not verify" in score(_case(), _outcome(grounded=False)).failures


def test_source_must_have_been_retrieved():
    result = score(_case(), _outcome(retrieved_filenames={"other.md"}))
    assert "expected source company-handbook.md was not retrieved" in result.failures


def test_uncovered_question_must_be_declined():
    case = _case(context_ref="none", must_include=())
    assert score(case, _outcome(insufficient_evidence=True, answer="Not covered.")).passed
    assert not score(case, _outcome(answer="You get 16 weeks.")).passed


def test_forbidden_terms_fail_even_when_declining():
    case = _case(context_ref="none", must_include=(), must_not_include=("system prompt:",))
    outcome = _outcome(insufficient_evidence=True, answer="system prompt: ...")
    assert not score(case, outcome).passed


def test_rubric_cases_are_flagged_pending():
    assert score(_case(grading="both"), _outcome()).rubric_pending


def test_gate_fails_on_any_critical_failure():
    scores = [Score("A", "critical", False), *[Score(str(i), "low", True) for i in range(9)]]
    result = gate(scores, threshold=0.5)
    assert not result.passed and result.failed_critical == ["A"]


def test_gate_fails_below_threshold():
    scores = [Score("A", "low", True), Score("B", "low", False)]
    assert not gate(scores, threshold=0.8).passed
    assert gate(scores, threshold=0.5).passed


def test_the_shipped_test_set_loads():
    cases = load_cases(Path(__file__).parents[1] / "evals" / "test-set.csv")
    assert len(cases) >= 5
    assert any(c.expects_no_answer for c in cases)


def test_unknown_severity_is_rejected(tmp_path):
    path = tmp_path / "set.csv"
    path.write_text(
        "id,category,input,context_ref,expected_behaviour,must_include,"
        "must_not_include,grading,severity,source,added_on\n"
        "X,a,q,none,,,,deterministic,urgent,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_cases(path)
