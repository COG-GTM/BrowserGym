import ast
import os
import pathlib
import platform
import re

import bs4
import gymnasium as gym
import pytest
from pyparsing.exceptions import ParseException

# register openended gym environments
import browsergym.core
from browsergym.core.action.functions import check, uncheck
from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.core.action.parsers import NamedArgument, highlevel_action_parser
from browsergym.core.constants import BROWSERGYM_ID_ATTRIBUTE as BID_ATTR
from browsergym.utils.obs import flatten_dom_to_str

_IS_MAC_OS = platform.system() == "Darwin"

__SLOW_MO = 1000 if "DISPLAY_BROWSER" in os.environ else None
__HEADLESS = False if "DISPLAY_BROWSER" in os.environ else True
__TIMEOUT = 500

__DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"

TEXTBOX_URL = f"file://{__DATA_DIR}/textbox.html"
EXAMPLE_URL = f"file://{__DATA_DIR}/example.html"
HOVER_URL = f"file://{__DATA_DIR}/hover.html"
DBLCLICK_URL = f"file://{__DATA_DIR}/dblclick.html"
INEXISTANT_FILE_URL = f"file://{__DATA_DIR}/no_file_here.html"
LONG_PAGE_URL = f"file://{__DATA_DIR}/long_page.html"
TEXT_INPUT_URL = f"file://{__DATA_DIR}/input_type/text_input.html"
URL_INPUT_URL = f"file://{__DATA_DIR}/input_type/url_input.html"
CHECKBOX_URL = f"file://{__DATA_DIR}/input_type/checkbox_input.html"
MULTI_IFRAME_URL = f"file://{__DATA_DIR}/basic_iframe_site/basic_iframe_2.html"
OBSTRUCTED_CHECKBOX_URL = f"file://{__DATA_DIR}/obstructed_checkbox_page.html"
LOTS_OF_IFRAMES_URL = f"file://{__DATA_DIR}/lots_of_iframes.html"
SELECT_URL = f"file://{__DATA_DIR}/select.html"
FILE_INPUT_URL = f"file://{__DATA_DIR}/input_type/file_input.html"
DRAG_AND_DROP_URL = f"file://{__DATA_DIR}/drag_and_drop.html"
AUTOCOMPLETE_URL = f"file://{__DATA_DIR}/autocomplete.html"
SCROLLABLE_PANELS_URL = f"file://{__DATA_DIR}/scrollable_panels.html"


def test_action_parser():
    parser = highlevel_action_parser

    with pytest.raises(ParseException):
        function_calls = parser.parse_string("", parseAll=True)
        assert not function_calls

    function_calls = parser.parse_string("a()", parseAll=True)
    assert len(function_calls) == 1

    function_calls = parser.parse_string("  a ( ) \n\n\t", parseAll=True)
    assert len(function_calls) == 1

    function_calls = parser.parse_string("  a ( ) b() \n \tc()", parseAll=True)
    assert [function_name for function_name, _ in function_calls] == ["a", "b", "c"]

    function_calls = parser.parse_string('a(12, 12.2, "text", (1, 2, 3), ["a", 23])', parseAll=True)
    _, function_args = function_calls[0]
    assert function_args == [12, 12.2, "text", (1, 2, 3), ["a", 23]]

    function_calls = parser.parse_string('a(x=12, y = 12.2, other = "text")', parseAll=True)
    _, function_args = function_calls[0]
    assert function_args == [
        NamedArgument(name="x", value=12),
        NamedArgument(name="y", value=12.2),
        NamedArgument(name="other", value="text"),
    ]

    function_calls = parser.parse_string('a(12, y = 12.2, other = "text")', parseAll=True)
    _, function_args = function_calls[0]
    assert function_args == [
        12,
        NamedArgument(name="y", value=12.2),
        NamedArgument(name="other", value="text"),
    ]

    with pytest.raises(ParseException):
        function_calls = parser.parse_string('a(x = 12, 12.2, other = "text")', parseAll=True)

    with pytest.raises(ParseException):
        function_calls = parser.parse_string('a(12, 12.2, 1 = "text")', parseAll=True)

    with pytest.raises(ParseException):
        function_calls = parser.parse_string("a(1-)", parseAll=True)

    with pytest.raises(ParseException):
        function_calls = parser.parse_string("a(1/2)", parseAll=True)

    function_calls = parser.parse_string('a("""\nsome\ntext\\"\\"""")', parseAll=True)
    _, function_args = function_calls[0]
    assert function_args == ['\nsome\ntext""']

    function_calls = parser.parse_string("a('\"some\\ntext\"')", parseAll=True)
    _, function_args = function_calls[0]
    assert function_args == ['"some\ntext"']

    function_calls = parser.parse_string('#comment\na("# not comment") #comment \n ', parseAll=True)
    assert len(function_calls) == 1
    function_name, function_args = function_calls[0]
    assert function_name == "a"
    assert function_args == ["# not comment"]

    function_calls = parser.parse_string('fun(12, x="val", y={"aaa": 23})', parseAll=True)
    function_name, function_args = function_calls[0]
    assert function_name == "fun"
    assert function_args == [
        12,
        NamedArgument(name="x", value="val"),
        NamedArgument(name="y", value={"aaa": 23}),
    ]


def test_valid_action():
    action_set = HighLevelActionSet()

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": CHECKBOX_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def get_checkbox_elem(obs):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        checkbox = soup.find("input", attrs={"type": "checkbox", "id": "vehicle1"})
        return checkbox

    obs, info = env.reset()
    checkbox = get_checkbox_elem(obs)

    # box not checked
    assert not obs["last_action_error"]
    assert not checkbox.has_attr("checked")

    # typo in action (unescaped double quotes)
    action = f"""\
click({repr(checkbox.get(BID_ATTR))}, "17" screen")  # typo here
"""
    with pytest.raises(ValueError):
        python_action = action_set.to_python_code(action)

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # error and box not checked
    assert "Received an empty action." in obs["last_action_error"]
    assert not checkbox.has_attr("checked")

    # click box 1 time
    action = f"""\
click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 1

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box checked
    assert not obs["last_action_error"]
    assert checkbox.has_attr("checked")

    # click box 2 times
    action = f"""\
click({repr(checkbox.get(BID_ATTR))})
click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 2

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box still checked
    assert not obs["last_action_error"]
    assert checkbox.has_attr("checked")

    # click box 3 times
    action = f"""\
click({repr(checkbox.get(BID_ATTR))})
click({repr(checkbox.get(BID_ATTR))})
click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 3

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box unchecked
    assert not obs["last_action_error"]
    assert not checkbox.has_attr("checked")

    # click box 3 times, same line ops
    action = f"""\
click({repr(checkbox.get(BID_ATTR))}) click({repr(checkbox.get(BID_ATTR))}) click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 3

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box checked
    assert not obs["last_action_error"]
    assert checkbox.has_attr("checked")

    # click box 3 times, multi line ops, whitespace, tab, comma in-between args
    action = f"""\
   click(  {repr(checkbox.get(BID_ATTR))} ) click({repr(checkbox.get(BID_ATTR))})\t
                                                  noop() noop () noop( )
   # THIS IS A COMMENT
   noop() # this is a noop() call
click({repr(checkbox.get(BID_ATTR))},   )
#click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 3

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box unchecked
    assert not obs["last_action_error"]
    assert not checkbox.has_attr("checked")

    # click box 3 times, multi line ops, whitespace, tab, comma in-between args, markdown code block
    action = f"""\
Below is code
        ```python
   click(  {repr(checkbox.get(BID_ATTR))} ) click({repr(checkbox.get(BID_ATTR))})\t
                                                  noop() noop () noop( )
   # THIS IS A COMMENT
   noop() # this is a noop() call
click({repr(checkbox.get(BID_ATTR))},   )
#click({repr(checkbox.get(BID_ATTR))})
```
This is not code, just an explanation
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 3

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box checked
    assert not obs["last_action_error"]
    assert checkbox.has_attr("checked")

    # multiple markdown code blocks
    action = f"""\
Below is code
        ```python
                                                  noop() noop () noop( )
   # THIS IS A COMMENT
   noop() # this is a noop() call
click({repr(checkbox.get(BID_ATTR))},   )
#click({repr(checkbox.get(BID_ATTR))})
```
This is not code, just an explanation
Below is more code
        ```python
   click(  {repr(checkbox.get(BID_ATTR))} ) click({repr(checkbox.get(BID_ATTR))})\t
                                                  noop() noop () noop( )
   # THIS IS A COMMENT
   noop() # this is a noop() call
#click({repr(checkbox.get(BID_ATTR))})
```
This is not code, just an explanation
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 3

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box unchecked
    assert not obs["last_action_error"]
    assert not checkbox.has_attr("checked")

    # multiple function calls in the middle of text
    action = f"""\
Let's do a noop(), then noop () noop( ) then click({repr(checkbox.get(BID_ATTR))},   )
#click({repr(checkbox.get(BID_ATTR))})
Now let's do two more
   click(  {repr(checkbox.get(BID_ATTR))} ) click({repr(checkbox.get(BID_ATTR))})\t
                                                  noop() noop () noop( )
   # THIS IS A COMMENT
   noop() # this is a noop() call
#click({repr(checkbox.get(BID_ATTR))})
```
This is not code, just an explanation
This is garbage
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nclick(") == 3

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box checked
    assert not obs["last_action_error"]
    assert checkbox.has_attr("checked")

    env.close()


def test_invalid_action():
    action_set = HighLevelActionSet()

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": CHECKBOX_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )
    obs, info = env.reset()

    # click inexistant bid
    action = f"""\
click("INVALID_BID")
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert "ValueError" in obs["last_action_error"]

    # invalid bid value type
    action = f"""\
click(None)
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert obs["last_action_error"] == "ValueError: expected a string, got None"

    # invalid bid value type
    action = f"""\
click(42.7)
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert obs["last_action_error"] == "ValueError: expected a string, got 42.7"

    # invalid bid value type
    action = f"""\
click([])
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert obs["last_action_error"] == "ValueError: expected a string, got []"

    # invalid bid value type
    action = f"""\
click([42, "a", True, None])
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert obs["last_action_error"] == "ValueError: expected a string, got [42, 'a', True, None]"

    # invalid bid value type
    action = f"""\
click({{}})
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert obs["last_action_error"] == "ValueError: expected a string, got {}"

    # invalid bid value type
    action = f"""\
click({{"k": "aaa"}})
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert obs["last_action_error"] == "ValueError: expected a string, got {'k': 'aaa'}"

    # invalid action args (too many)
    action = f"""\
click("4", "aa", "bb")
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert obs["last_action_error"] == "Error: Locator.click: modifiers: expected array, got string"

    # invalid action args (not enough)
    action = f"""\
click()
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert (
        obs["last_action_error"]
        == "TypeError: click() missing 1 required positional argument: 'bid'"
    )

    # invalid action args (not enough)
    action = f"""\
click()
"""

    obs, reward, term, trunc, info = env.step(action)

    # error
    assert (
        obs["last_action_error"]
        == "TypeError: click() missing 1 required positional argument: 'bid'"
    )

    # invalid action name
    with pytest.raises(NameError):
        action_set.to_python_code(
            f"""\
not_a_valid_action()
"""
        )

    # forbidden fill action
    with pytest.raises(NameError):
        HighLevelActionSet(subsets=["coord"]).to_python_code(
            f"""\
fill("INVALID_BID", "some text")
"""
        )

    # forbidden import
    with pytest.raises(ValueError):
        action_set.to_python_code(
            f"""\
import numpy as np
"""
        )

    # invalid expression, results in empty action
    with pytest.raises(ValueError):
        action_set.to_python_code(
            f"""\
[
"""
        )

    # invalid expression, results in empty action
    with pytest.raises(ValueError):
        action_set.to_python_code(
            f"""\
click
"""
        )

    env.close()


def test_click_through_frames():
    action_set = HighLevelActionSet()

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": MULTI_IFRAME_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    obs, info = env.reset()

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    checkbox = soup.find("input", attrs={"type": "checkbox", "id": "checkbox_2"})

    # box checked
    assert checkbox.has_attr("checked")

    # click box
    action = f"""\
click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    obs, reward, term, trunc, info = env.step(action)

    # no error
    assert not obs["last_action_error"]

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    checkbox = soup.find("input", attrs={"type": "checkbox", "id": "checkbox_2"})

    # box not checked
    assert not checkbox.has_attr("checked")

    env.close()


def test_fill_through_iframe():
    action_set = HighLevelActionSet()

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": MULTI_IFRAME_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    obs, info = env.reset()

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    text_input = soup.find(
        "input", attrs={"type": "text", "placeholder": "Enter text here in iframe"}
    )

    # empty input
    assert text_input.get("value") == ""

    # fill with some text
    action = f"""\
fill({repr(text_input.get(BID_ATTR))}, "This is a test value.")
"""
    python_action = action_set.to_python_code(action)

    obs, reward, term, trunc, info = env.step(action)

    # no error
    assert not obs["last_action_error"]

    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    text_input = soup.find(
        "input", attrs={"type": "text", "placeholder": "Enter text here in iframe"}
    )

    # input filled to desired value
    assert text_input.get("value") == "This is a test value."

    env.close()


def test_click():
    action_set = HighLevelActionSet()

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": CHECKBOX_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def get_checkbox_elem(obs):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        checkbox = soup.find("input", attrs={"type": "checkbox", "id": "vehicle1"})
        return checkbox

    obs, info = env.reset()
    checkbox = get_checkbox_elem(obs)

    # box not checked
    assert not checkbox.has_attr("checked")

    # click box
    action = f"""
click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    obs, reward, terminated, truncated, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # no error
    assert not obs["last_action_error"]

    # box checked
    assert checkbox.has_attr("checked")

    # click box
    action = f"""\
click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # no error
    assert not obs["last_action_error"]

    # box unchecked
    assert not checkbox.has_attr("checked")

    # click box twice
    action = f"""\
click({repr(checkbox.get(BID_ATTR))})
click({repr(checkbox.get(BID_ATTR))})
"""
    python_action = action_set.to_python_code(action)

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # no error
    assert not obs["last_action_error"]

    # box still unchecked
    assert not checkbox.has_attr("checked")

    env.close()


def test_hover():
    action_set = HighLevelActionSet(subsets=["bid", "coord"])

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": HOVER_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def get_button_elem(obs):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        button = soup.find("input", attrs={"type": "button"})
        return button

    obs, info = env.reset()
    button = get_button_elem(obs)

    assert not obs["last_action_error"]
    assert button.get("value") == "Hover me"

    action = f"""
hover({repr(button.get(BID_ATTR))})
"""

    obs, reward, terminated, truncated, info = env.step(action)
    button = get_button_elem(obs)

    assert not obs["last_action_error"]
    assert button.get("value") == "Hello world!"

    action = f"""
mouse_move(0, 0)
"""

    obs, reward, terminated, truncated, info = env.step(action)
    button = get_button_elem(obs)

    assert not obs["last_action_error"]
    assert button.get("value") == "Hover me"

    env.close()


def test_fill_type_press():
    action_set = HighLevelActionSet(subsets=["bid", "coord"])
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEXT_INPUT_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def get_fname_lname_elems(obs):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        fname = soup.find("input", attrs={"id": "fname"})
        lname = soup.find("input", attrs={"id": "lname"})
        return fname, lname

    obs, info = env.reset()
    fname, lname = get_fname_lname_elems(obs)

    # type using bid
    action = f"""
fill({repr(fname.get(BID_ATTR))}, 'Christian')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "Christian"
    assert lname.get("value") == ""

    # type using bid
    action = f"""
fill({repr(lname.get(BID_ATTR))}, 'Clavier')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "Christian"
    assert lname.get("value") == "Clavier"

    # type using focus and keyboard_type
    action = f"""
focus({repr(fname.get(BID_ATTR))}) keyboard_type('Gérard')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "ChristianGérard"
    assert lname.get("value") == "Clavier"

    # type using click and keyboard_insert_text
    action = f"""
click({repr(lname.get(BID_ATTR))}) keyboard_insert_text('Jugnot')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "ChristianGérard"
    assert lname.get("value") == "ClavierJugnot"

    # type using clear and keyboard_insert_text
    action = f"""
clear({repr(lname.get(BID_ATTR))}) keyboard_insert_text('Jugnot')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "ChristianGérard"
    assert lname.get("value") == "Jugnot"

    # type using click, manual clear and keyboard_insert_text
    action = f"""
click({repr(fname.get(BID_ATTR))})
# clear the field
keyboard_press('End')
keyboard_down('Shift')
keyboard_press('Home')
keyboard_up('Shift')
keyboard_press('Backspace')
# insert text
keyboard_insert_text('Gérard')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "Gérard"
    assert lname.get("value") == "Jugnot"

    # fill empty text
    action = f"""
fill({repr(fname.get(BID_ATTR))}, '')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == ""
    assert lname.get("value") == "Jugnot"

    # type in currently focused element
    action = f"""
keyboard_type('Jean')
"""

    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "Jean"
    assert lname.get("value") == "Jugnot"

    # de-focus (click 0, 0), then type text
    action = f"""
mouse_click(0, 0)
"""
    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "Jean"
    assert lname.get("value") == "Jugnot"

    action = f"""
keyboard_type('Reno')
"""
    obs, reward, terminated, truncated, info = env.step(action)
    fname, lname = get_fname_lname_elems(obs)

    assert not obs["last_action_error"]
    assert fname.get("value") == "Jean"
    assert lname.get("value") == "Jugnot"

    env.close()


def test_dblclick():
    action_set = HighLevelActionSet(subsets=["bid"])

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": DBLCLICK_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def get_counter_elem(obs):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        counter = soup.find("span", attrs={"id": "count"})
        return counter

    obs, info = env.reset()
    counter = get_counter_elem(obs)

    # counter starts at 0
    assert not obs["last_action_error"]
    assert counter.text.strip() == "0"

    # test dblclick using bid
    counter_button = counter.find_parent("button", attrs={"id": "dblclick-counter"})
    action = f"""
dblclick({repr(counter_button.get(BID_ATTR))})
"""

    obs, reward, terminated, truncated, info = env.step(action)
    counter = get_counter_elem(obs)

    # counter incremented to 1
    assert not obs["last_action_error"]
    assert counter.text.strip() == "1"

    # test dblclick using bid again
    counter_button = counter.find_parent("button", attrs={"id": "dblclick-counter"})
    action = f"""
dblclick({repr(counter_button.get(BID_ATTR))})
"""

    obs, reward, terminated, truncated, info = env.step(action)
    counter = get_counter_elem(obs)

    # counter incremented to 2
    assert not obs["last_action_error"]
    assert counter.text.strip() == "2"

    env.close()


def test_mouse_dblclick():
    action_set = HighLevelActionSet(subsets=["coord"])

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": DBLCLICK_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def counter():
        return env.unwrapped.page.inner_text("#count")

    def get_counter_coords():
        button = env.unwrapped.page.locator("button")
        box = button.bounding_box()
        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2
        return center_x, center_y

    obs, info = env.reset()

    # counter starts at 0    assert not obs["last_action_error"]
    assert counter() == "0"

    # test mouse_dblclick using coordinates
    counter_x, counter_y = get_counter_coords()
    action = f"""
mouse_dblclick({counter_x}, {counter_y})
"""

    obs, reward, terminated, truncated, info = env.step(action)

    # counter incremented to 1
    assert not obs["last_action_error"]
    assert counter() == "1"

    counter_x, counter_y = get_counter_coords()

    action = f"""
mouse_dblclick({counter_x}, {counter_y})
"""

    obs, reward, terminated, truncated, info = env.step(action)

    # counter incremented to 2
    assert not obs["last_action_error"]
    assert counter() == "2"

    env.close()


# copy/paste text using a sequence of keyboard_press actions
def test_key_press():
    action_set = HighLevelActionSet(subsets=["bid", "coord"])

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEXT_INPUT_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    obs, info = env.reset()

    def get_fname_lname_elems(obs):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        fname = soup.find("input", attrs={"id": "fname"})
        lname = soup.find("input", attrs={"id": "lname"})
        return fname, lname

    fname, lname = get_fname_lname_elems(obs)

    action = f"""
    fill({repr(fname.get(BID_ATTR))}, "Christian")
    keyboard_press({repr("Meta+a" if _IS_MAC_OS else "Control+a")})
    keyboard_press({repr("Meta+c" if _IS_MAC_OS else "Control+c")})
    click({repr(lname.get(BID_ATTR))})
    keyboard_press({repr("Meta+v" if _IS_MAC_OS else "Control+v")})
    """

    obs, reward, terminated, truncated, info = env.step(action)

    assert not obs["last_action_error"]

    fname, lname = get_fname_lname_elems(obs)

    assert lname.get("value") == "Christian"

    env.close()


def test_goto():
    url1 = URL_INPUT_URL
    url2 = TEXT_INPUT_URL

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": url1},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
    )

    obs, info = env.reset()

    assert obs["url"] == url1

    action = f"""
goto({repr(url2)})
"""

    obs, reward, terminated, truncated, info = env.step(action)

    assert not obs["last_action_error"]

    assert obs["url"] == url2

    action = """
go_back()
"""

    obs, reward, terminated, truncated, info = env.step(action)

    assert not obs["last_action_error"]

    assert obs["url"] == url1

    action = """
go_forward()
"""

    obs, reward, terminated, truncated, info = env.step(action)

    assert not obs["last_action_error"]

    assert obs["url"] == url2

    env.close()


def test_scroll():
    action_set = HighLevelActionSet(subsets=["bid", "coord"])

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": LONG_PAGE_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def extract_coords_from_elem(elem):
        return ast.literal_eval(elem.get("center"))

    def get_top_bottom_elems(obs):
        soup = bs4.BeautifulSoup(
            flatten_dom_to_str(
                obs["dom_object"], obs["extra_element_properties"], with_center_coords=True
            ),
            "lxml",
        )
        top = soup.find("input", attrs={"type": "checkbox", "id": "top"})
        bottom = soup.find("input", attrs={"type": "checkbox", "id": "bottom"})
        return top, bottom

    obs, info = env.reset()
    top, bottom = get_top_bottom_elems(obs)
    top_x, top_y = extract_coords_from_elem(top)
    bottom_x, bottom_y = extract_coords_from_elem(bottom)

    # top not checked
    assert not top.has_attr("checked")
    # bottom not checked
    assert not bottom.has_attr("checked")

    # click top
    action = f"mouse_click({repr(top_x)}, {repr(top_y)})"

    obs, reward, terminated, truncated, info = env.step(action)

    top, bottom = get_top_bottom_elems(obs)
    top_x, top_y = extract_coords_from_elem(top)
    bottom_x, bottom_y = extract_coords_from_elem(bottom)

    # no error
    assert not obs["last_action_error"]
    # top checked
    assert top.has_attr("checked")
    # bottom not checked
    assert not bottom.has_attr("checked")

    top, bottom = get_top_bottom_elems(obs)
    top_x, top_y = extract_coords_from_elem(top)
    bottom_x, bottom_y = extract_coords_from_elem(bottom)

    # click bottom
    action = f"mouse_click({repr(bottom_x)}, {repr(bottom_y)})"

    obs, reward, terminated, truncated, info = env.step(action)

    top, bottom = get_top_bottom_elems(obs)
    top_x, top_y = extract_coords_from_elem(top)
    bottom_x, bottom_y = extract_coords_from_elem(bottom)

    # no error (click coordinates out of viewport is a silent fail in playwright)
    assert not obs["last_action_error"]
    # top checked
    assert top.has_attr("checked")
    # bottom not checked (click didn't go through)
    assert not bottom.has_attr("checked")

    # scroll up
    action = f"scroll(0, -500)"

    obs, reward, terminated, truncated, info = env.step(action)

    top, bottom = get_top_bottom_elems(obs)
    prev_top_x, prev_top_y = top_x, top_y
    top_x, top_y = extract_coords_from_elem(top)
    prev_bottom_x, prev_bottom_y = bottom_x, bottom_y
    bottom_x, bottom_y = extract_coords_from_elem(bottom)

    # no error
    assert not obs["last_action_error"]

    # no movement
    assert prev_top_x == top_x and prev_top_y == top_y
    assert prev_bottom_x == bottom_x and prev_bottom_y == bottom_y

    # scroll down
    action = f"scroll(0, 500)"

    obs, reward, terminated, truncated, info = env.step(action)

    top, bottom = get_top_bottom_elems(obs)
    prev_top_x, prev_top_y = top_x, top_y
    top_x, top_y = extract_coords_from_elem(top)
    prev_bottom_x, prev_bottom_y = bottom_x, bottom_y
    bottom_x, bottom_y = extract_coords_from_elem(bottom)

    # no error
    assert not obs["last_action_error"]

    # movement
    assert prev_top_x == top_x and prev_top_y > top_y
    assert prev_bottom_x == bottom_x and prev_bottom_y > bottom_y

    env.close()


def test_tab_actions():
    action_set = HighLevelActionSet(subsets=["tab", "nav"])

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": CHECKBOX_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )
    obs, info = env.reset()
    assert not obs["last_action_error"]
    assert len(obs["open_pages_urls"]) == 1
    assert len(obs["open_pages_titles"]) == 1
    assert obs["active_page_index"] == 0
    assert obs["open_pages_urls"][obs["active_page_index"][0]] == obs["url"]

    obs, reward, terminated, truncated, info = env.step("new_tab()")
    assert not obs["last_action_error"]
    assert len(obs["open_pages_urls"]) == 2
    assert len(obs["open_pages_titles"]) == 2
    assert obs["active_page_index"] == 1
    assert obs["open_pages_urls"][obs["active_page_index"][0]] == obs["url"]

    obs, reward, terminated, truncated, info = env.step(f"goto({repr(TEXTBOX_URL)})")
    assert not obs["last_action_error"]
    assert len(obs["open_pages_urls"]) == 2
    assert len(obs["open_pages_titles"]) == 2
    assert obs["active_page_index"] == 1
    assert obs["open_pages_urls"][obs["active_page_index"][0]] == obs["url"]

    obs, reward, terminated, truncated, info = env.step("tab_focus(0)")
    assert not obs["last_action_error"]
    assert len(obs["open_pages_urls"]) == 2
    assert len(obs["open_pages_titles"]) == 2
    assert obs["active_page_index"] == 0
    assert obs["open_pages_urls"][obs["active_page_index"][0]] == obs["url"]

    obs, reward, terminated, truncated, info = env.step("tab_close()")
    assert not obs["last_action_error"]
    assert len(obs["open_pages_urls"]) == 1
    assert len(obs["open_pages_titles"]) == 1
    assert obs["active_page_index"] == 0
    assert obs["open_pages_urls"][obs["active_page_index"][0]] == obs["url"]

    env.close()


def test_mouse_down_up():
    action_set = HighLevelActionSet(subsets=["bid", "coord"])

    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": CHECKBOX_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    def get_checkbox_elem(obs):
        soup = bs4.BeautifulSoup(
            flatten_dom_to_str(
                obs["dom_object"], obs["extra_element_properties"], with_center_coords=True
            ),
            "lxml",
        )
        checkbox = soup.find("input", attrs={"type": "checkbox", "id": "vehicle1"})
        return checkbox

    obs, info = env.reset()
    checkbox = get_checkbox_elem(obs)

    # box not checked
    assert not obs["last_action_error"]
    assert not checkbox.has_attr("checked")

    # click box 1 time
    x, y = ast.literal_eval(checkbox.get("center"))
    action = f"""\
mouse_click({repr(x)}, {repr(y)})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nmouse_") == 1

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box checked
    assert not obs["last_action_error"]
    assert checkbox.has_attr("checked")

    # click box 1 time
    x, y = ast.literal_eval(checkbox.get("center"))
    action = f"""\
mouse_move(0, 0)
mouse_move({repr(x)}, {repr(y)})
mouse_down({repr(x)}, {repr(y)})
mouse_up({repr(x)}, {repr(y)})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nmouse_") == 4

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box not checked
    assert not obs["last_action_error"]
    assert not checkbox.has_attr("checked")

    # click box 2 times
    x, y = ast.literal_eval(checkbox.get("center"))
    action = f"""\
mouse_move(0, 0)
mouse_move({repr(x)}, {repr(y)})
mouse_down({repr(x)}, {repr(y)}, button="left")
mouse_up({repr(x)}, {repr(y)}, "left")
mouse_down({repr(x)}, {repr(y)})
mouse_up({repr(x)}, {repr(y)})
"""
    python_action = action_set.to_python_code(action)

    assert python_action.count("\nmouse_") == 6

    obs, reward, term, trunc, info = env.step(action)
    checkbox = get_checkbox_elem(obs)

    # box not checked
    assert not obs["last_action_error"]
    assert not checkbox.has_attr("checked")


# test that forced action can click an obstructed element
@pytest.mark.parametrize("retry_with_force", [True, False])
def test_forced_actions(retry_with_force):
    action_set = HighLevelActionSet(subsets=["bid"], retry_with_force=retry_with_force)
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": OBSTRUCTED_CHECKBOX_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    obs, info = env.reset()

    def get_checkbox(obs):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        checkbox = soup.find("input", attrs={"id": "hobbies-checkbox-1"})
        return checkbox

    checkbox = get_checkbox(obs)

    action = f"""
    click({repr(checkbox.get(BID_ATTR))})
    """

    obs, reward, terminated, truncated, info = env.step(action)
    checkbox = get_checkbox(obs)
    if retry_with_force:
        assert not obs["last_action_error"]
        assert checkbox.get("checked", False) == False
    else:
        assert obs["last_action_error"]
        assert checkbox.has_attr("checked")

    env.close()


# TODO investigate why it takes ~1sec to mark each frame, although they are very small, and if we can do something about it
@pytest.mark.slow
def test_iframe_bid():
    action_set = HighLevelActionSet(subsets=["bid"])
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": LOTS_OF_IFRAMES_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )

    obs, info = env.reset()

    def get_checkbox(obs, i):
        soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
        checkbox = soup.find("input", attrs={"id": f"checkbox{i}"})
        return checkbox

    # try to click on checkboxes
    checkboxes = [
        (0, "a"),
        # (5, "f"),
        # (26, "aA"),
        (29, "aD"),
    ]
    for id, iframe_bid in checkboxes:

        # try to click on checkbox
        checkbox = get_checkbox(obs, id)
        bid = checkbox.get(BID_ATTR)

        # iframe bid should match
        assert re.match(f"^{iframe_bid}[0-9]+$", bid)

        action = f"""
        click({repr(bid)})
        """

        obs, reward, terminated, truncated, info = env.step(action)
        assert not obs["last_action_error"]

        # checkbox should get checked
        checkbox = get_checkbox(obs, id)
        assert checkbox.has_attr("checked")

    env.close()


def _make_env(start_url, action_set):
    return gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": start_url},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=action_set.to_python_code,
    )


def _get_soup(obs, with_center_coords=False):
    return bs4.BeautifulSoup(
        flatten_dom_to_str(
            obs["dom_object"],
            obs["extra_element_properties"],
            with_center_coords=with_center_coords,
        ),
        "lxml",
    )


def _center(elem):
    return ast.literal_eval(elem.get("center"))


def test_select_option():
    action_set = HighLevelActionSet(subsets=["bid"])
    env = _make_env(SELECT_URL, action_set)

    def get_elems(obs):
        soup = _get_soup(obs)
        return (
            soup.find("select", attrs={"id": "color"}),
            soup.find("span", attrs={"id": "color-result"}).get_text(strip=True),
            soup.find("select", attrs={"id": "fruits"}),
            soup.find("span", attrs={"id": "fruits-result"}).get_text(strip=True),
        )

    obs, info = env.reset()
    color, color_result, fruits, fruits_result = get_elems(obs)
    assert color.get("value") == "red"
    assert color_result == ""
    assert fruits_result == ""

    # single option, by value
    obs, reward, terminated, truncated, info = env.step(
        f"select_option({repr(color.get(BID_ATTR))}, 'blue')"
    )
    color, color_result, fruits, fruits_result = get_elems(obs)
    assert not obs["last_action_error"]
    assert color.get("value") == "blue"
    assert color_result == "blue"

    # single option, by label
    obs, reward, terminated, truncated, info = env.step(
        f"select_option({repr(color.get(BID_ATTR))}, 'Green')"
    )
    color, color_result, fruits, fruits_result = get_elems(obs)
    assert not obs["last_action_error"]
    assert color.get("value") == "green"
    assert color_result == "green"

    # multiple options (mixing value and label) in a multi-select
    obs, reward, terminated, truncated, info = env.step(
        f"select_option({repr(fruits.get(BID_ATTR))}, ['banana', 'Date'])"
    )
    color, color_result, fruits, fruits_result = get_elems(obs)
    assert not obs["last_action_error"]
    assert fruits_result == "banana,date"
    assert color_result == "green"

    # unknown option is reported as an action error
    obs, reward, terminated, truncated, info = env.step(
        f"select_option({repr(color.get(BID_ATTR))}, 'purple')"
    )
    color, color_result, fruits, fruits_result = get_elems(obs)
    assert obs["last_action_error"]
    assert color.get("value") == "green"

    env.close()


def test_upload_file(tmp_path):
    action_set = HighLevelActionSet(subsets=["bid", "coord"])
    env = _make_env(FILE_INPUT_URL, action_set)

    first_file = tmp_path / "upload_me.txt"
    first_file.write_text("hello")
    second_file = tmp_path / "upload_me_too.txt"
    second_file.write_text("world")

    def get_file_input(obs):
        return _get_soup(obs, with_center_coords=True).find("input", attrs={"id": "myfile"})

    obs, info = env.reset()
    file_input = get_file_input(obs)
    assert not file_input.get("value")

    # upload using bid
    obs, reward, terminated, truncated, info = env.step(
        f"upload_file({repr(file_input.get(BID_ATTR))}, {repr(str(first_file))})"
    )
    file_input = get_file_input(obs)
    assert not obs["last_action_error"]
    assert file_input.get("value").endswith("upload_me.txt")

    # an empty list clears the selected files
    obs, reward, terminated, truncated, info = env.step(
        f"upload_file({repr(file_input.get(BID_ATTR))}, [])"
    )
    file_input = get_file_input(obs)
    assert not obs["last_action_error"]
    assert not file_input.get("value")

    # upload using coordinates
    x, y = _center(file_input)
    obs, reward, terminated, truncated, info = env.step(
        f"mouse_upload_file({repr(x)}, {repr(y)}, [{repr(str(second_file))}])"
    )
    file_input = get_file_input(obs)
    assert not obs["last_action_error"]
    assert file_input.get("value").endswith("upload_me_too.txt")

    # clicking something that does not open a file chooser is reported as an action error
    heading_x, heading_y = _center(_get_soup(obs, with_center_coords=True).find("h1"))
    obs, reward, terminated, truncated, info = env.step(
        f"mouse_upload_file({repr(heading_x)}, {repr(heading_y)}, {repr(str(first_file))})"
    )
    file_input = get_file_input(obs)
    assert obs["last_action_error"]
    assert file_input.get("value").endswith("upload_me_too.txt")

    env.close()


def test_drag_and_drop():
    action_set = HighLevelActionSet(subsets=["bid", "coord"])
    env = _make_env(DRAG_AND_DROP_URL, action_set)

    def get_state(obs):
        soup = _get_soup(obs, with_center_coords=True)
        source = soup.find("div", attrs={"id": "source"})
        target = soup.find("div", attrs={"id": "target"})
        item_1 = soup.find("div", attrs={"id": "item-1"})
        item_2 = soup.find("div", attrs={"id": "item-2"})
        drop_log = soup.find("span", attrs={"id": "drop-log"}).get_text(strip=True)
        return source, target, item_1, item_2, drop_log

    def child_ids(zone):
        return [child.get("id") for child in zone.find_all("div")]

    obs, info = env.reset()
    source, target, item_1, item_2, drop_log = get_state(obs)
    assert child_ids(source) == ["item-1", "item-2"]
    assert child_ids(target) == []

    # drag and drop using bids
    obs, reward, terminated, truncated, info = env.step(
        f"drag_and_drop({repr(item_1.get(BID_ATTR))}, {repr(target.get(BID_ATTR))})"
    )
    source, target, item_1, item_2, drop_log = get_state(obs)
    assert not obs["last_action_error"]
    assert drop_log == "item-1"
    assert child_ids(source) == ["item-2"]
    assert child_ids(target) == ["item-1"]

    # drag and drop using coordinates
    from_x, from_y = _center(item_2)
    to_x, to_y = _center(target)
    obs, reward, terminated, truncated, info = env.step(
        f"mouse_drag_and_drop({repr(from_x)}, {repr(from_y)}, {repr(to_x)}, {repr(to_y)})"
    )
    source, target, item_1, item_2, drop_log = get_state(obs)
    assert not obs["last_action_error"]
    assert drop_log == "item-2"
    assert child_ids(source) == []
    assert child_ids(target) == ["item-1", "item-2"]

    env.close()


def test_fill_autocomplete_menu():
    action_set = HighLevelActionSet(subsets=["bid"])
    env = _make_env(AUTOCOMPLETE_URL, action_set)

    def get_state(obs):
        soup = _get_soup(obs)
        city = soup.find("input", attrs={"id": "city"})
        suggestions = [
            option.get_text(strip=True)
            for option in soup.find_all("div", attrs={"class": "suggestion"})
        ]
        keydowns = int(soup.find("span", attrs={"id": "keydown-count"}).get_text(strip=True))
        return city, suggestions, keydowns

    obs, info = env.reset()
    city, suggestions, keydowns = get_state(obs)
    bid = city.get(BID_ATTR)
    assert keydowns == 0

    # plain fill: no key events
    obs, reward, terminated, truncated, info = env.step(f"fill({repr(bid)}, 'Lon')")
    city, suggestions, prev_keydowns = get_state(obs)
    assert not obs["last_action_error"]
    assert city.get("value") == "Lon"
    assert suggestions == ["London"]
    assert prev_keydowns == 0

    # autocomplete mode: fill n-1 chars then type the last one (exactly one character keydown)
    obs, reward, terminated, truncated, info = env.step(f"fill({repr(bid)}, 'Par', True)")
    city, suggestions, keydowns = get_state(obs)
    assert not obs["last_action_error"]
    assert city.get("value") == "Par"
    assert suggestions == ["Paris", "Parma"]
    assert keydowns == prev_keydowns + 1
    prev_keydowns = keydowns

    # autocomplete mode, single character: previous value is cleared, char is typed
    obs, reward, terminated, truncated, info = env.step(
        f"fill({repr(bid)}, 'L', enable_autocomplete_menu=True)"
    )
    city, suggestions, keydowns = get_state(obs)
    assert not obs["last_action_error"]
    assert city.get("value") == "L"
    assert suggestions == ["Lisbon", "London", "Lyon"]
    assert keydowns == prev_keydowns + 1
    prev_keydowns = keydowns

    # autocomplete mode, empty value: field is cleared, nothing is typed
    obs, reward, terminated, truncated, info = env.step(f"fill({repr(bid)}, '', True)")
    city, suggestions, keydowns = get_state(obs)
    assert not obs["last_action_error"]
    assert city.get("value") == ""
    assert suggestions == []
    assert keydowns == prev_keydowns

    env.close()


def test_scroll_at():
    action_set = HighLevelActionSet(subsets=["bid", "coord"])
    env = _make_env(SCROLLABLE_PANELS_URL, action_set)

    def get_state(obs):
        soup = _get_soup(obs, with_center_coords=True)
        left = soup.find("div", attrs={"id": "left"})
        right = soup.find("div", attrs={"id": "right"})
        left_scroll = int(soup.find("span", attrs={"id": "left-scroll"}).get_text(strip=True))
        right_scroll = int(soup.find("span", attrs={"id": "right-scroll"}).get_text(strip=True))
        return left, right, left_scroll, right_scroll

    obs, info = env.reset()
    left, right, left_scroll, right_scroll = get_state(obs)
    assert left_scroll == 0 and right_scroll == 0

    # scroll down over the left panel: only the left panel scrolls
    x, y = _center(left)
    obs, reward, terminated, truncated, info = env.step(f"scroll_at({repr(x)}, {repr(y)}, 0, 300)")
    left, right, left_scroll, right_scroll = get_state(obs)
    assert not obs["last_action_error"]
    assert left_scroll > 0
    assert right_scroll == 0
    prev_left_scroll = left_scroll

    # scroll down over the right panel: only the right panel scrolls
    x, y = _center(right)
    obs, reward, terminated, truncated, info = env.step(f"scroll_at({repr(x)}, {repr(y)}, 0, 300)")
    left, right, left_scroll, right_scroll = get_state(obs)
    assert not obs["last_action_error"]
    assert left_scroll == prev_left_scroll
    assert right_scroll > 0
    prev_right_scroll = right_scroll

    # scroll back up over the left panel
    x, y = _center(left)
    obs, reward, terminated, truncated, info = env.step(
        f"scroll_at({repr(x)}, {repr(y)}, 0, -1000)"
    )
    left, right, left_scroll, right_scroll = get_state(obs)
    assert not obs["last_action_error"]
    assert left_scroll == 0
    assert right_scroll == prev_right_scroll

    env.close()


def test_tab_close_last_tab():
    action_set = HighLevelActionSet(subsets=["tab", "nav"])
    env = _make_env(CHECKBOX_URL, action_set)

    obs, info = env.reset()
    assert len(obs["open_pages_urls"]) == 1
    assert obs["url"] == CHECKBOX_URL

    # closing the only tab opens a fresh blank page and makes it active
    obs, reward, terminated, truncated, info = env.step("tab_close()")
    assert not obs["last_action_error"]
    assert obs["open_pages_urls"] == ("about:blank",)
    assert len(obs["open_pages_titles"]) == 1
    assert obs["active_page_index"] == 0
    assert obs["url"] == "about:blank"

    # the new page is usable
    obs, reward, terminated, truncated, info = env.step(f"goto({repr(TEXTBOX_URL)})")
    assert not obs["last_action_error"]
    assert obs["open_pages_urls"] == (TEXTBOX_URL,)
    assert obs["active_page_index"] == 0
    assert obs["url"] == TEXTBOX_URL

    env.close()


# test that forced check/uncheck can toggle an obstructed checkbox
@pytest.mark.parametrize("retry_with_force", [True, False])
@pytest.mark.parametrize(
    "action_name, checkbox_id, expected_checked",
    [("check", "hobbies-checkbox-2", True), ("uncheck", "hobbies-checkbox-1", False)],
)
def test_forced_check_actions(retry_with_force, action_name, checkbox_id, expected_checked):
    action_set = HighLevelActionSet(
        subsets=["custom"],
        custom_actions=[check, uncheck],
        retry_with_force=retry_with_force,
    )
    env = _make_env(OBSTRUCTED_CHECKBOX_URL, action_set)

    def get_checkbox(obs):
        return _get_soup(obs).find("input", attrs={"id": checkbox_id})

    obs, info = env.reset()
    checkbox = get_checkbox(obs)
    assert checkbox.has_attr("checked") != expected_checked

    obs, reward, terminated, truncated, info = env.step(
        f"{action_name}({repr(checkbox.get(BID_ATTR))})"
    )
    checkbox = get_checkbox(obs)
    if retry_with_force:
        assert not obs["last_action_error"]
        assert checkbox.has_attr("checked") == expected_checked
    else:
        assert obs["last_action_error"]
        assert checkbox.has_attr("checked") != expected_checked

    env.close()


if __name__ == "__main__":
    test_scroll()
