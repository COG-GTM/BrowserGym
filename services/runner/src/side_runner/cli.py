"""CLI entry point (runner contract in docs/side/ARCHITECTURE.md)::

    python -m side_runner --run-id <id> --task <gym_id> --agent-json '<AgentConfig JSON>' \\
      --max-steps <n> --data-dir <SIDE_DATA_DIR> [--goal <text>] [--start-url <url>] \\
      [--headless/--no-headless]

Exit code: 0 when the run ends succeeded/cancelled, 1 when failed, 2 on invalid arguments.
"""

import argparse
import json
import logging
import os
import sys
from typing import Optional, Sequence

from .artifacts import validate_run_id
from .runner import RunConfig, run_episode


def _run_id(value: str) -> str:
    try:
        return validate_run_id(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="side_runner", description=__doc__.split("::")[0])
    p.add_argument("--run-id", required=True, type=_run_id)
    p.add_argument("--task", required=True, help="gym id, e.g. browsergym/openended")
    p.add_argument("--agent-json", required=True, help="AgentConfig JSON object")
    p.add_argument("--max-steps", type=int, default=15)
    p.add_argument("--data-dir", default=os.environ.get("SIDE_DATA_DIR", "./.side-data"))
    p.add_argument("--goal", default=None)
    p.add_argument("--start-url", default=None)
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    # optional extras (not required by the API)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--slow-mo", type=int, default=None, help="override Playwright slow_mo (ms)")
    p.add_argument("--timeout", type=int, default=None, help="override Playwright timeout (ms)")
    p.add_argument("--log-level", default=os.environ.get("SIDE_RUNNER_LOG_LEVEL", "INFO"))
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        agent = json.loads(args.agent_json)
    except json.JSONDecodeError as e:
        parser.error(f"--agent-json is not valid JSON: {e}")
    if not isinstance(agent, dict) or "type" not in agent:
        parser.error("--agent-json must be an object with a 'type' field")
    if args.max_steps < 1:
        parser.error("--max-steps must be >= 1")

    status = run_episode(
        RunConfig(
            run_id=args.run_id,
            task=args.task,
            agent=agent,
            max_steps=args.max_steps,
            data_dir=args.data_dir,
            goal=args.goal,
            start_url=args.start_url,
            headless=args.headless,
            seed=args.seed,
            slow_mo=args.slow_mo,
            timeout=args.timeout,
        )
    )
    print(json.dumps({"run_id": args.run_id, "status": status}))
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
