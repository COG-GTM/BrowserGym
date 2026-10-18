import types

import pytest

from side_runner.agents import create_agent, register_agent, agent_types
from side_runner.agents.base import Agent, AgentOutput
from side_runner.agents.llm import build_user_content, parse_response
from side_runner.agents.anthropic_agent import AnthropicAgent
from side_runner.agents.openai_agent import OpenAIAgent

import numpy as np


def _obs(**kw):
    obs = {
        "chat_messages": (
            {"role": "assistant", "message": "Hi"},
            {"role": "user", "message": "goal"},
        ),
        "goal_object": ({"type": "text", "text": "goal"},),
        "open_pages_urls": ("http://x/",),
        "open_pages_titles": ("X",),
        "active_page_index": np.asarray([0]),
        "axtree_txt": "RootWebArea 'X'\n\t[12] button 'Go'",
        "pruned_html": "<button bid='12'>Go</button>",
        "screenshot": np.zeros((4, 4, 3), dtype=np.uint8),
        "last_action_error": "",
    }
    obs.update(kw)
    return obs


def test_builtin_registry():
    assert set(agent_types()) >= {"mock", "scripted", "openai", "anthropic"}
    with pytest.raises(ValueError, match="unknown agent type"):
        create_agent({"type": "nope"})
    with pytest.raises(ValueError, match="'type'"):
        create_agent({})


def test_register_custom_agent():
    class Echo(Agent):
        type = "echo-test"

        def get_action(self, obs):
            return AgentOutput("noop()", done=True)

    register_agent("echo-test", Echo)
    assert create_agent({"type": "echo-test"}).get_action({}).done


def test_mock_agent_is_deterministic_and_acks_user_messages():
    agent = create_agent({"type": "mock"})
    obs = _obs()
    outs = [agent.get_action(obs)]
    obs = _obs(chat_messages=obs["chat_messages"] + ({"role": "user", "message": "hello"},))
    assert agent.n_user_msgs_seen == 1
    outs += [agent.get_action(obs) for _ in range(3)]
    assert [o.action for o in outs] == [
        "noop(200)",
        "send_msg_to_user('Received: hello')",
        "scroll(0, 200)",
        "send_msg_to_user('done')",
    ]
    assert [o.done for o in outs] == [False, False, False, True]
    for o in outs:  # every action parses in the shared action set
        agent.action_set.to_python_code(o.action)


def test_mock_agent_fail_at_step():
    agent = create_agent({"type": "mock", "fail_at_step": 2})
    agent.get_action(_obs())
    with pytest.raises(RuntimeError, match="step 2"):
        agent.get_action(_obs())


def test_scripted_agent():
    agent = create_agent({"type": "scripted", "actions": ["click('12')", "noop()"]})
    a, b = agent.get_action(_obs()), agent.get_action(_obs())
    assert (a.action, a.done, b.action, b.done) == ("click('12')", False, "noop()", True)
    with pytest.raises(ValueError):
        create_agent({"type": "scripted"})
    with pytest.raises(ValueError):
        create_agent({"type": "scripted", "actions": [""]})


def test_parse_response():
    assert parse_response('I will click.\n```click("12")```') == ('click("12")', "I will click.")
    assert parse_response("```python\nnoop()\n```") == ("noop()", None)
    assert parse_response("noop()") == ("noop()", None)


def test_prompt_contents():
    agent = create_agent({"type": "mock"})
    parts = build_user_content(_obs(), agent.action_set, [], use_axtree=True, use_screenshot=True)
    text = "\n".join(p.get("text", "") for p in parts)
    assert "# Goal\ngoal" in text and "[12] button 'Go'" in text and "send_msg_to_user" in text
    assert any(p["type"] == "image" for p in parts)
    parts = build_user_content(
        _obs(), agent.action_set, ["noop()"], use_axtree=False, use_screenshot=False
    )
    text = "\n".join(p.get("text", "") for p in parts)
    assert "<button bid='12'>" in text and "History of past actions" in text
    assert not any(p["type"] == "image" for p in parts)


def test_llm_agents_require_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        create_agent({"type": "openai"})
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        create_agent({"type": "anthropic"})


def test_openai_agent_with_fake_client():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        msg = types.SimpleNamespace(content='The button is 12.\n```click("12")```')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    agent = OpenAIAgent(
        {"type": "openai", "model": "gpt-test", "use_screenshot": True}, client=client
    )
    out = agent.get_action(_obs())
    assert (out.action, out.thought, out.done) == ('click("12")', "The button is 12.", False)
    assert calls[0]["model"] == "gpt-test"
    user = calls[0]["messages"][1]["content"]
    assert any(
        p["type"] == "image_url" and p["image_url"]["url"].startswith("data:image/jpeg")
        for p in user
    )


def test_anthropic_agent_with_fake_client():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        block = types.SimpleNamespace(type="text", text='Done.\n```send_msg_to_user("ok")```')
        return types.SimpleNamespace(content=[block])

    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    agent = AnthropicAgent({"type": "anthropic", "use_screenshot": True}, client=client)
    out = agent.get_action(_obs())
    assert out.action == 'send_msg_to_user("ok")' and out.done
    assert calls[0]["model"] == AnthropicAgent.default_model
    content = calls[0]["messages"][0]["content"]
    assert any(p["type"] == "image" and p["source"]["media_type"] == "image/jpeg" for p in content)
