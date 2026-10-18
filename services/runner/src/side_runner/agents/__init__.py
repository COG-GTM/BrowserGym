"""Pluggable agent registry.

Register a new agent type with :func:`register_agent` (a class taking the AgentConfig dict).
"""

from typing import Any, Callable

from .base import Agent, AgentOutput

_REGISTRY: dict[str, Callable[[dict], Agent]] = {}


def register_agent(agent_type: str, factory: Callable[[dict], Agent]) -> None:
    _REGISTRY[agent_type] = factory


def agent_types() -> list[str]:
    return list(_REGISTRY)


def create_agent(config: dict[str, Any]) -> Agent:
    if not isinstance(config, dict) or "type" not in config:
        raise ValueError("agent config must be a JSON object with a 'type' field")
    agent_type = config["type"]
    if agent_type not in _REGISTRY:
        raise ValueError(f"unknown agent type {agent_type!r} (available: {', '.join(_REGISTRY)})")
    return _REGISTRY[agent_type](config)


def _register_builtins() -> None:
    from .anthropic_agent import AnthropicAgent
    from .mock import MockAgent
    from .openai_agent import OpenAIAgent
    from .scripted import ScriptedAgent

    for cls in (MockAgent, ScriptedAgent, OpenAIAgent, AnthropicAgent):
        register_agent(cls.type, cls)


_register_builtins()

__all__ = ["Agent", "AgentOutput", "agent_types", "create_agent", "register_agent"]
