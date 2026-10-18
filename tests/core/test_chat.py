import re
import time
import warnings

import pytest

from browsergym.core.chat import (
    CHATBOX_DIR,
    Chat,
    get_chatbox,
    get_chatbox_classic,
    get_chatbox_modern,
)

XSS_PAYLOAD = '<img src=x onerror="window.__xss = 1"><script>window.__xss = 2</script>'


@pytest.fixture
def chat():
    chat = Chat(headless=True)
    yield chat
    chat.close()


def bubbles(chat, role):
    return chat.page.locator(f'#chatBody article[data-role="{role}"] .msg__bubble')


def type_and_send(chat, text, key="Enter"):
    chat.page.locator("#inputBox").fill(text)
    chat.page.locator("#inputBox").press(key)


def test_single_self_contained_chatbox():
    html = get_chatbox()
    assert get_chatbox_modern(CHATBOX_DIR) == html
    assert get_chatbox_classic(CHATBOX_DIR) == html
    assert not (CHATBOX_DIR / "chatbox_modern.html").is_file()
    # no external resources: no <link>, no remote scripts/styles/fonts
    assert "<link" not in html
    assert "@import" not in html
    assert not re.search(r"""src=["']https?:""", html)
    assert not re.search(r"""url\(["']?https?:""", html)


def test_modern_false_is_deprecated_but_works():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        chat = Chat(headless=True, modern=False)
    try:
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        chat.add_message("assistant", "still works")
        assert bubbles(chat, "assistant").last.inner_text() == "still works"
    finally:
        chat.close()


def test_agent_to_user_messages_render_per_role(chat):
    chat.add_message("assistant", "Hello from the agent")
    chat.add_message("infeasible", "Cannot do that")
    chat.add_message("user", "Hello from python")

    assert bubbles(chat, "assistant").last.inner_text() == "Hello from the agent"
    assert bubbles(chat, "infeasible").last.inner_text() == "Cannot do that"
    assert bubbles(chat, "user").last.inner_text() == "Hello from python"

    meta = chat.page.locator('#chatBody article[data-role="infeasible"] .msg__meta')
    assert "infeasible" in meta.inner_text().lower()
    assert re.fullmatch(r"\d\d:\d\d:\d\d", meta.locator("time").inner_text())

    assert [m["role"] for m in chat.messages] == ["assistant", "infeasible", "user"]


def test_user_to_agent_enter_sends(chat):
    type_and_send(chat, "book the cheapest flight")
    bubbles(chat, "user").last.wait_for()

    assert bubbles(chat, "user").last.inner_text() == "book the cheapest flight"
    assert chat.page.locator("#inputBox").input_value() == ""
    assert chat.page.evaluate("USER_MESSAGE_RECEIVED") is True
    assert chat.messages[-1]["role"] == "user"
    assert chat.messages[-1]["message"] == "book the cheapest flight"


def test_shift_enter_inserts_newline(chat):
    box = chat.page.locator("#inputBox")
    box.click()
    box.type("line one")
    box.press("Shift+Enter")
    box.type("line two")
    assert box.input_value() == "line one\nline two"
    assert chat.messages == []

    box.press("Enter")
    bubbles(chat, "user").last.wait_for()
    assert chat.messages[-1]["message"] == "line one\nline two"
    assert bubbles(chat, "user").last.locator("br").count() == 1


def test_send_button_and_empty_messages(chat):
    send = chat.page.locator("#sendButton")
    assert send.is_disabled()
    type_and_send(chat, "   ")
    assert chat.messages == []

    chat.page.locator("#inputBox").fill("via button")
    assert send.is_enabled()
    send.click()
    bubbles(chat, "user").last.wait_for()
    assert chat.messages[-1]["message"] == "via button"


@pytest.mark.parametrize("role", ["assistant", "user", "infeasible"])
def test_agent_side_html_is_escaped(chat, role):
    chat.add_message(role, XSS_PAYLOAD)
    bubble = bubbles(chat, role).last
    assert bubble.inner_text() == XSS_PAYLOAD
    assert bubble.locator("img, script").count() == 0
    assert chat.page.evaluate("window.__xss") is None


def test_user_typed_html_is_escaped(chat):
    type_and_send(chat, XSS_PAYLOAD)
    bubble = bubbles(chat, "user").last
    bubble.wait_for()
    assert bubble.inner_text() == XSS_PAYLOAD
    assert bubble.locator("img, script").count() == 0
    assert chat.page.evaluate("window.__xss") is None


def test_quotes_and_js_special_chars_round_trip(chat):
    msg = 'it\'s "quoted" `x` \\ ${not_a_template} </script> \u2028 done'
    chat.add_message("info", msg)
    assert chat.page.locator("#chatDebug .info-message__body").last.inner_text() == msg


def test_markdown_rendering(chat):
    chat.add_message(
        "assistant",
        "**bold** and *italic* and `<b>code</b>`\n\n```python\nprint('<hi>')\n```\n"
        "[docs](https://example.com/a?b=1&c=2) [bad](javascript:alert(1))",
    )
    bubble = bubbles(chat, "assistant").last
    assert bubble.locator("strong").inner_text() == "bold"
    assert bubble.locator("em").inner_text() == "italic"
    assert bubble.locator("p code").inner_text() == "<b>code</b>"
    assert bubble.locator("pre code").inner_text() == "print('<hi>')"
    links = bubble.locator("a")
    assert links.count() == 1
    assert links.get_attribute("href") == "https://example.com/a?b=1&c=2"
    assert links.get_attribute("rel") == "noopener noreferrer"
    assert "[bad](javascript:alert(1))" in bubble.inner_text()


def test_user_image(chat):
    pixel = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
        "DwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    chat.add_message("user_image", pixel)
    chat.add_message("user_image", "javascript:alert(1)")
    imgs = chat.page.locator('#chatBody article[data-role="user_image"] img')
    assert imgs.count() == 1
    assert imgs.get_attribute("src") == pixel
    assert imgs.get_attribute("alt")
    assert "unsupported" in bubbles(chat, "user_image").last.inner_text()


def test_info_messages_only_latest_visible(chat):
    chat.add_message("info", "step 1 <b>not bold</b>")
    chat.add_message("info", "step 2")
    infos = chat.page.locator("#chatDebug .info-message")
    assert infos.count() == 2
    assert not infos.nth(0).is_visible()
    assert infos.nth(1).is_visible()
    assert "step 2" in infos.nth(1).inner_text()
    assert infos.nth(0).locator("b").count() == 0
    # info messages are not part of the conversation history
    assert chat.messages == []


def test_thinking_indicator(chat):
    indicator = chat.page.locator("#thinkingIndicator")
    assert indicator.is_hidden()
    chat.add_message("user", "go")
    assert indicator.is_visible()
    assert "thinking" in indicator.inner_text().lower()
    chat.add_message("info", "working")
    assert indicator.is_visible()
    chat.add_message("assistant", "done")
    assert indicator.is_hidden()
    chat.set_thinking(True)
    assert indicator.is_visible()
    chat.set_thinking(False)
    assert indicator.is_hidden()


def test_auto_scroll(chat):
    for i in range(40):
        chat.add_message("assistant", f"message {i}\nwith a second line")
    at_bottom = (
        "(() => { const b = document.getElementById('chatBody');"
        " return b.scrollHeight - b.scrollTop - b.clientHeight < 2; })()"
    )
    chat.page.wait_for_function(at_bottom)
    assert chat.page.locator("#jumpLatest").is_hidden()

    # when the reader scrolled up, new agent messages do not yank the view
    chat.page.evaluate("document.getElementById('chatBody').scrollTop = 0")
    chat.add_message("assistant", "new one")
    assert chat.page.evaluate("document.getElementById('chatBody').scrollTop") == 0
    assert chat.page.locator("#jumpLatest").is_visible()
    chat.page.locator("#jumpLatest").click()
    chat.page.wait_for_function(at_bottom)
    assert chat.page.locator("#jumpLatest").is_hidden()

    # the user's own messages always scroll into view
    chat.page.evaluate("document.getElementById('chatBody').scrollTop = 0")
    type_and_send(chat, "mine")
    chat.page.wait_for_function(at_bottom)


def test_accessibility_attributes(chat):
    page = chat.page
    body = page.locator("#chatBody")
    assert body.get_attribute("role") == "log"
    assert body.get_attribute("aria-live") == "polite"
    assert page.locator("#thinkingIndicator").get_attribute("role") == "status"
    assert page.locator("#chatDebug").get_attribute("aria-live") == "polite"
    assert page.get_by_label("Message", exact=True).count() == 1
    assert page.get_by_role("button", name="Send message").count() == 1
    chat.add_message("assistant", "hi")
    assert page.get_by_role("article").last.get_attribute("aria-label").startswith("Assistant at")


def test_color_scheme(chat):
    page = chat.page
    bg = "getComputedStyle(document.body).backgroundColor"
    page.emulate_media(color_scheme="light")
    light = page.evaluate(bg)
    page.emulate_media(color_scheme="dark")
    dark = page.evaluate(bg)
    assert light != dark
    assert light == "rgb(246, 247, 249)"
    assert dark == "rgb(15, 20, 26)"


def test_legacy_two_argument_add_chat_message(chat):
    chat.page.evaluate("addChatMessage('assistant', 'legacy <i>call</i>')")
    bubble = bubbles(chat, "assistant").last
    assert bubble.inner_text() == "legacy <i>call</i>"
    assert re.fullmatch(
        r"\d\d:\d\d:\d\d",
        chat.page.locator('#chatBody article[data-role="assistant"] time').last.inner_text(),
    )


def test_invalid_role_raises(chat):
    with pytest.raises(ValueError):
        chat.add_message("system", "nope")


def test_wait_for_user_message(chat):
    chat.add_message("assistant", "what next?")
    # simulate the user typing shortly after the wait starts
    chat.page.evaluate(
        "setTimeout(() => {"
        " const box = document.getElementById('inputBox');"
        " box.value = 'next please';"
        " box.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));"
        "}, 300)"
    )
    start = time.time()
    chat.wait_for_user_message()
    assert time.time() - start < 10
    assert chat.messages[-1] == {
        "role": "user",
        "timestamp": chat.messages[-1]["timestamp"],
        "message": "next please",
    }


def test_link_destination_not_formatted(chat):
    chat.add_message(
        "assistant", "see [the *topic*](https://example.com/*topic*?q=**x**) and *after*"
    )
    bubble = bubbles(chat, "assistant").last
    link = bubble.locator("a")
    assert link.get_attribute("href") == "https://example.com/*topic*?q=**x**"
    assert link.locator("em").inner_text() == "topic"
    assert bubble.locator("p > em").inner_text() == "after"


ADVERSARIAL_MESSAGES = [
    '[<img src=x onerror="window.__xss=1">](https://a.com)',
    '[x](https://a.com/"onmouseover="window.__xss=1)',
    "[x](https://a.com/*)<b>*[y](https://b.com/*)</b>",
    '**[x](https://a.com/**" onclick="window.__xss=1**)**',
    "*[a](https://a.com/x*y) *[b](javascript:window.__xss=1)*",
    "[`x`](https://a.com/`<svg onload=window.__xss=1>`)",
    "``` <script>window.__xss=1</script> ```",
    "[x](https://a.com/&quot;onfocus=&quot;window.__xss=1)",
]


@pytest.mark.parametrize("msg", ADVERSARIAL_MESSAGES)
def test_markdown_only_produces_safe_markup(chat, msg):
    chat.add_message("assistant", msg)
    report = chat.page.evaluate("""() => {
            const bubble = [...document.querySelectorAll('#chatBody .msg__bubble')].pop();
            const allowed = {P: [], BR: [], STRONG: [], EM: [], CODE: [], PRE: [],
                             A: ['href', 'target', 'rel']};
            const bad = [];
            for (const el of bubble.querySelectorAll('*')) {
                if (!(el.tagName in allowed)) { bad.push(el.tagName); continue; }
                for (const attr of el.attributes) {
                    if (!allowed[el.tagName].includes(attr.name)) bad.push(el.tagName + '@' + attr.name);
                }
                if (el.tagName === 'A' && !/^https?:\\/\\//.test(el.getAttribute('href'))) bad.push('href');
            }
            return bad;
        }""")
    assert report == []
    assert chat.page.evaluate("window.__xss") is None
