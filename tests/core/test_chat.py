import os

import pytest

from browsergym.core.chat import Chat

__HEADLESS = False if "DISPLAY_BROWSER" in os.environ else True

TRICKY_MSG = "it's \"quoted\" \\ back`slash` ${x}\nline two </script> é 漢字 😀 \u2028 \U000e0041"


@pytest.fixture(params=[True, False], ids=["modern", "classic"])
def modern(request):
    return request.param


@pytest.fixture
def chat(modern):
    chat = Chat(headless=__HEADLESS, modern=modern)
    yield chat
    chat.close()


def _texts(chat: Chat, selector: str, modern: bool) -> list[str]:
    # the modern chatbox renders newlines as <br>, the classic one keeps them as text
    prop = "innerText" if modern else "textContent"
    return chat.page.eval_on_selector_all(selector, f"els => els.map(e => e.{prop})")


def test_invalid_role_raises(chat):
    with pytest.raises(ValueError, match="Invalid role"):
        chat.add_message("bogus", "hello")
    assert chat.messages == []
    assert chat.page.locator("#chatBody .message").count() == 0


def test_recorded_roles(chat, modern):
    for role in ("user", "user_image", "assistant", "info", "infeasible"):
        chat.add_message(role, f"{role} message")

    assert [m["role"] for m in chat.messages] == ["user", "user_image", "assistant", "infeasible"]
    assert [m["message"] for m in chat.messages] == [
        "user message",
        "user_image message",
        "assistant message",
        "infeasible message",
    ]
    assert all(isinstance(m["timestamp"], float) for m in chat.messages)

    # info messages are displayed in the debug area only
    assert _texts(chat, "#chatDebug .info-message", modern) == ["info message"]
    assert chat.page.locator("#chatBody .message").count() == 4
    assert _texts(chat, "#chatBody .assistant-message", modern) == [
        "assistant message",
        "infeasible message",
    ]
    assert chat.page.locator("#chatBody .user-message img").get_attribute("src") == (
        "user_image message"
    )


def test_tricky_message_is_rendered_verbatim(chat, modern):
    chat.add_message("assistant", TRICKY_MSG)

    assert chat.messages[-1]["message"] == TRICKY_MSG
    assert _texts(chat, "#chatBody .assistant-message", modern) == [TRICKY_MSG]


def test_user_message_from_chatbox(chat):
    result = chat.page.evaluate("send_user_message('hi from js')")

    assert result[0] == "user"
    assert result[2] == "hi from js"
    assert len(result[1].split(":")) == 2
    assert chat.messages[-1]["role"] == "user"
    assert chat.messages[-1]["message"] == "hi from js"


def test_wait_for_user_message(chat, modern):
    chat.page.evaluate("USER_MESSAGE_RECEIVED = true;")
    chat.page.evaluate(
        """setTimeout(() => {
            const box = document.getElementById('inputBox');
            box.value = 'typed by the user';
            box.dispatchEvent(new KeyboardEvent('keypress', {key: 'Enter'}));
        }, 200);"""
    )
    chat.wait_for_user_message()

    assert chat.page.evaluate("USER_MESSAGE_RECEIVED") is True
    assert chat.messages == [
        {"role": "user", "timestamp": chat.messages[0]["timestamp"], "message": "typed by the user"}
    ]
    assert _texts(chat, "#chatBody .user-message", modern) == ["typed by the user"]
    assert chat.page.input_value("#inputBox") == ""


def test_classic_chatbox_assistant_image():
    chat = Chat(headless=__HEADLESS, modern=False)
    try:
        content = chat.page.content()
        assert "<ASSISTANT_IMAGE_URL>" not in content
        assert 'const assistant_image_data = "data:image/png;base64,' in content
        chat.add_message("assistant", "hello")
        src = chat.page.locator("#chatBody .assistant-image").get_attribute("src")
        assert src.startswith("data:image/png;base64,")
    finally:
        chat.close()
