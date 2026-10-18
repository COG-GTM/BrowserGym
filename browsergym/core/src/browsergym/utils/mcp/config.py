import argparse
from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

from browsergym.core.action.highlevel import ACTION_SUBSETS

Transport = Literal["stdio", "streamable-http"]
DemoMode = Literal["off", "default", "all_blue", "only_visible_elements"]

DEFAULT_SUBSETS = ["chat", "infeas", "bid", "nav", "tab"]
DEFAULT_PORT = 8931


@dataclass
class ServerConfig:
    """Settings shared by every browser session served by one MCP server."""

    task_id: str = "browsergym/openended"
    start_url: str = "about:blank"
    goal: Optional[str] = None
    headless: bool = True
    timeout_ms: int = 10000
    subsets: list[str] = field(default_factory=lambda: list(DEFAULT_SUBSETS))
    demo_mode: DemoMode = "off"
    record_video_dir: Optional[str] = None
    viewport_width: int = 1280
    viewport_height: int = 720
    screenshots: bool = True
    allow_upload_file: bool = False
    max_axtree_chars: Optional[int] = None
    transport: Transport = "stdio"
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    path: str = "/mcp"
    log_level: str = "INFO"

    @classmethod
    def from_args(cls, argv: Optional[Sequence[str]] = None, known_only: bool = False):
        parser = build_arg_parser()
        if known_only:
            args, _ = parser.parse_known_args(argv)
        else:
            args = parser.parse_args(argv)
        subsets: list[str] = []
        for item in args.subset or DEFAULT_SUBSETS:
            subsets.extend(s for s in item.split(",") if s)
        return cls(
            task_id=args.task_id,
            start_url=args.start_url,
            goal=args.goal,
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            subsets=subsets,
            demo_mode=args.demo_mode,
            record_video_dir=args.record_video_dir,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            screenshots=args.screenshots,
            allow_upload_file=args.allow_upload_file,
            max_axtree_chars=args.max_axtree_chars,
            transport=args.transport,
            host=args.host,
            port=args.port,
            path=args.path,
            log_level=args.log_level,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m browsergym.utils.mcp",
        description="BrowserGym MCP server (stdio or Streamable HTTP).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # underscore spellings are kept for backwards compatibility with the original mcp_server.py
    parser.add_argument(
        "-t", "--task-id", "--task_id", dest="task_id", default="browsergym/openended"
    )
    parser.add_argument("--start-url", dest="start_url", default="about:blank")
    parser.add_argument("--goal", default=None, help="Initial goal (open-ended task only)")
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Chromium headless",
    )
    parser.add_argument(
        "-l", dest="headless", action="store_const", const=True, help=argparse.SUPPRESS
    )
    parser.add_argument("--timeout-ms", "--timeout_ms", dest="timeout_ms", type=int, default=10000)
    parser.add_argument(
        "--subset",
        action="append",
        default=None,
        help=f"Action subset(s), repeatable or comma-separated. Choices: {', '.join(ACTION_SUBSETS)}. "
        f"Default: {','.join(DEFAULT_SUBSETS)}",
    )
    parser.add_argument(
        "--demo-mode",
        "--demo_mode",
        dest="demo_mode",
        default="off",
        choices=["off", "default", "all_blue", "only_visible_elements"],
    )
    parser.add_argument("-r", "--record-video-dir", "--record_video_dir", dest="record_video_dir")
    parser.add_argument("--viewport-width", dest="viewport_width", type=int, default=1280)
    parser.add_argument("--viewport-height", dest="viewport_height", type=int, default=720)
    parser.add_argument(
        "--screenshots",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Attach a PNG screenshot to every tool result",
    )
    parser.add_argument(
        "--allow-upload-file",
        dest="allow_upload_file",
        action="store_true",
        help="Expose the upload_file tool (lets MCP clients upload files from the server host)",
    )
    parser.add_argument(
        "--max-axtree-chars",
        dest="max_axtree_chars",
        type=int,
        default=None,
        help="Truncate the AXTree text to this many characters",
    )
    parser.add_argument(
        "--transport", default="stdio", choices=["stdio", "streamable-http"], help="MCP transport"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Streamable HTTP bind host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Streamable HTTP port")
    parser.add_argument("--path", default="/mcp", help="Streamable HTTP endpoint path")
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--validate_actions", "--validate-actions", nargs="+", default=None, help=argparse.SUPPRESS
    )  # deprecated no-op: every action now goes through BrowserEnv.step() (always validated)
    return parser
