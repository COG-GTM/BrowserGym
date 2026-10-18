"""Generate realistic trace-viewer fixtures by running a real BrowserGym episode.

Runs browsergym/openended on a local page with a scripted action list and writes the
Side artifact layout (contracts/openapi.yaml shapes) to ../fixtures/flight-search/.

Usage (needs browsergym-core + playwright chromium):
    python scripts/make_fixtures.py
"""

import io
import json
import pathlib
import time
from datetime import datetime, timedelta, timezone

import gymnasium as gym
from PIL import Image

import browsergym.core  # noqa: F401  (registers browsergym/openended)
from browsergym.utils.obs import flatten_axtree_to_str

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "fixtures" / "flight-search"
BASE_TIME = datetime(2026, 10, 18, 2, 40, 0, tzinfo=timezone.utc)
GOAL = "Find the cheapest direct Business flight from Paris to Lisbon on Nov 3 and hold it."


def iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def bid_of(page, selector: str) -> str:
    return page.get_attribute(selector, "bid")


def png_bytes(arr) -> bytes:
    img = Image.fromarray(arr).convert("RGB")
    img = img.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def boxes(extra: dict) -> list:
    out = []
    for bid, props in extra.items():
        bbox = props.get("bbox")
        if not bbox or props.get("visibility", 0) < 0.5:
            continue
        out.append(
            {
                "bid": bid,
                "bbox": [round(v, 1) for v in bbox],
                "clickable": bool(props.get("clickable")),
                "som": bool(props.get("set_of_marks")),
            }
        )
    return out


def main() -> None:
    (OUT / "steps").mkdir(parents=True, exist_ok=True)
    env = gym.make(
        "browsergym/openended",
        task_kwargs={"start_url": (HERE / "fixture_page.html").as_uri(), "goal": GOAL},
        viewport={"width": 800, "height": 520},
        headless=True,
        wait_for_user_message=False,
    )
    obs, _ = env.reset(seed=0)
    page = env.unwrapped.page

    plan = [
        (
            "thought",
            "The form is empty. I'll start with the origin field.",
            lambda: f"fill('{bid_of(page, '#from')}', 'Paris')",
        ),
        ("thought", "Now the destination.", lambda: f"fill('{bid_of(page, '#to')}', 'Lisbon')"),
        (
            "thought",
            "Cabin must be Business.",
            lambda: f"select_option('{bid_of(page, '#cabin')}', 'Business')",
        ),
        (
            "thought",
            "Only direct flights are wanted; I'll tick the checkbox.",
            lambda: "click('zz99')",
        ),
        (
            "thought",
            "That bid does not exist. Retrying with the checkbox's real bid.",
            lambda: f"click('{bid_of(page, '#direct')}')",
        ),
        (
            "thought",
            "All filters set. Submitting the search.",
            lambda: f"click('{bid_of(page, '#go')}')",
        ),
        (
            "thought",
            "SH 218 at €389 is the cheapest direct option. Selecting it.",
            lambda: f"click('{bid_of(page, '#results .flight:nth-of-type(2) button')}')",
        ),
        (
            "thought",
            "The flight is held. Reporting back to the user.",
            lambda: "send_msg_to_user('Held SH 218 (12:45 → 14:40, Business, direct) for €389. The hold expires in 15 minutes.')",
        ),
        ("thought", None, lambda: None),
    ]

    chat = [
        {"role": "user", "message": GOAL, "timestamp": iso(BASE_TIME)},
        {
            "role": "assistant",
            "message": "Hi! I am your assistant, how can I help?",
            "timestamp": iso(BASE_TIME),
        },
    ]
    clock = BASE_TIME + timedelta(seconds=1)
    cumulative_reward = 0.0
    n_steps = 0
    for index, (_, thought, make_action) in enumerate(plan):
        action = make_action()
        (OUT / "steps" / f"{index}.png").write_bytes(png_bytes(obs["screenshot"]))
        axtree_txt = flatten_axtree_to_str(
            obs["axtree_object"], extra_properties=obs["extra_element_properties"]
        )
        step = {
            "index": index,
            "action": action,
            "thought": thought,
            "url": "https://skyhop.example/flights",
            "reward": 0.0,
            "terminated": action is None,
            "truncated": False,
            "last_action_error": obs["last_action_error"] or None,
            "screenshot_url": f"/runs/run_flight_search/steps/{index}/screenshot",
            "elapsed_ms": None,
            "timestamp": iso(clock),
            "axtree_txt": axtree_txt,
            "pruned_html": None,
            "focused_element_bid": obs["focused_element_bid"] or None,
        }
        (OUT / "steps" / f"{index}.boxes.json").write_text(
            json.dumps(boxes(obs["extra_element_properties"]))
        )
        n_steps = index + 1
        if action is None:
            step["reward"] = 1.0
            (OUT / "steps" / f"{index}.json").write_text(
                json.dumps(step, indent=2, ensure_ascii=False)
            )
            break
        t0 = time.time()
        obs, reward, terminated, truncated, _ = env.step(action)
        elapsed = int((time.time() - t0) * 1000)
        step["elapsed_ms"] = elapsed
        (OUT / "steps" / f"{index}.json").write_text(json.dumps(step, indent=2, ensure_ascii=False))
        clock += timedelta(milliseconds=elapsed + 2300)
        if action.startswith("send_msg_to_user"):
            chat.append(
                {
                    "role": "assistant",
                    "message": action[len("send_msg_to_user('") : -2],
                    "timestamp": iso(clock),
                }
            )
        cumulative_reward += reward

    chat.insert(
        2,
        {
            "role": "info",
            "message": "Run started: browsergym/openended · scripted agent",
            "timestamp": iso(BASE_TIME),
        },
    )
    run = {
        "id": "run_flight_search",
        "task_id": "browsergym/openended",
        "goal": GOAL,
        "agent": {"type": "scripted", "model": None, "use_screenshot": True, "use_axtree": True},
        "status": "succeeded",
        "reward": 1.0,
        "n_steps": n_steps,
        "max_steps": 15,
        "created_at": iso(BASE_TIME - timedelta(seconds=2)),
        "started_at": iso(BASE_TIME),
        "finished_at": iso(clock),
        "error": None,
    }
    (OUT / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False))
    (OUT / "chat.json").write_text(json.dumps(chat, indent=2, ensure_ascii=False))
    env.close()
    print(f"wrote {n_steps} steps to {OUT}")


if __name__ == "__main__":
    main()
