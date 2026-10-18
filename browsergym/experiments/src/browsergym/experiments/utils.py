import logging
import time
from collections.abc import Sequence
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# rough average for English text, used when no tokenizer is available (e.g., offline)
APPROX_CHARS_PER_TOKEN = 4


# seconds before retrying to load a tokenizer that failed to load (e.g., transient network error)
ENCODING_RETRY_DELAY = 60.0

_encodings: dict[str, tiktoken.Encoding] = {}
_encoding_failures: dict[str, float] = {}


def _get_encoding(model: str) -> tiktoken.Encoding | None:
    if model in _encodings:
        return _encodings[model]
    failed_at = _encoding_failures.get(model)
    if failed_at is not None and time.monotonic() - failed_at < ENCODING_RETRY_DELAY:
        return None
    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception as e:  # unknown model, or BPE file not cached and no network access
        if failed_at is None:
            logger.warning(
                "Could not load the tiktoken encoding for model %r (%s: %s). "
                "Token counts will be approximated (%d characters per token).",
                model,
                type(e).__name__,
                e,
                APPROX_CHARS_PER_TOKEN,
            )
        _encoding_failures[model] = time.monotonic()
        return None
    _encoding_failures.pop(model, None)
    _encodings[model] = encoding
    return encoding


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
