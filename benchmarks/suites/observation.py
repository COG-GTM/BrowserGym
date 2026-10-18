"""Observation extraction cost: CDP extraction and pure-python post-processing."""

from __future__ import annotations

from browsergym.core.observation import (
    _post_extract,
    _pre_extract,
    extract_dom_extra_properties,
    extract_dom_snapshot,
    extract_focused_element_bid,
    extract_merged_axtree,
    extract_screenshot,
)
from browsergym.utils.obs import flatten_axtree_to_str, flatten_dom_to_str, overlay_som, prune_html

from ..context import Context, collect_garbage, watch_crashes
from ..harness import Runner

GROUP = "obs"
NAMES = [
    "pre_extract",
    "post_extract",
    "dom_snapshot",
    "axtree",
    "focused_bid",
    "extra_properties",
    "screenshot",
    "get_obs",
    "flatten_axtree",
    "flatten_dom",
    "prune_html",
    "som_overlay",
]


def run(runner: Runner, ctx: Context) -> None:
    for size, info in ctx.pages.items():
        if not runner.any_selected(GROUP, NAMES, size):
            continue
        env = ctx.make_env(info.url)
        try:
            env.reset(seed=0)
            _run_size(runner, ctx, size, env)
        finally:
            env.close()


def _run_size(runner: Runner, ctx: Context, size: str, env) -> None:
    page = env.unwrapped.page
    tags_to_mark = env.unwrapped.tags_to_mark
    params = ctx.page_params(size)
    watch_crashes(page, f"obs[{size}]")

    def gc_setup():
        collect_garbage(page)

    # browser round trips get fewer rounds on large pages
    browser_rounds = {"small": 20, "medium": 15, "large": 8}.get(size, 10)
    python_rounds = {"small": 50, "medium": 20, "large": 8}.get(size, 10)

    # --- marking (bid assignment) and its cleanup
    runner.bench(
        GROUP,
        "pre_extract",
        size,
        lambda _: _pre_extract(page, tags_to_mark=tags_to_mark),
        rounds=browser_rounds,
        setup=gc_setup,
        teardown=lambda _: _post_extract(page),
        params=params,
    )
    runner.bench(
        GROUP,
        "post_extract",
        size,
        lambda _: _post_extract(page),
        rounds=browser_rounds,
        setup=lambda: (collect_garbage(page), _pre_extract(page, tags_to_mark=tags_to_mark)),
        params=params,
    )

    # --- raw extraction on a marked page (as done inside BrowserEnv._get_obs)
    def sel(*names: str) -> bool:
        return any(runner.selected(GROUP, n, size) for n in names)

    need_dom = sel("extra_properties", "flatten_axtree", "flatten_dom", "prune_html", "som_overlay")
    need_axtree = sel("flatten_axtree")
    dom = axtree = None
    marked = need_dom or sel("dom_snapshot", "axtree", "focused_bid")
    if marked:
        with runner.guard(f"{GROUP}.mark[{size}]"):
            _pre_extract(page, tags_to_mark=tags_to_mark)
    try:
        runner.bench(
            GROUP,
            "dom_snapshot",
            size,
            lambda _: extract_dom_snapshot(page),
            rounds=browser_rounds,
            setup=gc_setup,
            params=params,
        )
        runner.bench(
            GROUP,
            "axtree",
            size,
            lambda _: extract_merged_axtree(page),
            rounds=browser_rounds,
            setup=gc_setup,
            params=params,
        )
        runner.bench(
            GROUP,
            "focused_bid",
            size,
            lambda _: extract_focused_element_bid(page),
            rounds=browser_rounds,
            setup=gc_setup,
            params=params,
        )
        # inputs for the pure-python benchmarks, only when one of them is selected
        with runner.guard(f"{GROUP}.capture[{size}]"):
            if need_dom:
                dom = extract_dom_snapshot(page)
            if need_axtree:
                axtree = extract_merged_axtree(page)
    finally:
        if marked:
            with runner.guard(f"{GROUP}.unmark[{size}]"):
                _post_extract(page)

    runner.bench(
        GROUP,
        "extra_properties",
        size,
        lambda _: extract_dom_extra_properties(dom, scale_factor=1.0),
        rounds=python_rounds,
        params=params,
    )
    runner.bench(
        GROUP,
        "screenshot",
        size,
        lambda _: extract_screenshot(page),
        rounds=browser_rounds,
        setup=gc_setup,
        params=params,
    )
    # complete observation as returned by env.step()/reset() (without pre_observation_delay)
    runner.bench(
        GROUP,
        "get_obs",
        size,
        lambda _: env.unwrapped._get_obs(),
        rounds=browser_rounds,
        setup=gc_setup,
        params=params,
    )

    # --- pure-python processing used by agents
    if not need_dom:
        return
    extra = extract_dom_extra_properties(dom, scale_factor=1.0)
    with runner.guard(f"{GROUP}.capture_screenshot[{size}]"):
        screenshot = extract_screenshot(page)
    axtree_params = dict(params, axtree_nodes=len(axtree["nodes"]) if axtree else None)
    runner.bench(
        GROUP,
        "flatten_axtree",
        size,
        lambda _: flatten_axtree_to_str(axtree, extra_properties=extra),
        rounds=python_rounds,
        params=axtree_params,
    )
    runner.bench(
        GROUP,
        "flatten_dom",
        size,
        lambda _: flatten_dom_to_str(dom, extra_properties=extra),
        rounds=python_rounds,
        params=params,
    )
    html = flatten_dom_to_str(dom, extra_properties=extra)
    runner.bench(
        GROUP,
        "prune_html",
        size,
        lambda _: prune_html(html),
        rounds=python_rounds,
        params=dict(params, html_chars=len(html)),
    )
    som_params = dict(params, som_marks=sum(1 for p in extra.values() if p.get("set_of_marks")))
    runner.bench(
        GROUP,
        "som_overlay",
        size,
        lambda _: overlay_som(screenshot, extra),
        rounds=python_rounds,
        params=som_params,
    )
