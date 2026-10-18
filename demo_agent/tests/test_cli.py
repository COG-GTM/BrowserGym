import pytest
import run_demo
from agent import split_think_action


def test_dry_run_defaults():
    args = run_demo.parse_args(["--dry-run"])
    assert args.command == "run"
    assert args.provider == "mock" and args.model == "mock-deterministic"
    assert args.headless is True and args.max_steps == 10
    assert args.start_url == run_demo.DRY_RUN_PAGE and args.goal


def test_run_defaults(monkeypatch):
    monkeypatch.delenv("DEMO_AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("DEMO_AGENT_MODEL", raising=False)
    args = run_demo.parse_args([])
    assert (args.provider, args.model) == ("openai", "gpt-5-mini")
    assert args.headless is False and args.max_steps == 100
    assert args.start_url == "https://www.google.com" and args.goal is None


def test_env_and_flags(monkeypatch):
    monkeypatch.setenv("DEMO_AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("DEMO_AGENT_MODEL", "claude-haiku-4-5")
    args = run_demo.parse_args(["run", "--headless", "--no-use-axtree", "--use-html"])
    assert (args.provider, args.model) == ("anthropic", "claude-haiku-4-5")
    assert args.headless and args.use_html and not args.use_axtree
    args = run_demo.parse_args(["--model_name", "gpt-4.1", "--provider", "openai"])
    assert args.model == "gpt-4.1"


def test_dry_run_ignores_model_override():
    args = run_demo.parse_args(["--dry-run", "--model", "gpt-5"])
    assert args.provider == "mock" and args.model == "mock-deterministic"


def test_models_subcommand(capsys):
    assert run_demo.main(["models"]) == 0
    assert "gpt-5-mini" in capsys.readouterr().out


def test_missing_key_fails_fast(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert run_demo.main(["run", "--provider", "openai"]) == 2
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().err


def test_agent_args_default_model_follows_provider():
    from agent import DemoAgentArgs

    assert DemoAgentArgs().model_name == "gpt-5-mini"
    assert DemoAgentArgs().agent_name == "DemoAgentArgs"
    assert DemoAgentArgs(provider="anthropic").model_name == "claude-sonnet-4-5"
    assert DemoAgentArgs(provider="mock").make_agent().llm.model == "mock-deterministic"
    explicit = DemoAgentArgs(provider="anthropic", model_name="claude-haiku-4-5")
    assert explicit.model_name == "claude-haiku-4-5"


@pytest.mark.parametrize(
    "text,think,action",
    [
        ("I click.\n```click('12')```", "I click.", "click('12')"),
        ("a\n```python\nnoop()\n```\nb", "a\n\nb", "noop()"),
        ("noop()", "", "noop()"),
    ],
)
def test_split_think_action(text, think, action):
    assert split_think_action(text) == (think, action)
