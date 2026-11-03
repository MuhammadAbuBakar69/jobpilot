from jobpilot.extract import (
    FASTROUTER_BASE,
    OPENAI_BASE,
    parse_with_llm,
    resolve_llm_config,
)

POSTING = "Frontend Developer at Acme\nStack: React\nhttps://acme.example/1"


def test_no_key_means_disabled():
    cfg = resolve_llm_config({})
    assert cfg.enabled is False
    assert cfg.base_url == OPENAI_BASE


def test_fastrouter_key_selects_fastrouter_and_prefixed_model():
    cfg = resolve_llm_config({"FASTROUTER_API_KEY": "sk-or-v1-demo"})
    assert cfg.api_key == "sk-or-v1-demo"
    assert cfg.base_url == FASTROUTER_BASE
    assert cfg.model == "openai/gpt-4o-mini"


def test_openai_key_keeps_openai_base_and_plain_model():
    cfg = resolve_llm_config({"OPENAI_API_KEY": "sk-proj-demo"})
    assert cfg.base_url == OPENAI_BASE
    assert cfg.model == "gpt-4o-mini"


def test_explicit_base_url_and_model_win():
    cfg = resolve_llm_config(
        {
            "FASTROUTER_API_KEY": "k",
            "OPENAI_BASE_URL": "http://localhost:11434/v1/",
            "JOBPILOT_MODEL": "llama3.1",
        }
    )
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.model == "llama3.1"


def test_github_shaped_token_is_refused():
    # a GitHub token exported under an LLM key name is a misconfiguration
    cfg = resolve_llm_config({"OPENAI_API_KEY": "ghp_notanllmkey"})
    assert cfg.enabled is False


def test_parse_with_llm_without_key_uses_heuristics():
    posting = parse_with_llm(POSTING, config=resolve_llm_config({}))
    assert posting.source == "manual"
    assert posting.company == "Acme"
