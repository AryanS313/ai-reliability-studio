from __future__ import annotations

from datetime import date

from src import config
from src.versioning import build_run_manifest, text_hash, version_hash


def test_unknown_model_has_no_cost_attribution():
    detail = config.estimate_cost_detail("unknown-provider-model", 1000, 1000)
    assert detail["cost"] is None
    assert "No pricing" in detail["warning"]
    assert detail["pricing_source"] is None


def test_known_model_cost_includes_auditable_pricing_provenance():
    detail = config.estimate_cost_detail("gpt-4o-mini", 1000, 1000)
    assert detail["cost"] == 0.00075
    assert detail["pricing_source"].startswith("https://developers.openai.com/")
    assert detail["pricing_effective_date"] == "2026-08-20"


def test_sonnet_standard_rate_does_not_expire_after_cancelled_price_increase(monkeypatch):
    class SeptemberDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 8)

    monkeypatch.setattr(config, "date", SeptemberDate)
    detail = config.estimate_cost_detail("claude-sonnet-5", 1000, 1000)
    assert detail["cost"] == 0.012
    assert detail["pricing_expires_on"] is None
    assert detail["warning"] is None
    assert detail["pricing_effective_date"] == "2026-09-08"


def test_expiry_guard_still_applies_to_an_explicitly_temporary_price(monkeypatch):
    monkeypatch.setitem(
        config.TOKEN_PRICING_PER_1K,
        "temporary-fixture-model",
        {"input": 0.002, "output": 0.01, "effective_date": "2020-01-01", "expires_on": "2020-01-02"},
    )
    assert "expired on 2020-01-02" in config.estimate_cost_detail("temporary-fixture-model", 1000, 1000)["warning"]


def test_version_hashes_are_deterministic_and_sensitive():
    assert version_hash({"b": 2, "a": 1}) == version_hash({"a": 1, "b": 2})
    assert text_hash("one") != text_hash("two")


def test_run_manifest_contains_reproducibility_fields():
    manifest = build_run_manifest(
        prompt={"content": "prompt"},
        dataset={"records": [1]},
        documents=[{"name": "policy"}],
        retrieval={"top_k": 3, "threshold": 0.1},
        target={"version": "t1"},
        evaluators=[{"version": "e1"}],
        model={"provider": "openai", "identifier": "model", "temperature": 0, "seed": 1, "token_limit": 100},
        user_id=1,
        workspace_id=2,
        environment="test",
    )
    for field in ["application_version", "git_commit", "created_at", "environment", "runtime", "manifest_hash"]:
        assert field in manifest
    assert manifest["prompt"]["content_hash"]
    assert manifest["dataset"]["content_hash"]
