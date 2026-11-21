"""Build the site's live demo: the real llmly frontend on fictional logs, with no server.

    uv run python site/scripts/build_demo.py

1. Writes the fictional logs from demo_logs.py to a temp dir.
2. Points llmly at them and saves its real API responses as JSON.
3. Copies the app's template and static files to site/demo/, with demo-shim.js
   in front. The shim answers the app's /api/* fetches from that JSON and pins
   the clock to the demo day.

site/demo/ is build output. It is not committed. The Pages workflow runs this.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(ROOT, "site")
OUT = os.path.join(SITE, "demo")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(SITE, "scripts"))

import demo_logs  # noqa: E402

SOURCES = ["all", "copilot", "codex", "claude"]


def dump(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))


def main() -> None:
    logs = tempfile.mkdtemp(prefix="llmly-demo-")
    demo_logs.main(logs)
    # The analyzer reads these at import time.
    os.environ.update({
        "COPILOT_USAGE_STORAGE": os.path.join(logs, "copilot"),
        "CODEX_USAGE_HOME": os.path.join(logs, "codex"),
        "CLAUDE_USAGE_HOME": os.path.join(logs, "claude"),
        "CLAUDE_DESKTOP_SESSIONS": os.path.join(logs, "no-desktop"),
        "LLMLY_CACHE_DIR": os.path.join(logs, "cache"),
    })
    from llmly import analyzer

    shutil.rmtree(OUT, ignore_errors=True)
    api = os.path.join(OUT, "api")
    sids = set()
    for src in SOURCES:
        rows = []
        for s in analyzer.query_sessions(start_ts=0, end_ts=4e9, limit=100000, source=src):
            summary = analyzer.session_summary(s)
            t0 = (s.main.get("t0") or s.mtime * 1000) / 1000
            # Window and sort inputs for the shim, same as the server's query.
            summary["_q"] = {"t0": t0, "t1": max(s.last_event_ts / 1000, t0)}
            rows.append(summary)
            sids.add(summary["sid"])
        dump(os.path.join(api, f"sessions-{src}.json"), rows)
        for unit in ("aic", "usd"):
            dump(os.path.join(api, f"daily-{src}-{unit}.json"), {"days": {}, **analyzer.daily_usage(src, unit), "took_ms": 3})
    for sid in sids:
        dump(os.path.join(api, "session", sid.replace(":", "_") + ".json"), analyzer.session_detail(analyzer.get_session(sid)))

    shutil.copytree(os.path.join(ROOT, "llmly", "static"), os.path.join(OUT, "static"))
    with open(os.path.join(ROOT, "llmly", "templates", "index.html")) as f:
        html = f.read()
    n = html.count('"/static/')
    assert n == 2, f"expected 2 /static/ links in the template, found {n}"
    html = html.replace('"/static/', '"static/')
    head = '<script src="../demo-shim.js"></script>\n<meta name="robots" content="noindex">\n'
    assert html.count("<head>") == 1
    html = html.replace("<head>", "<head>\n" + head, 1)
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(html)
    shutil.rmtree(logs)
    print(f"demo: {len(sids)} sessions -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
