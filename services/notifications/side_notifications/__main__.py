from __future__ import annotations

import argparse
import logging
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Side push notification service")
    parser.add_argument("--host", default=os.environ.get("SIDE_NOTIFY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SIDE_NOTIFY_PORT", "8010")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=os.environ.get("SIDE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        "side_notifications.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=None,
    )


if __name__ == "__main__":
    main()
