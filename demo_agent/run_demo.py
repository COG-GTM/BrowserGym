"""Command line entry point for the BrowserGym demo agent.

python run_demo.py --dry-run                  # offline, deterministic mock LLM, headless
python run_demo.py run --provider anthropic   # real LLM, interactive chat on --start-url
python run_demo.py models                     # default models and pricing used for cost logs
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from llm import DEFAULT_MODELS, PRICING_PER_MTOK, PROVIDERS, LLMError

HERE = Path(__file__).resolve().parent
DRY_RUN_PAGE = (HERE / "pages" / "dry_run.html").as_uri()
DRY_RUN_GOAL = "Look around the page and report its title and how many elements it has."
SUBCOMMANDS = ("run", "models")

BANNER = """\
--- WARNING ---
This is a basic agent for demo purposes.
Visit AgentLab for more capable agents with advanced features.
https://github.com/ServiceNow/AgentLab"""


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_demo.py",
        description="BrowserGym demo agent. Without a subcommand, 'run' is assumed.",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run the agent on a BrowserGym task (default)")
    llm = run.add_argument_group("LLM")
    llm.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=os.getenv("DEMO_AGENT_PROVIDER", "openai"),
        help="LLM provider (env: DEMO_AGENT_PROVIDER, default: openai).",
    )
    llm.add_argument(
        "--model",
        "--model_name",
        dest="model",
        default=os.getenv("DEMO_AGENT_MODEL"),
        help="Model name (env: DEMO_AGENT_MODEL). Defaults per provider: "
        + ", ".join(f"{k}={v}" for k, v in DEFAULT_MODELS.items()),
    )
    llm.add_argument(
        "--max-retries",
        type=int,
        default=_env_int("DEMO_AGENT_MAX_RETRIES", 4),
        help="Retries with exponential backoff on rate limits / transient API errors (default: 4).",
    )
    llm.add_argument(
        "--dry-run",
        action="store_true",
        help="Use the deterministic mock LLM (no API key, no LLM network calls). Defaults to a "
        "bundled local page, a fixed goal and headless mode.",
    )

    task = run.add_argument_group("task")
    task.add_argument(
        "--task",
        "--task_name",
        dest="task",
        default="openended",
        help="BrowserGym task id. 'openended' runs on --start-url (default: openended).",
    )
    task.add_argument(
        "--start-url",
        "--start_url",
        dest="start_url",
        default=None,
        help="Start URL for the openended task (default: https://www.google.com, or a bundled "
        "local page with --dry-run).",
    )
    task.add_argument(
        "--goal",
        default=None,
        help="Goal for the openended task. With a goal the agent runs autonomously and stops "
        "after answering; without one it chats interactively with you.",
    )
    task.add_argument("--max-steps", type=int, default=None, help="Default: 100 (10 in dry-run).")
    task.add_argument("--seed", type=int, default=None, help="Task seed.")

    browser = run.add_argument_group("browser / observation")
    browser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run Chromium headless (default: headed, headless with --dry-run).",
    )
    browser.add_argument(
        "--visual-effects",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show visual effects when the agent acts.",
    )
    browser.add_argument("--use-html", action=argparse.BooleanOptionalAction, default=False)
    browser.add_argument("--use-axtree", action=argparse.BooleanOptionalAction, default=True)
    browser.add_argument("--use-screenshot", action=argparse.BooleanOptionalAction, default=False)

    out = run.add_argument_group("output")
    out.add_argument("--results-dir", default="./results", help="Default: ./results")
    out.add_argument(
        "--log-level",
        default=os.getenv("DEMO_AGENT_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    sub.add_parser("models", help="list providers, default models and pricing used for cost logs")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in SUBCOMMANDS and argv[0] not in ("-h", "--help")):
        argv.insert(0, "run")
    args = build_parser().parse_args(argv)

    if args.command == "run":
        if args.dry_run:
            args.provider = "mock"
            args.start_url = args.start_url or DRY_RUN_PAGE
            args.goal = args.goal or DRY_RUN_GOAL
            args.headless = True if args.headless is None else args.headless
            args.max_steps = args.max_steps or 10
        args.start_url = args.start_url or "https://www.google.com"
        args.headless = bool(args.headless)
        args.max_steps = args.max_steps or 100
        args.model = args.model if args.model and args.provider != "mock" else None
        args.model = args.model or DEFAULT_MODELS[args.provider]
    return args


def cmd_models() -> int:
    print("provider   default model")
    for provider, model in DEFAULT_MODELS.items():
        print(f"{provider:<10} {model}")
    print("\nUSD per 1M tokens (input / output) used for cost logging:")
    for model, (p_in, p_out) in PRICING_PER_MTOK.items():
        print(f"  {model:<22} {p_in:>6.2f} / {p_out:>6.2f}")
    print("\nOther models: set DEMO_AGENT_PRICE_IN and DEMO_AGENT_PRICE_OUT to log costs.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from agent import DemoAgentArgs

    from browsergym.experiments import EnvArgs, ExpArgs, get_exp_result

    agent_args = DemoAgentArgs(
        model_name=args.model,
        provider=args.provider,
        max_retries=args.max_retries,
        chat_mode=False,
        demo_mode="default" if args.visual_effects else "off",
        use_html=args.use_html,
        use_axtree=args.use_axtree,
        use_screenshot=args.use_screenshot,
    )
    env_args = EnvArgs(
        task_name=args.task,
        task_seed=args.seed,
        max_steps=args.max_steps,
        headless=args.headless,
    )
    if args.task == "openended":
        env_args.task_kwargs = {"start_url": args.start_url}
        if args.goal:
            env_args.task_kwargs["goal"] = args.goal
        else:
            # interactive: the user gives instructions through the chat window
            agent_args.chat_mode = True
            env_args.wait_for_user_message = True

    logging.getLogger(__name__).info(
        "provider=%s model=%s task=%s start_url=%s headless=%s max_steps=%d",
        args.provider,
        args.model,
        args.task,
        args.start_url if args.task == "openended" else "-",
        args.headless,
        args.max_steps,
    )

    try:
        agent_args.make_agent()  # fail fast on a missing API key, before launching the browser
    except LLMError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    exp_args = ExpArgs(env_args=env_args, agent_args=agent_args)
    exp_args.prepare(args.results_dir)
    exp_args.run()

    exp_record = get_exp_result(exp_args.exp_dir).get_exp_record()
    for key, val in exp_record.items():
        print(f"{key}: {val}")
    return 1 if exp_record.get("err_msg") else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "models":
        return cmd_models()
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    print(BANNER, flush=True)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
