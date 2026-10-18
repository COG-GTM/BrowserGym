"""Screenshot every story of a built Storybook (storybook-static/) with Playwright.

Usage: python scripts/screenshot_stories.py [out_dir]   (serves storybook-static on a free port)
"""

import functools
import http.server
import json
import pathlib
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent / "storybook-static"
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "story-screenshots")
MOBILE = {"trace-viewer-runreplayplayer--mobile"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    entries = json.loads((ROOT / "index.json").read_text())["entries"]
    stories = [k for k, v in entries.items() if v["type"] == "story"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for sid in stories:
            mobile = sid in MOBILE
            page = browser.new_page(
                viewport=(
                    {"width": 414, "height": 896} if mobile else {"width": 1280, "height": 800}
                ),
                device_scale_factor=2 if mobile else 1,
            )
            page.goto(f"{base}/iframe.html?id={sid}&viewMode=story")
            page.wait_for_selector("#storybook-root > *")
            page.wait_for_load_state("networkidle")
            page.evaluate(
                "() => Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => i.onload = i.onerror = r)))"
            )
            page.wait_for_timeout(300)
            page.screenshot(path=str(OUT / f"{sid}.png"), full_page=True)
            page.close()
            print("ok", sid)
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()
