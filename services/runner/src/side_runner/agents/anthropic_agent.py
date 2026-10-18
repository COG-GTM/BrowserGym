from typing import Any

from .llm import LLMAgent


class AnthropicAgent(LLMAgent):
    type = "anthropic"
    title = "Anthropic Claude (AXTree + optional screenshot)"
    models = ("claude-sonnet-4-5", "claude-opus-4-1", "claude-3-5-haiku-latest")
    api_key_env = "ANTHROPIC_API_KEY"
    model_env = "SIDE_ANTHROPIC_MODEL"
    default_model = "claude-sonnet-4-5"
    max_tokens = 1024

    def make_client(self):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "anthropic agent requires `pip install side-runner[anthropic]`"
            ) from e
        return anthropic.Anthropic()

    @staticmethod
    def to_anthropic_content(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for part in content:
            if part["type"] == "image":
                out.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": part["data"],
                        },
                    }
                )
            else:
                out.append({"type": "text", "text": part["text"]})
        return out

    def complete(self, system: str, content: list[dict[str, Any]]) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": self.to_anthropic_content(content)}],
        )
        return "".join(
            getattr(block, "text", "") for block in response.content if block.type == "text"
        )
