"""Container healthcheck: GET <url>; healthy if status is in the accepted range.

Usage: python healthcheck.py <url> [--any]   (--any: any HTTP status < 500 counts as up)
"""

import sys
import urllib.error
import urllib.request

url = sys.argv[1]
accept_any = "--any" in sys.argv[2:]
try:
    with urllib.request.urlopen(url, timeout=4) as resp:
        status = resp.status
except urllib.error.HTTPError as e:
    status = e.code
except Exception as e:  # connection refused, timeout, ...
    print(f"unhealthy: {e}")
    sys.exit(1)

ok = status < 500 if accept_any else 200 <= status < 300
print(f"{'healthy' if ok else 'unhealthy'}: {url} -> {status}")
sys.exit(0 if ok else 1)
