import ast
import os
from pathlib import Path

import bs4
import gymnasium as gym
import numpy as np
import pytest
import regex as re

# register gym environments
import browsergym.core
from browsergym.core.constants import BROWSERGYM_ID_ATTRIBUTE as BID_ATTR
from browsergym.core.observation import (
    _post_extract,
    _pre_extract,
    extract_all_frame_axtrees,
    extract_dom_snapshot,
    extract_merged_axtree,
    extract_screenshot,
)
from browsergym.utils.obs import (
    _get_coord_str,
    _process_bid,
    flatten_axtree_to_str,
    flatten_dom_to_str,
    overlay_som,
    prune_html,
)

__SLOW_MO = 1000 if "DISPLAY_BROWSER" in os.environ else None
__HEADLESS = False if "DISPLAY_BROWSER" in os.environ else True
__TIMEOUT = 500
__VIEWPORT = {"width": 800, "height": 600}

__DATA_DIR = Path(__file__).resolve().parent / "data"

TEST_PAGE = f"file://{__DATA_DIR}/test_page.html"
TEST_PAGE_2 = f"file://{__DATA_DIR}/test_page_2.html"
MULTI_IFRAME_URL = f"file://{__DATA_DIR}/basic_iframe_site/basic_iframe_2.html"
SHADOW_DOM_URL = f"file://{__DATA_DIR}/basic_shadow_dom_site/basic_shadow_dom.html"
SIMPLE_SHADOW_DOM_URL = f"file://{__DATA_DIR}/basic_shadow_dom_site/simple_shadow_dom.html"
BASIC_IFRAME_URL = f"file://{__DATA_DIR}/basic_shadow_iframe_site/basic_iframe.html"
BASIC_IFRAME_2_URL = f"file://{__DATA_DIR}/basic_shadow_iframe_site/basic_iframe_2.html"
INNER_IFRAME_URL = f"file://{__DATA_DIR}/basic_shadow_iframe_site/inner-iframe.html"
OUTER_IFRAME_URL = f"file://{__DATA_DIR}/basic_shadow_iframe_site/outer-iframe.html"
CUSTOM_PAGE_URL = f"file://{__DATA_DIR}/custom_page/basic_iframe.html"
MULTI_IFRAME_URL = f"file://{__DATA_DIR}/basic_iframe_site/basic_iframe_2.html"


@pytest.mark.skip(reason="TODO: how to get the final viewport size right?")
def test_extract_screenshot():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    _pre_extract(env.unwrapped.page)
    screenshot = extract_screenshot(env.unwrapped.page)
    _post_extract(env.unwrapped.page)

    # 3D array (height, width, rgb) of unsigned bytes (between 0 and 255)
    assert isinstance(screenshot, np.ndarray)
    assert len(screenshot.shape) == 3
    assert screenshot.shape[0] == __VIEWPORT["height"]
    assert screenshot.shape[1] == __VIEWPORT["width"]
    assert screenshot.shape[2] == 3  # RGB
    assert screenshot.dtype == np.uint8

    env.close()


def test_extract_axtree_simple():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    _pre_extract(env.unwrapped.page)
    all_frame_axtrees = extract_all_frame_axtrees(env.unwrapped.page)
    merged_axtree = extract_merged_axtree(env.unwrapped.page)
    _post_extract(env.unwrapped.page)

    # single frame
    assert len(all_frame_axtrees) == 1
    assert len(next(iter(all_frame_axtrees.values()))["nodes"]) == len(merged_axtree["nodes"])

    env.close()


def test_extract_axtree_multi_iframe():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": MULTI_IFRAME_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    _pre_extract(env.unwrapped.page)
    all_frame_axtrees = extract_all_frame_axtrees(env.unwrapped.page)
    merged_axtree = extract_merged_axtree(env.unwrapped.page)
    _post_extract(env.unwrapped.page)

    # multiple frames
    assert len(all_frame_axtrees) == 3

    # total number of nodes in merged and individual frame axtrees should be equal
    n_nodes = 0
    for frame_id, frame_axtree in all_frame_axtrees.items():
        n_nodes += len(frame_axtree["nodes"])

    assert n_nodes == len(merged_axtree["nodes"])

    env.close()


def test_extract_dom_simple():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    _pre_extract(env.unwrapped.page)
    dom_snapshot = extract_dom_snapshot(env.unwrapped.page)
    _post_extract(env.unwrapped.page)

    # single frame
    assert len(dom_snapshot["documents"]) == 1

    env.close()


def test_extract_dom_multi_iframe():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": MULTI_IFRAME_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    _pre_extract(env.unwrapped.page)
    dom_snapshot = extract_dom_snapshot(env.unwrapped.page)
    _post_extract(env.unwrapped.page)

    # multiple frames
    assert len(dom_snapshot["documents"]) == 3

    env.close()


def test_simple_shadowdom():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": SIMPLE_SHADOW_DOM_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    # retrieve an input element inside the shadowDOM
    elem = env.unwrapped.page.get_by_placeholder("Level 1.1 Text Field 1")
    assert elem.count() == 1

    # elem should have a browsergym_id in its BID_ATTR attribute
    elem_id = elem.get_attribute(BID_ATTR)
    assert elem_id is not None

    # elem should not have an aria-description (it should have been cleaned)
    aria_description = elem.get_attribute("aria-description")
    assert aria_description is None

    # elem should not have an aria-roledescription (it should have been cleaned)
    aria_roledescription = elem.get_attribute("aria-roledescription")
    assert aria_roledescription is None

    # check that elem can be retrieved correctly using its browsergym_id
    elem2 = env.unwrapped.page.get_by_test_id(elem_id)
    assert elem2.count() == 1
    assert env.unwrapped.page.evaluate(
        "([node1, node2]) => {return node1.isEqualNode(node2);}",
        [elem.element_handle(), elem2.element_handle()],
    )

    env.close()


def test_nested_shadowdom():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": SHADOW_DOM_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    # retrieve an input element inside the nested shadowDOM
    elem = env.unwrapped.page.get_by_placeholder("Level 2.4 Text Field 2")
    assert elem.count() == 1

    # elem should have a browsergym_id in its BID_ATTR attribute
    elem_id = elem.get_attribute(BID_ATTR)
    assert elem_id is not None

    # elem should not have an aria-description (it should have been cleaned)
    aria_description = elem.get_attribute("aria-description")
    assert aria_description is None

    # elem should not have an aria-roledescription (it should have been cleaned)
    aria_roledescription = elem.get_attribute("aria-roledescription")
    assert aria_roledescription is None

    # check that elem can be retrieved correctly using its browsergym_id
    elem2 = env.unwrapped.page.get_by_test_id(elem_id)
    assert elem2.count() == 1
    assert env.unwrapped.page.evaluate(
        "([node1, node2]) => {return node1.isEqualNode(node2);}",
        [elem.element_handle(), elem2.element_handle()],
    )

    env.close()


@pytest.mark.parametrize(
    "url",
    [
        TEST_PAGE,
        MULTI_IFRAME_URL,
        SIMPLE_SHADOW_DOM_URL,
        BASIC_IFRAME_URL,
        BASIC_IFRAME_2_URL,
        INNER_IFRAME_URL,
        OUTER_IFRAME_URL,
    ],
)
def test_dom_has_bids_no_aria(url):
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": url},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    # exceptions
    dom_node_names_without_bid = ["html", "#text", "#document", "#comment"]
    axtree_roles_without_bid = ["RootWebArea", "none", "generic", "StaticText", "InlineTextBox"]

    # 1. test the DOM snapshot for BID_ATTR, "aria-description" and "aria-roledescription"

    # check all HTML elements in the DOM for unique browsergym id
    dom = obs["dom_object"]
    bids = []
    for doc in dom["documents"]:
        for node_name_id, attributes in zip(doc["nodes"]["nodeName"], doc["nodes"]["attributes"]):
            node_name = dom["strings"][node_name_id]
            # read the node's attributes
            j = 0
            bid = None
            while j < len(attributes):
                attr_name = dom["strings"][attributes[j]]
                attr_value = dom["strings"][attributes[j + 1]]

                # print(f"{node_name} {attr_name}: {attr_value}")

                # check that the "aria-roledescription" attribute is absent (this is specific to this test page)
                assert attr_name != "aria-roledescription"

                # check that the "aria-description" attribute is absent (this is specific to this test page)
                assert attr_name != "aria-description"

                # extract the browsergym id from the BID_ATTR attribute
                if attr_name == BID_ATTR:
                    bid = attr_value
                j += 2

            # check that all elements (with exceptions) have a browsergym id
            if node_name not in dom_node_names_without_bid:
                assert bid is not None

            if bid is not None:
                bids.append(bid)

    # check that all browsergym ids are unique
    assert len(bids) == len(set(bids))

    # 2. test the AXTree for "browsergym_id" and "description" properties
    axtree = obs["axtree_object"]
    bids = []
    for node in axtree["nodes"]:
        bid = node.get("browsergym_id", None)

        # check that the "aria-roledescription" attribute is absent (this is specific to this test page)
        for property in node.get("properties", []):
            assert property["name"] != "roledescription"

        # check that the "aria-description" attribute is absent (this is specific to this test page)
        assert "description" not in node

        # check that all elements (with exceptions) have a browsergym id
        if node["role"]["value"] not in axtree_roles_without_bid:
            assert bid is not None

            if bid is not None:
                bids.append(bid)

    # check that all browsergym ids are unique
    assert len(bids) == len(set(bids))

    env.close()


def test_dom_to_text():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE_2},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=None,
    )
    obs, info = env.reset()

    dom = flatten_dom_to_str(obs["dom_object"])
    assert isinstance(dom, str)
    assert "Subscribe to newsletter" in dom
    assert "Janice" not in dom

    obs, reward, term, trunc, info = env.step(
        f"""\
page.get_by_label("Name:").click()
page.get_by_label("Name:").fill("Janice")
page.get_by_label("Name:").press("Tab")
page.get_by_label("Email:").fill("janice@mail.com")
page.get_by_label("Email:").press("Tab")
page.get_by_label("Age:", exact=True).fill("21")
page.get_by_label("Age:", exact=True).press("Tab")
"""
    )

    dom = flatten_dom_to_str(obs["dom_object"])
    assert "Janice" in dom
    assert "janice@mail.com" in dom

    dom = flatten_dom_to_str(
        obs["dom_object"],
        extra_properties=obs["extra_element_properties"],
        with_visible=True,
        with_clickable=True,
        with_center_coords=True,
        with_bounding_box_coords=True,
        with_som=True,
    )
    assert 'box="(' in dom
    assert 'center="(' in dom
    assert 'clickable="" som="" type="submit" value="Submit" visible=""' in dom
    assert 'head bid="1">' in dom
    assert 'clickable="" for="email" visible=""' in dom
    assert "Text within a non-html tag" in dom
    assert "Text that should not be visible" in dom

    dom = flatten_dom_to_str(
        obs["dom_object"], extra_properties=obs["extra_element_properties"], filter_som_only=True
    )
    assert 'for="email"' not in dom
    assert 'type="submit" value="Submit"' in dom
    assert "Text within a non-html tag" not in dom
    assert "Text that should not be visible" not in dom

    dom = flatten_dom_to_str(
        obs["dom_object"],
        extra_properties=obs["extra_element_properties"],
        filter_visible_only=True,
    )
    assert "<title bid=" not in dom
    assert 'type="submit" value="Submit"' in dom
    assert "Text within a non-html tag" in dom
    assert "Text that should not be visible" not in dom

    dom = flatten_dom_to_str(
        obs["dom_object"],
        extra_properties=obs["extra_element_properties"],
        hide_bid_if_invisible=True,
    )
    assert "<title" in dom
    assert "<title bid=" not in dom
    assert 'type="submit" value="Submit"' in dom
    assert "Text within a non-html tag" in dom
    assert "Text that should not be visible" in dom

    dom = flatten_dom_to_str(
        obs["dom_object"],
        extra_properties=obs["extra_element_properties"],
        filter_with_bid_only=True,
    )
    assert "<title bid=" in dom
    assert 'type="submit" value="Submit"' in dom
    assert "Text within a non-html tag" not in dom
    assert "Text that should not be visible" in dom

    env.close()


def test_axtree_to_text():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE_2},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=None,
    )
    obs, info = env.reset()

    axtree = flatten_axtree_to_str(obs["axtree_object"])
    assert isinstance(axtree, str)
    assert "checkbox 'Subscribe to newsletter', checked='false'" in axtree
    assert "Janice" not in axtree

    obs, reward, term, trunc, info = env.step(
        f"""\
page.get_by_label("Name:").click()
page.get_by_label("Name:").fill("Janice")
page.get_by_label("Name:").press("Tab")
page.get_by_label("Email:").fill("janice@mail.com")
page.get_by_label("Email:").press("Tab")
page.get_by_label("Age:", exact=True).fill("21")
page.get_by_label("Age:", exact=True).press("Tab")
page.get_by_label("Subscribe to newsletter").click()
"""
    )

    axtree = flatten_axtree_to_str(obs["axtree_object"])
    assert "Janice" in axtree
    assert "janice@mail.com" in axtree
    assert "checkbox 'Subscribe to newsletter', focused, checked='true'" in axtree

    axtree = flatten_axtree_to_str(
        obs["axtree_object"],
        extra_properties=obs["extra_element_properties"],
        with_visible=True,
        with_clickable=True,
        with_center_coords=True,
        with_bounding_box_coords=True,
        with_som=True,
    )
    assert 'box="(' in axtree
    assert 'center="(' in axtree
    assert ", clickable, visible, som" in axtree
    assert "] heading 'Simple Form', box=\"(" in axtree
    assert "] textbox 'Email:' value='janice@mail.com'" in axtree
    assert "Text within a non-html tag" in axtree
    assert "Text that should not be visible" in axtree
    assert "] paragraph" in axtree

    axtree = flatten_axtree_to_str(
        obs["axtree_object"], extra_properties=obs["extra_element_properties"], filter_som_only=True
    )
    assert "LabelText" not in axtree
    assert "] button 'Submit'" in axtree
    assert "Text within a non-html tag" not in axtree
    assert "Text that should not be visible" not in axtree

    axtree = flatten_axtree_to_str(
        obs["axtree_object"],
        extra_properties=obs["extra_element_properties"],
        filter_visible_only=True,
    )
    assert "RootWebArea" in axtree
    assert "] button 'Submit'" in axtree
    assert "Text within a non-html tag" in axtree
    assert "Text that should not be visible" not in axtree
    assert "] paragraph" not in axtree

    axtree = flatten_axtree_to_str(
        obs["axtree_object"],
        extra_properties=obs["extra_element_properties"],
        hide_bid_if_invisible=True,
    )
    assert "RootWebArea" in axtree
    assert "] button 'Submit'" in axtree
    assert "Text within a non-html tag" in axtree
    assert "Text that should not be visible" in axtree
    assert "] paragraph '" not in axtree
    assert "paragraph '" in axtree

    axtree = flatten_axtree_to_str(
        obs["axtree_object"],
        extra_properties=obs["extra_element_properties"],
        filter_with_bid_only=True,
    )
    assert "button 'Submit'" in axtree
    assert "Text within a non-html tag" in axtree
    assert "Text that should not be visible" in axtree

    env.close()


def test_axtree_to_text_remove_redundant():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE_2},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=None,
    )
    obs, info = env.reset()

    axtree = flatten_axtree_to_str(obs["axtree_object"], remove_redundant_static_text=True)
    assert "heading 'Simple Form'" in axtree
    assert "StaticText 'Simple Form'" not in axtree

    axtree = flatten_axtree_to_str(obs["axtree_object"], remove_redundant_static_text=False)
    assert "heading 'Simple Form'" in axtree
    assert "StaticText 'Simple Form'" in axtree


def test_simple_webpage():
    """
    In this simple unit test, we make sure the retrieved coordinates of a known element
    are correct, by verifing that the element is checked after clicking on it.

    """
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    element = env.unwrapped.page.query_selector('[type="checkbox"]')

    assert not element.is_checked()

    soup = bs4.BeautifulSoup(
        flatten_dom_to_str(
            obs["dom_object"], obs["extra_element_properties"], with_center_coords=True
        ),
        "lxml",
    )
    input_elem = soup.find("input", attrs={"type": "checkbox"})
    x, y = map(float, ast.literal_eval(input_elem.get("center")))

    # click input elem
    env.unwrapped.page.mouse.click(x, y)

    element = env.unwrapped.page.query_selector('[type="checkbox"]')

    assert element.is_checked()

    env.close()


def test_basic_iframe_webpage():
    """
    In this simple unit test, we make sure the retrieved coordinates of a known element
    are correct, by verifing that the element is checked after clicking on it.

    """
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": BASIC_IFRAME_2_URL, "goal": "dummy goal"},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )

    # click on the checkbox in the main frame
    obs, info = env.reset()

    element = env.unwrapped.page.query_selector('[type="checkbox"]')

    assert not element.is_checked()

    bid = element.get_attribute("bid")
    soup = bs4.BeautifulSoup(
        flatten_dom_to_str(
            obs["dom_object"], obs["extra_element_properties"], with_center_coords=True
        ),
        "lxml",
    )
    input_elem = soup.find("input", attrs={"bid": bid})
    x, y = map(float, ast.literal_eval(input_elem.get("center")))
    env.unwrapped.page.mouse.click(x, y)

    assert element.is_checked()

    # click on the checkbox in the inner_frame
    obs, _, _, _, _ = env.step("")
    element = env.unwrapped.page.frames[2].query_selector('[type="checkbox"]')

    assert element.is_checked()  # instantiated as checked

    bid = element.get_attribute("bid")
    soup = bs4.BeautifulSoup(
        flatten_dom_to_str(
            obs["dom_object"], obs["extra_element_properties"], with_center_coords=True
        ),
        "lxml",
    )
    input_elem = soup.find("input", attrs={"bid": bid})
    x, y = map(float, ast.literal_eval(input_elem.get("center")))
    env.unwrapped.page.mouse.click(x, y)

    assert not element.is_checked()

    # scroll inside a frame, and click on the checkbox in the inner_frame
    env.unwrapped.page.frames[1].evaluate("window.scrollTo(0, document.body.scrollHeight);")
    obs, _, _, _, _ = env.step("")
    element = env.unwrapped.page.frames[2].query_selector('[type="checkbox"]')

    assert not element.is_checked()  # instantiated as checked

    bid = element.get_attribute("bid")
    soup = bs4.BeautifulSoup(
        flatten_dom_to_str(
            obs["dom_object"], obs["extra_element_properties"], with_center_coords=True
        ),
        "lxml",
    )
    input_elem = soup.find("input", attrs={"bid": bid})
    x, y = map(float, ast.literal_eval(input_elem.get("center")))
    env.unwrapped.page.mouse.click(x, y)

    assert element.is_checked()
    env.close()


@pytest.mark.skip(reason="HTML file seems missing. Deactivating for now.")
def test_filter_visible_only():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": CUSTOM_PAGE_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
        goal="dummy goal",
    )

    # click on the checkbox in the main frame
    obs, info = env.reset()
    axtree_txt = flatten_axtree_to_str(obs["axtree_object"], filter_visible_only=True)
    assert "textbox" not in axtree_txt

    # scroll on the main frame, then scroll inside a frame to find that hidden textbox element
    env.unwrapped.page.evaluate(
        "window.scrollTo(document.body.scrollWidth / 3, document.body.scrollHeight / 3);"
    )
    iframe = env.unwrapped.page.frames[1]
    iframe.evaluate("window.scrollTo(0, document.body.scrollHeight / 3.5);")

    obs, _, _, _, _ = env.step("")
    axtree_txt = flatten_axtree_to_str(obs["axtree_object"])
    assert "textbox" in obs["axtree_txt"]


def test_extract_focused_element_bid_through_iframes():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": MULTI_IFRAME_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
    )

    obs, info = env.reset()
    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    inner_checkbox = soup.find("input", attrs={"id": "checkbox_2"})
    body = soup.find("body")

    # focused bid is body element
    assert obs["focused_element_bid"] == body.get(BID_ATTR)

    # click box
    action = f"click({repr(inner_checkbox.get(BID_ATTR))})"

    obs, reward, terminated, truncated, info = env.step(action)
    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    inner_checkbox = soup.find("input", attrs={"id": "checkbox_2"})

    # no error
    assert not obs["last_action_error"]

    # focused bid is checkbox
    assert obs["focused_element_bid"] == inner_checkbox.get(BID_ATTR)

    env.close()


def test_extract_focused_element_bid_through_shadowdom():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": SHADOW_DOM_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
    )

    obs, info = env.reset()
    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    input_elem = soup.find("input", attrs={"name": "level2.4-textfield2"})
    body = soup.find("body")

    # focused bid is body element
    assert obs["focused_element_bid"] == body.get(BID_ATTR)

    # click input elem
    action = f"click({repr(input_elem.get(BID_ATTR))})"

    obs, reward, terminated, truncated, info = env.step(action)
    soup = bs4.BeautifulSoup(flatten_dom_to_str(obs["dom_object"]), "lxml")
    input_elem = soup.find("input", attrs={"name": "level2.4-textfield2"})

    # no error
    assert not obs["last_action_error"]

    # focused bid is input elem
    assert obs["focused_element_bid"] == input_elem.get(BID_ATTR)

    env.close()


def test_tags_to_mark():

    # default value
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE_2},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        action_mapping=None,
    )
    obs, info = env.reset()

    dom = flatten_dom_to_str(obs["dom_object"])
    assert isinstance(dom, str)
    assert "<nonhtmltag" in dom
    assert '<nonhtmltag bid="' not in dom
    assert '<p bid="' in dom

    env.close()

    # standard_html
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE_2},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        tags_to_mark="standard_html",
        action_mapping=None,
    )
    obs, info = env.reset()

    dom = flatten_dom_to_str(obs["dom_object"])
    assert isinstance(dom, str)
    assert "<nonhtmltag" in dom
    assert '<nonhtmltag bid="' not in dom
    assert '<p bid="' in dom

    env.close()

    # all
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": TEST_PAGE_2},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        timeout=__TIMEOUT,
        tags_to_mark="all",
        action_mapping=None,
    )
    obs, info = env.reset()

    dom = flatten_dom_to_str(obs["dom_object"])
    assert isinstance(dom, str)
    assert "<nonhtmltag" in dom
    assert '<nonhtmltag bid="' in dom
    assert '<p bid="' in dom

    env.close()

    # incorrect value
    with pytest.raises(Exception):
        env = gym.make(
            "browsergym/openended",
            task_kwargs={"start_url": TEST_PAGE_2},
            headless=__HEADLESS,
            slow_mo=__SLOW_MO,
            timeout=__TIMEOUT,
            tags_to_mark="fdsjkhjk",
            action_mapping=None,
        )


def test_prune_html():
    html = """<html><head><link rel="stylesheet" href="x.css"><style>.k{color:red}</style></head><body>
<!-- secret comment -->
<script>alert(1)</script>
<div bid="a"></div>
<span bid="b">unwrapped text</span><br>
<div bid="c" class="k">kept div</div>
<p bid="d"><i bid="e">nested</i></p>
<button bid="f">Submit</button>
</body></html>"""

    pruned = prune_html(html)
    soup = bs4.BeautifulSoup(pruned, "lxml")

    # comments, useless tags and html/body wrappers are removed
    assert "secret comment" not in pruned
    assert "<!--" not in pruned
    assert "alert(1)" not in pruned
    assert ".k{color:red}" not in pruned
    for tag in ("<script", "<style", "<link", "<br", "<html", "<body"):
        assert tag not in pruned

    # empty bid-only structural tag is dropped
    assert soup.find(attrs={"bid": "a"}) is None

    # non-empty bid-only structural tags are unwrapped, content is kept
    assert soup.find(attrs={"bid": "b"}) is None
    assert soup.find(attrs={"bid": "d"}) is None
    assert soup.find(attrs={"bid": "e"}) is None
    assert "unwrapped text" in pruned
    assert "nested" in pruned

    # structural tags with extra attributes are kept
    kept_div = soup.find(attrs={"bid": "c"})
    assert kept_div is not None
    assert kept_div.name == "div"
    assert kept_div["class"] == ["k"]
    assert kept_div.get_text(strip=True) == "kept div"

    # non-structural tags are kept, even with a bid only
    button = soup.find(attrs={"bid": "f"})
    assert button is not None
    assert button.name == "button"
    assert button.get_text(strip=True) == "Submit"


def test_prune_html_multiline_comment():
    pruned = prune_html("<div bid='a' class='x'>keep<!-- line1\nline2 --></div>")
    assert "line1" not in pruned
    assert "line2" not in pruned
    assert "keep" in pruned


@pytest.mark.parametrize(
    "coord,decimals,expected",
    [
        ((1.234, 5.678), 1, "(1.2,5.7)"),
        ((1.234, 5.678), 0, "(1,6)"),
        ((1.234, 5.678), 2, "(1.23,5.68)"),
        ((0, 10, 20.5, 30.25), 1, "(0.0,10.0,20.5,30.2)"),
        ("(1.234, 5.678)", 1, "(1.2,5.7)"),
        ("[3, 4.5]", 2, "(3.00,4.50)"),
    ],
)
def test_get_coord_str(coord, decimals, expected):
    assert _get_coord_str(coord, decimals) == expected


@pytest.mark.parametrize(
    "flag",
    [
        "with_visible",
        "with_clickable",
        "with_center_coords",
        "with_bounding_box_coords",
        "with_som",
        "filter_visible_only",
        "filter_with_bid_only",
        "filter_som_only",
    ],
)
def test_process_bid_requires_extra_properties(flag):
    with pytest.raises(ValueError, match="extra_properties argument required"):
        _process_bid("1", extra_properties=None, **{flag: True})


def test_process_bid_without_extra_properties():
    assert _process_bid("1", extra_properties=None) == (False, [])
    assert _process_bid(None, extra_properties=None) == (False, [])


def test_process_bid_coord_decimals():
    extra_properties = {
        "1": {
            "visibility": 1.0,
            "bbox": (10.25, 20.5, 30.0, 40.75),
            "clickable": False,
            "set_of_marks": False,
        },
        "2": {
            "visibility": 1.0,
            "bbox": None,
            "clickable": False,
            "set_of_marks": False,
        },
    }

    _, attrs = _process_bid(
        "1",
        extra_properties=extra_properties,
        with_center_coords=True,
        with_bounding_box_coords=True,
        coord_decimals=2,
    )
    assert attrs == ['box="(10.25,20.50,40.25,61.25)"', 'center="(25.25,40.88)"']

    _, attrs = _process_bid(
        "1",
        extra_properties=extra_properties,
        with_center_coords=True,
        with_bounding_box_coords=True,
    )
    assert attrs == ['box="(10,20,40,61)"', 'center="(25,41)"']

    # no coordinates printed when bbox is None
    _, attrs = _process_bid(
        "2",
        extra_properties=extra_properties,
        with_center_coords=True,
        with_bounding_box_coords=True,
        coord_decimals=2,
    )
    assert attrs == []


def test_flatten_axtree_to_str_requires_extra_properties():
    AX_tree = {
        "nodes": [
            {
                "nodeId": "1",
                "role": {"value": "RootWebArea"},
                "name": {"value": "page"},
                "childIds": ["2"],
            },
            {
                "nodeId": "2",
                "role": {"value": "button"},
                "name": {"value": "Submit"},
                "browsergym_id": "a",
                "childIds": [],
            },
        ]
    }

    with pytest.raises(ValueError, match="extra_properties argument required"):
        flatten_axtree_to_str(AX_tree, extra_properties=None, with_clickable=True)

    # no extra properties needed when no attribute or filter is requested
    tree_str = flatten_axtree_to_str(AX_tree, extra_properties=None)
    assert "[a] button 'Submit'" in tree_str


def test_overlay_som():
    height, width = 120, 160
    screenshot = np.full((height, width, 3), 255, dtype=np.uint8)
    original = screenshot.copy()

    extra_properties = {
        "12": {
            "visibility": 1.0,
            "bbox": (40, 50, 80, 40),
            "clickable": True,
            "set_of_marks": True,
        },
        "13": {
            "visibility": 0.0,
            "bbox": None,
            "clickable": False,
            "set_of_marks": True,
        },
        "14": {
            "visibility": 1.0,
            "bbox": (5, 100, 30, 15),
            "clickable": False,
            "set_of_marks": False,
        },
        "15": {
            "visibility": 1.0,
            "bbox": (140, 100, 3, 3),
            "clickable": True,
            "set_of_marks": True,
        },
    }

    som = overlay_som(screenshot, extra_properties)

    assert som.shape == screenshot.shape
    assert som.dtype == np.uint8
    # input screenshot is not modified
    assert np.array_equal(screenshot, original)

    changed = np.any(som != original, axis=-1)
    assert changed.any()

    # drawing happens on the bbox of the som element (dashed border + tag)
    x, y, w, h = extra_properties["12"]["bbox"]
    assert changed[y - 2 : y + 3, x : x + w].any()  # top edge
    assert changed[y + h - 2 : y + h + 3, x : x + w].any()  # bottom edge
    assert changed[y : y + h, x - 2 : x + 3].any()  # left edge
    assert changed[y : y + h, x + w - 2 : x + w + 3].any()  # right edge
    # the interior of the box (away from the tag) is untouched
    assert not changed[y + 15 : y + h - 3, x + 30 : x + w - 3].any()

    # non-som elements and too-small boxes are not drawn
    x, y, w, h = extra_properties["14"]["bbox"]
    assert not changed[y : y + h + 1, x : x + w + 1].any()
    x, y, w, h = extra_properties["15"]["bbox"]
    assert not changed[y : y + h + 1, x : x + w + 1].any()

    # all drawing stays around the som element bbox
    x, y, w, h = extra_properties["12"]["bbox"]
    outside = changed.copy()
    outside[y - 15 : y + h + 3, x - 3 : x + w + 3] = False
    assert not outside.any()


def test_overlay_som_no_marks():
    screenshot = np.zeros((40, 60, 3), dtype=np.uint8)
    extra_properties = {
        "1": {"visibility": 1.0, "bbox": None, "clickable": False, "set_of_marks": True},
        "2": {"visibility": 1.0, "bbox": (0, 0, 10, 10), "clickable": False, "set_of_marks": False},
    }

    som = overlay_som(screenshot, extra_properties)

    assert som.shape == screenshot.shape
    assert np.array_equal(som, screenshot)
