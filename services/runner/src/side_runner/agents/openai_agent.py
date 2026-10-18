from typing import Any

from .llm import LLMAgent


class OpenAIAgent(LLMAgent):
    type = "openai"
    title = "OpenAI (AXTree + optional screenshot)"
    models = ("gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini")
    api_key_env = "OPENAI_API_KEY"
    model_env = "SIDE_OPENAI_MODEL"
    default_model = "gpt-4o-mini"

    def make_client(self):
        try:
            import openai
        except ImportError as e:  # pragma: no cover - depends on optional extra
            raise RuntimeError("openai agent requires `pip install side-runner[openai]`") from e
        return openai.OpenAI()

    @staticmethod
    def to_openai_content(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for part in content:
            if part["type"] == "image":
                url = f"data:image/jpeg;base64,{part['data']}"
                out.append({"type": "image_url", "image_url": {"url": url, "detail": "auto"}})
            else:
                out.append({"type": "text", "text": part["text"]})
        return out

    def complete(self, system: str, content: list[dict[str, Any]]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": self.to_openai_content(content)},
            ],
        )
        return response.choices[0].message.content or ""
