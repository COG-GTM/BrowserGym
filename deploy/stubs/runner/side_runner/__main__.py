"""Deploy smoke stub of side_runner (NOT the real services/runner).

Accepts the ARCHITECTURE.md CLI and writes a one-step mock run in the artifact layout,
without launching a browser (the image smoke test covers chromium separately).
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    p = argparse.ArgumentParser(prog="side_runner")
    p.add_argument("--run-id", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--agent-json", required=True)
    p.add_argument("--max-steps", type=int, default=15)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--goal")
    p.add_argument("--start-url")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    a = p.parse_args()

    run_dir = Path(a.data_dir) / "runs" / a.run_id
    (run_dir / "steps").mkdir(parents=True, exist_ok=True)
    run = {
        "id": a.run_id,
        "task_id": a.task,
        "goal": a.goal,
        "agent": json.loads(a.agent_json),
        "status": "running",
        "reward": None,
        "n_steps": 0,
        "max_steps": a.max_steps,
        "created_at": now(),
        "started_at": now(),
        "finished_at": None,
        "error": None,
    }

    def event(**kw):
        with open(run_dir / "events.jsonl", "a") as f:
            f.write(json.dumps({"run_id": a.run_id, "timestamp": now(), **kw}) + "\n")

    def write_run():
        (run_dir / "run.json").write_text(json.dumps(run, indent=2))

    write_run()
    event(type="status", status="running")
    step = {
        "index": 0,
        "action": "send_msg_to_user('deploy stub done')",
        "thought": None,
        "url": a.start_url,
        "reward": 0.0,
        "terminated": True,
        "truncated": False,
        "last_action_error": None,
        "screenshot_url": None,
        "elapsed_ms": 0,
        "timestamp": now(),
    }
    (run_dir / "steps" / "0.json").write_text(json.dumps(step, indent=2))
    event(type="step", step=step)
    chat = {"role": "assistant", "message": "deploy stub done", "timestamp": now()}
    with open(run_dir / "chat.jsonl", "a") as f:
        f.write(json.dumps(chat) + "\n")
    event(type="chat", chat=chat)
    run.update(status="succeeded", n_steps=1, finished_at=now())
    write_run()
    event(type="status", status="succeeded")


if __name__ == "__main__":
    main()
