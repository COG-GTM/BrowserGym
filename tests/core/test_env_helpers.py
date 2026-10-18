import pytest

from browsergym.core.env import _extract_action_exec_timeout, _try_to_extract_legacy_goal

LEGACY_GOAL_WARNING = 'WARNING: This goal cannot be converted to a text-only goal format. Use the new goal format instead ("goal_object" field). Any agent reading this should abort immediately.'


def test_legacy_goal_text_only():
    goal = [
        {"type": "text", "text": "First line."},
        {"type": "text", "text": "Second line\nwith a break."},
    ]
    assert _try_to_extract_legacy_goal(goal) == "First line.\nSecond line\nwith a break."


def test_legacy_goal_text_then_image():
    goal = [
        {"type": "text", "text": "Find this item."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "text", "text": "This text comes after the image."},
    ]
    legacy_goal = _try_to_extract_legacy_goal(goal)
    assert legacy_goal == "Find this item.\n" + LEGACY_GOAL_WARNING
    assert "after the image" not in legacy_goal


def test_legacy_goal_image_first():
    goal = [
        {"type": "image_url", "image_url": "data:image/png;base64,AAAA"},
        {"type": "text", "text": "Ignored."},
    ]
    assert _try_to_extract_legacy_goal(goal) == LEGACY_GOAL_WARNING


def test_legacy_goal_empty():
    assert _try_to_extract_legacy_goal([]) == ""


@pytest.mark.parametrize(
    "action_error,expected",
    [
        # format of playwright>=1.40 (API name prefix)
        (
            'TimeoutError: Locator.click: Timeout 500ms exceeded.\nCall log:\nwaiting for get_by_test_id("14")',
            0.5,
        ),
        ("TimeoutError: Page.goto: Timeout 30000ms exceeded.", 30.0),
        ("TimeoutError: Frame.wait_for_selector: Timeout 1500ms exceeded.", 1.5),
        # legacy format (no API name prefix)
        ("TimeoutError: Timeout 500ms exceeded.\n=========================== logs", 0.5),
        ("", 0),
        ("ValueError: Received an empty action.", 0),
        ("Error: Locator.click: Element is not attached to the DOM\nCall log:", 0),
        # a timeout mentioned by a non-timeout error is not an action timeout
        ("ValueError: TimeoutError: Timeout 500ms exceeded.", 0),
    ],
)
def test_extract_action_exec_timeout(action_error, expected):
    assert _extract_action_exec_timeout(action_error) == expected
