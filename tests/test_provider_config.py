from src import config
from src.evaluator import read_eval_dataset


def test_provider_is_inferred_from_model_name():
    assert config.provider_for_model("gpt-4.1-mini") == "openai"
    assert config.provider_for_model("gemini-3.5-flash") == "gemini"
    assert config.provider_for_model("claude-sonnet-5") == "anthropic"


def test_provider_models_are_only_available_with_a_key():
    assert config.available_models(api_key="", provider="gemini") == ["mock-model"]
    assert config.GEMINI_MODEL_A in config.available_models(api_key="test-key", provider="gemini")


def test_unknown_model_cost_is_not_misattributed():
    assert config.estimate_cost("unknown-provider-model", 1000, 1000) == 0.0


def test_evaluation_dataset_can_be_loaded_from_jsonl():
    data = (
        b'{"question":"Can I close my account?","expected_answer":"Settle the loan",'
        b'"expected_source":"Closure Policy","category":"Closure","should_escalate":false}\n'
    )
    frame = read_eval_dataset("cases.jsonl", data)
    assert len(frame) == 1
    assert bool(frame.iloc[0]["should_escalate"]) is False
