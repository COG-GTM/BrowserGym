"""Start an ASGI app with uvicorn, auto-detecting the module path.

Usage: python serve.py --port 8000 --env-var SIDE_API_APP side_api.main:app app.main:app main:app

The first importable candidate wins unless the env var named by --env-var is set.
"""

import argparse
import importlib
import os
import sys

import uvicorn


def resolve(candidates):
    errors = []
    for spec in candidates:
        module_name, _, attr = spec.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            if e.name and module_name.startswith(e.name):
                errors.append(f"{spec}: {e}")
                continue
            raise
        if hasattr(module, attr or "app"):
            return spec
        errors.append(f"{spec}: no attribute {attr!r}")
    sys.exit("side-deploy: no ASGI app found. Tried:\n  " + "\n  ".join(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--env-var", required=True)
    parser.add_argument("candidates", nargs="+")
    args = parser.parse_args()

    spec = os.environ.get(args.env_var) or resolve(args.candidates)
    print(f"side-deploy: serving {spec} on {args.host}:{args.port}", flush=True)
    uvicorn.run(spec, host=args.host, port=args.port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
