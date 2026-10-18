"""BrowserGym observation -> Side StepDetail mapping."""

from typing import Any, Optional

from browsergym.utils.obs import flatten_axtree_to_str, flatten_dom_to_str, prune_html


def preprocess_obs(obs: dict) -> dict:
    """Add the text views agents and StepDetail need (``axtree_txt``, ``pruned_html``)."""
    out = dict(obs)
    out["axtree_txt"] = (
        flatten_axtree_to_str(obs["axtree_object"]) if obs.get("axtree_object") else ""
    )
    out["pruned_html"] = (
        prune_html(flatten_dom_to_str(obs["dom_object"])) if obs.get("dom_object") else ""
    )
    return out


def _none_if_empty(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value)
    return value or None


def build_step(
    *,
    run_id: str,
    index: int,
    obs: dict,
    action: Optional[str],
    thought: Optional[str],
    reward: float,
    terminated: bool,
    truncated: bool,
    elapsed_ms: Optional[float],
    timestamp: str,
    has_screenshot: bool,
) -> dict:
    """Build a StepDetail dict (contract schema) from a preprocessed observation."""
    return {
        "index": index,
        "action": action,
        "thought": thought,
        "url": _none_if_empty(obs.get("url")),
        "reward": float(reward),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "last_action_error": _none_if_empty(obs.get("last_action_error")),
        "screenshot_url": f"/runs/{run_id}/steps/{index}/screenshot" if has_screenshot else None,
        "elapsed_ms": None if elapsed_ms is None else round(float(elapsed_ms), 1),
        "timestamp": timestamp,
        "axtree_txt": _none_if_empty(obs.get("axtree_txt")),
        "pruned_html": _none_if_empty(obs.get("pruned_html")),
        "focused_element_bid": _none_if_empty(obs.get("focused_element_bid")),
    }


STEP_SUMMARY_KEYS = (
    "index",
    "action",
    "thought",
    "url",
    "reward",
    "terminated",
    "truncated",
    "last_action_error",
    "screenshot_url",
    "elapsed_ms",
    "timestamp",
)


def step_summary(step: dict) -> dict:
    """The Step (non-detail) view, used in `step` RunEvents."""
    return {k: step[k] for k in STEP_SUMMARY_KEYS}
