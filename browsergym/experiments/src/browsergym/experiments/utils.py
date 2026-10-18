import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# rough average for English text, used when no tokenizer is available (e.g., offline)
APPROX_CHARS_PER_TOKEN = 4


@lru_cache(maxsize=None)
def _get_encoding(model: str) -> tiktoken.Encoding | None:
    try:
        return tiktoken.encoding_for_model(model)
    except Exception as e:  # unknown model, or BPE file not cached and no network access
        logger.warning(
            "Could not load the tiktoken encoding for model %r (%s: %s). "
            "Token counts will be approximated (%d characters per token).",
            model,
            type(e).__name__,
            e,
            APPROX_CHARS_PER_TOKEN,
        )
        return None


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count the number of tokens in a text.

    Falls back to a character-based approximation if the tokenizer cannot be loaded.
    """
    encoding = _get_encoding(model)
    if encoding is None:
        return -(-len(text) // APPROX_CHARS_PER_TOKEN)  # ceil division
    return len(encoding.encode(text))


def count_messages_token(messages: Sequence[Any], model: str = "gpt-4") -> int:
    """Count the number of tokens in a list of messages.

    Args:
        messages (list): a list of messages, each message can be a string or a
            list of dicts or an object with a content attribute.
        model (str): the model to use for tokenization.

    Returns:
        int: the number of tokens.
    """
    token_count = 0
    for message in messages:
        if hasattr(message, "content"):
            message = message.content
        elif isinstance(message, dict) and "content" in message:
            message = message["content"]

        if isinstance(message, str):
            token_count += count_tokens(message, model)
        # handles messages with image content
        elif isinstance(message, (list, tuple)):
            for part in message:
                if not isinstance(part, dict):
                    raise ValueError(
                        f"The message is expected to be a list of dicts, but got list of {type(part)}"
                    )
                if part["type"] == "text":
                    token_count += count_tokens(part["text"], model)
        else:
            raise ValueError(
                f"The message is expected to be a string or a list of dicts, but got {type(message)}"
            )
    return token_count
