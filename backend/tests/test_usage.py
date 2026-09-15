"""Fast-lane tests for LLM cost computation (no DB, no network)."""

from app.observability.usage import cost_usd


def test_known_model_cost():
    # gpt-4.1: (2.00, 8.00) per 1M
    c = cost_usd("gpt-4.1", input_tokens=1_000_000, output_tokens=1_000_000)
    assert round(c, 4) == 10.0


def test_provider_prefix_stripped():
    assert cost_usd("openai:gpt-4.1", 1_000_000, 0) == 2.0


def test_unknown_model_costs_zero():
    assert cost_usd("some-future-model", 1_000_000, 1_000_000) == 0.0


def test_embedding_cost_input_only():
    # text-embedding-3-small: (0.02, 0.0)
    assert round(cost_usd("text-embedding-3-small", 1_000_000, 0), 4) == 0.02
