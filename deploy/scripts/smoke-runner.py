"""Runner image smoke test: imports + one real headless BrowserGym episode step (no network).

Usage: python smoke-runner.py
"""

import json
import sys
import time

import browsergym.core  # noqa: F401  registers browsergym/openended
from playwright.sync_api import sync_playwright

print("imports ok: browsergym.core", browsergym.core.__version__)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content("<h1>Side</h1>")
    print("playwright chromium ok:", browser.version, "| h1 =", page.inner_text("h1"))
    browser.close()

import gymnasium as gym  # noqa: E402

t0 = time.time()
env = gym.make(
    "browsergym/openended",
    task_kwargs={"start_url": "data:text/html,<button>Hello Side</button>"},
    headless=True,
    wait_for_user_message=False,
)
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step("noop()")
env.close()
summary = {
    "url": obs["url"][:40],
    "axtree_nodes": len(obs["axtree_object"]["nodes"]),
    "screenshot_shape": list(obs["screenshot"].shape),
    "last_action_error": obs["last_action_error"],
    "elapsed_s": round(time.time() - t0, 2),
}
print("browsergym episode ok:", json.dumps(summary))
sys.exit(0 if not obs["last_action_error"] else 1)
