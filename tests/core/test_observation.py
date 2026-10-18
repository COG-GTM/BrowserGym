import ast
import copy
import logging
import os
import types
from pathlib import Path

import bs4
import gymnasium as gym
import numpy as np
import playwright.sync_api
import pytest
import regex as re

# register gym environments
import browsergym.core
from browsergym.core.constants import BROWSERGYM_ID_ATTRIBUTE as BID_ATTR
from browsergym.core.observation import (
    MarkingError,
    _post_extract,
    _pre_extract,
    extract_all_frame_axtrees,
    extract_data_items_from_aria,
    extract_dom_snapshot,
    extract_merged_axtree,
    extract_screenshot,
    pop_bids_from_attribute,
)
from browsergym.utils.obs import flatten_axtree_to_str, flatten_dom_to_str

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
SANDBOXED_IFRAMES_URL = f"file://{__DATA_DIR}/sandboxed_iframes.html"
IFRAME_BID_STRIPPED_URL = f"file://{__DATA_DIR}/iframe_bid_stripped.html"
ARIA_ATTRIBUTES_URL = f"file://{__DATA_DIR}/aria_attributes.html"


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


# --- extract_data_items_from_aria / pop_bids_from_attribute (pure helpers) ---


@pytest.mark.parametrize(
    "aria_string,expected_items,expected_original",
    [
        # format produced by frame_mark_elements.js: f"browsergym_id_{bid} {original_content}"
        ("browsergym_id_12 ", ["12"], ""),
        ("browsergym_id_aB3 original text", ["aB3"], "original text"),
        ("browsergym_id_a", ["a"], ""),
        ("browsergym_id_7 browsergym_id_8 nested", ["7"], "browsergym_id_8 nested"),
        ("browsergym_id_5 first line\nsecond line", ["5"], "first line\nsecond line"),
    ],
)
def test_extract_data_items_from_aria_marked(aria_string, expected_items, expected_original):
    data_items, original_aria = extract_data_items_from_aria(aria_string)
    assert list(data_items) == expected_items
    assert original_aria == expected_original


@pytest.mark.parametrize(
    "aria_string",
    [
        "",
        "plain description",
        "browsergym_id_ missing bid",
        "prefix browsergym_id_12 not at start",
    ],
)
def test_extract_data_items_from_aria_unmarked(aria_string, caplog):
    with caplog.at_level(logging.WARNING, logger="browsergym.core.observation"):
        data_items, original_aria = extract_data_items_from_aria(
            aria_string, log_level=logging.WARNING
        )
    assert list(data_items) == []
    assert original_aria == aria_string
    assert "Failed to extract BrowserGym data from ARIA string" in caplog.text


def _make_dom_snapshot(strings, documents_attributes):
    return {
        "strings": list(strings),
        "documents": [
            {"nodes": {"attributes": [list(attrs) for attrs in doc_attrs]}}
            for doc_attrs in documents_attributes
        ],
    }


def test_pop_bids_from_attribute():
    strings = [
        "aria-description",  # 0
        "browsergym_id_0 ",  # 1: becomes empty, shared by several nodes
        "browsergym_id_1 keep me",  # 2: keeps original text, shared across documents
        "id",  # 3
        "x",  # 4
        "plain",  # 5: unmarked value
        "browsergym_id_3 browsergym_id_legit",  # 6: original text looks like a bid
        "aria-roledescription",  # 7
    ]
    dom_snapshot = _make_dom_snapshot(
        strings,
        [
            [
                [3, 4, 0, 1],  # other attribute before the target (emptied)
                [0, 2],  # target keeps original text
                [0, 1],  # shares string id 1 with node 0
                [],  # no attributes
                [0, 1, 3, 4],  # other attribute after the target (emptied)
                [0, 5],  # unmarked value
                [0, 6],  # bid-looking original text
                [0, 6],  # same, shared string id (must not be stripped twice)
                [7, 1],  # different attribute name, untouched
            ],
            [
                [0, 2],  # shares string id 2 with the first document
            ],
        ],
    )

    pop_bids_from_attribute(dom_snapshot, "aria-description")

    doc0, doc1 = (doc["nodes"]["attributes"] for doc in dom_snapshot["documents"])
    # emptied target attributes are removed (name and value), other attributes preserved
    assert doc0[0] == [3, 4]
    assert doc0[2] == []
    assert doc0[4] == [3, 4]
    # non-empty target attributes are kept, with BrowserGym data stripped from the string
    assert doc0[1] == [0, 2]
    assert doc1[0] == [0, 2]
    assert dom_snapshot["strings"][2] == "keep me"
    # unmarked values are left untouched
    assert doc0[5] == [0, 5]
    assert dom_snapshot["strings"][5] == "plain"
    # shared strings are only processed once
    assert doc0[6] == [0, 6]
    assert doc0[7] == [0, 6]
    assert dom_snapshot["strings"][6] == "browsergym_id_legit"
    # nodes without attributes and other attribute names are untouched
    assert doc0[3] == []
    assert doc0[8] == [7, 1]


def test_pop_bids_from_attribute_missing_attribute_name():
    dom_snapshot = _make_dom_snapshot(
        ["id", "browsergym_id_0 ", "aria-label"],
        [[[0, 1], [2, 1]]],
    )
    expected = copy.deepcopy(dom_snapshot)

    pop_bids_from_attribute(dom_snapshot, "aria-description")

    assert dom_snapshot == expected


# --- _pre_extract / _post_extract frame branches (fake playwright objects) ---


class _FakeElement:
    def __init__(self, attributes=None, content_frame=None):
        self.attributes = attributes or {}
        self._content_frame = content_frame

    def get_attribute(self, name):
        return self.attributes.get(name)

    def content_frame(self):
        return self._content_frame


class _FakeFrame:
    def __init__(self, name="", attributes=None, child_frames=(), detached=False, error=None):
        self.name = name
        self.child_frames = list(child_frames)
        self.detached = detached
        self.error = error
        self.element = _FakeElement(attributes, content_frame=self)
        self.evaluations = []

    def is_detached(self):
        return self.detached

    def frame_element(self):
        if self.error is not None:
            raise self.error
        return self.element

    def evaluate(self, script, args=None):
        if self.error is not None:
            raise self.error
        self.evaluations.append(args)
        return []


def _fake_page(main_frame, other_frames=()):
    return types.SimpleNamespace(main_frame=main_frame, frames=[main_frame, *other_frames])


def test_pre_extract_frame_branches(caplog):
    detached = _FakeFrame("detached", {BID_ATTR: "a"}, detached=True)
    problematic = _FakeFrame("problematic", {BID_ATTR: "b"})
    problematic.element._content_frame = None  # e.g. pdf viewer in <embed>
    sandbox_empty = _FakeFrame("sandbox_empty", {BID_ATTR: "c", "sandbox": ""})
    sandbox_no_scripts = _FakeFrame(
        "sandbox_no_scripts", {BID_ATTR: "d", "sandbox": "allow-forms allow-same-origin"}
    )
    grandchild = _FakeFrame("grandchild", {BID_ATTR: "eA"})
    sandbox_scripts = _FakeFrame(
        "sandbox_scripts",
        {BID_ATTR: "e", "sandbox": "allow-forms allow-scripts"},
        child_frames=[grandchild],
    )
    main = _FakeFrame(
        child_frames=[detached, problematic, sandbox_empty, sandbox_no_scripts, sandbox_scripts]
    )

    with caplog.at_level(logging.WARNING, logger="browsergym.core.observation"):
        _pre_extract(_fake_page(main), tags_to_mark="all")

    assert main.evaluations == [["", BID_ATTR, "all"]]
    assert sandbox_scripts.evaluations == [["e", BID_ATTR, "all"]]
    assert grandchild.evaluations == [["eA", BID_ATTR, "all"]]
    for skipped in (detached, problematic, sandbox_empty, sandbox_no_scripts):
        assert skipped.evaluations == []
    assert "Skipping frame 'problematic' for marking, seems problematic." in caplog.text


def test_pre_extract_child_frame_without_bid(caplog):
    no_bid = _FakeFrame("no_bid", {})
    sibling = _FakeFrame("sibling", {BID_ATTR: "b"})
    main = _FakeFrame(child_frames=[no_bid, sibling])

    with pytest.raises(MarkingError, match="Cannot mark a child frame without a bid"):
        _pre_extract(_fake_page(main))
    assert no_bid.evaluations == []

    main.evaluations.clear()
    with caplog.at_level(logging.WARNING, logger="browsergym.core.observation"):
        _pre_extract(_fake_page(main), lenient=True)
    assert len(main.evaluations) == 1
    assert no_bid.evaluations == []
    assert sibling.evaluations == [["b", BID_ATTR, "standard_html"]]
    assert "Cannot mark a child frame without a bid. Skipping frame." in caplog.text


def test_post_extract_frame_branches(caplog):
    main = _FakeFrame()
    problematic = _FakeFrame("problematic", {BID_ATTR: "a"})
    problematic.element._content_frame = None
    sandbox_empty = _FakeFrame("sandbox_empty", {BID_ATTR: "b", "sandbox": ""})
    sandbox_no_scripts = _FakeFrame("sandbox_no_scripts", {BID_ATTR: "c", "sandbox": "allow-forms"})
    no_bid = _FakeFrame("no_bid", {})
    detached = _FakeFrame(
        "detached", {BID_ATTR: "d"}, error=playwright.sync_api.Error("Frame was detached")
    )
    detached_bis = _FakeFrame(
        "detached_bis", {BID_ATTR: "e"}, error=playwright.sync_api.Error("Frame has been detached.")
    )
    sandbox_scripts = _FakeFrame("sandbox_scripts", {BID_ATTR: "f", "sandbox": "allow-scripts"})
    page = _fake_page(
        main,
        [
            problematic,
            sandbox_empty,
            sandbox_no_scripts,
            no_bid,
            detached,
            detached_bis,
            sandbox_scripts,
        ],
    )

    with caplog.at_level(logging.WARNING, logger="browsergym.core.observation"):
        _post_extract(page)

    assert len(main.evaluations) == 1
    # frames after the detached ones are still unmarked
    assert len(sandbox_scripts.evaluations) == 1
    for skipped in (problematic, sandbox_empty, sandbox_no_scripts, no_bid):
        assert skipped.evaluations == []
    assert "Skipping frame 'problematic' for unmarking, seems problematic." in caplog.text


def test_post_extract_reraises_other_errors():
    main = _FakeFrame()
    broken = _FakeFrame(
        "broken",
        {BID_ATTR: "a"},
        error=playwright.sync_api.Error("Execution context was destroyed"),
    )
    with pytest.raises(playwright.sync_api.Error, match="Execution context was destroyed"):
        _post_extract(_fake_page(main, [broken]))


# --- marking edge cases on real pages ---


def _dom_attributes_by_id(dom_snapshot):
    """Map each DOM element's id attribute to all its attributes (name -> value)."""
    strings = dom_snapshot["strings"]
    elements = {}
    for document in dom_snapshot["documents"]:
        for node_attrs in document["nodes"]["attributes"]:
            attrs = {
                strings[node_attrs[i]]: strings[node_attrs[i + 1]]
                for i in range(0, len(node_attrs), 2)
            }
            if "id" in attrs:
                elements[attrs["id"]] = attrs
    return elements


def test_sandboxed_iframes():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": SANDBOXED_IFRAMES_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()
    page = env.unwrapped.page

    # explicit marking of a page with script-blocked frames does not raise, even when strict
    _pre_extract(page, lenient=False)
    dom = extract_dom_snapshot(page)
    _post_extract(page)

    for snapshot in (dom, obs["dom_object"]):
        elements = _dom_attributes_by_id(snapshot)
        # iframe elements themselves are marked by their parent frame
        for iframe_id in ("sandbox-empty", "sandbox-no-scripts", "sandbox-scripts"):
            assert BID_ATTR in elements[iframe_id]
        # script-blocked frames are skipped (the opaque-origin frame may be absent from the snapshot)
        assert BID_ATTR not in elements.get("sandbox-empty-button", {})
        assert BID_ATTR not in elements["sandbox-no-scripts-button"]
        # frames allowing scripts are marked, with the iframe bid as a prefix
        assert elements["sandbox-scripts-button"][BID_ATTR].startswith(
            elements["sandbox-scripts"][BID_ATTR]
        )
        assert BID_ATTR in elements["main-button"]
        # no BrowserGym data leaks through the ARIA attributes
        for attrs in elements.values():
            assert "aria-description" not in attrs
            assert "aria-roledescription" not in attrs

    # _post_extract cleaned up the ARIA attributes in the main and script-enabled frames
    assert page.get_attribute("#main-button", "aria-description") is None
    scripts_frame = page.frame_locator("#sandbox-scripts")
    assert (
        scripts_frame.locator("#sandbox-scripts-button").get_attribute("aria-description") is None
    )

    env.close()


def test_pre_extract_marking_error_on_iframe_without_bid(caplog):
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": IFRAME_BID_STRIPPED_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )

    # env.reset() retries on MarkingError, then falls back to lenient marking on the last try
    with caplog.at_level(logging.WARNING):
        obs, info = env.reset()
    assert "Cannot mark a child frame without a bid" in caplog.text
    assert "Retrying" in caplog.text
    assert "Cannot mark a child frame without a bid. Skipping frame." in caplog.text
    elements = _dom_attributes_by_id(obs["dom_object"])
    assert BID_ATTR in elements["main-button"]
    assert BID_ATTR not in elements["stripped-iframe"]
    assert BID_ATTR not in elements["inner-button"]

    page = env.unwrapped.page
    inner_frame = page.frame_locator("#stripped-iframe")

    # strict marking raises
    with pytest.raises(MarkingError, match="Cannot mark a child frame without a bid"):
        _pre_extract(page, lenient=False)
    _post_extract(page)
    assert inner_frame.locator("#inner-button").get_attribute(BID_ATTR) is None
    assert page.get_attribute("#main-button", "aria-description") is None

    # lenient marking warns and skips the frame
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="browsergym.core.observation"):
        _pre_extract(page, lenient=True)
    assert "Cannot mark a child frame without a bid. Skipping frame." in caplog.text
    assert page.get_attribute("#main-button", BID_ATTR) is not None
    assert inner_frame.locator("#inner-button").get_attribute(BID_ATTR) is None
    _post_extract(page)
    assert page.get_attribute("#main-button", "aria-description") is None

    env.close()


def test_post_extract_frame_detached_after_marking():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": MULTI_IFRAME_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()
    page = env.unwrapped.page

    _pre_extract(page)
    frames_before = list(page.frames)
    assert len(frames_before) == 3
    assert page.get_attribute("input[name='textfield']", "aria-description") is not None

    # detach an iframe between marking and unmarking
    stale_frame = frames_before[1]
    page.evaluate("document.querySelector('iframe').remove()")
    assert stale_frame.is_detached()

    # playwright reports detached frames with one of the messages _post_extract swallows
    with pytest.raises(playwright.sync_api.Error) as exc_info:
        stale_frame.evaluate("1")
    assert any(
        msg in str(exc_info.value) for msg in ("Frame was detached", "Frame has been detached")
    )

    # unmarking with the live frame list does not raise
    _post_extract(page)
    assert page.get_attribute("input[name='textfield']", "aria-description") is None

    # unmarking with a stale frame list (detach race) does not raise either
    _pre_extract(page)
    _post_extract(types.SimpleNamespace(main_frame=page.main_frame, frames=frames_before))
    assert page.get_attribute("input[name='textfield']", "aria-description") is None

    env.close()


def test_dom_snapshot_preserves_original_aria_attributes():
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": ARIA_ATTRIBUTES_URL},
        headless=__HEADLESS,
        slow_mo=__SLOW_MO,
        viewport=__VIEWPORT,
        timeout=__TIMEOUT,
    )
    obs, info = env.reset()

    dom = obs["dom_object"]
    assert not any(
        s.startswith("browsergym_id_") and s != "browsergym_id_x not ours" for s in dom["strings"]
    )

    elements = _dom_attributes_by_id(dom)
    assert "aria-description" not in elements["no-aria"]
    assert "aria-roledescription" not in elements["no-aria"]
    assert elements["with-description"]["aria-description"] == "Saves the form"
    assert elements["with-roledescription"]["aria-roledescription"] == "slide"
    assert elements["with-multiline-description"]["aria-description"] == "first line\nsecond line"
    assert elements["with-bid-like-description"]["aria-description"] == "browsergym_id_x not ours"
    assert elements["shared-a"]["aria-description"] == "Shared description"
    assert elements["shared-b"]["aria-description"] == "Shared description"
    for element_id, attrs in elements.items():
        assert BID_ATTR in attrs, element_id

    # every element keeps its bid in the AXTree, including the multi-line description
    axtree_bids = {
        node["browsergym_id"] for node in obs["axtree_object"]["nodes"] if "browsergym_id" in node
    }
    for element_id in (
        "no-aria",
        "with-description",
        "with-roledescription",
        "with-multiline-description",
        "with-bid-like-description",
        "shared-a",
        "shared-b",
    ):
        assert elements[element_id][BID_ATTR] in axtree_bids, element_id

    env.close()
