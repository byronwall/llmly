"""Reshoot the site's screenshots and og.png from the fictional demo.

    uv run --with playwright==1.58.0 --with pillow python site/scripts/capture.py

Builds site/demo, serves site/ under /llmly/ like GitHub Pages, and writes WebP
shots to site/images/ at 2x scale. The demo pins its clock, so a reshoot gives
the same images. Takes about 30 seconds.
"""
from __future__ import annotations

import functools
import http.server
import io
import os
import subprocess
import sys
import tempfile
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(SITE, "images")


def save(png: bytes, name: str, width: int | None = None) -> None:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if width and img.width != width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    if name.endswith(".png"):
        img.save(os.path.join(IMAGES, name), optimize=True)
    else:
        img.save(os.path.join(IMAGES, name), "WEBP", quality=88, method=6)
    print(f"  {name} {img.width}x{img.height}")


def serve() -> tuple[http.server.ThreadingHTTPServer, str]:
    root = tempfile.mkdtemp(prefix="llmly-pages-")
    os.symlink(SITE, os.path.join(root, "llmly"))
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=root)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/llmly/"


def main() -> None:
    subprocess.run([sys.executable, os.path.join(SITE, "scripts", "build_demo.py")], check=True)
    os.makedirs(IMAGES, exist_ok=True)
    srv, base = serve()
    demo = base + "demo/"
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-mock-keychain", "--password-store=basic"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                                  timezone_id="America/New_York", locale="en-US")
        page = ctx.new_page()

        def open_demo(query: str = "") -> None:
            page.goto(demo + query)
            page.wait_for_selector(".card, #tableWrap table", timeout=10000)
            page.wait_for_timeout(300)

        open_demo()
        save(page.screenshot(), "grid.webp", 2880)
        # The anatomy markers in index.html are placed for this 1680 px crop.
        page.set_viewport_size({"width": 1680, "height": 1000})
        page.wait_for_timeout(300)
        save(page.locator(".card").first.screenshot(), "card.webp")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(300)

        page.locator(".card").first.click()
        page.wait_for_selector(".modal-right .dview")
        page.wait_for_timeout(300)
        save(page.screenshot(), "detail-turns.webp", 2880)
        for view in ("tools", "files"):
            page.click(f'.dview-btn[data-dview="{view}"]')
            page.wait_for_timeout(300)
            save(page.screenshot(), f"detail-{view}.webp", 2880)
        page.click(".dview-btn[data-dview='turns']")

        open_demo("?view=table&hours=168")
        save(page.screenshot(), "table.webp", 2880)

        open_demo("?cal=1")
        page.wait_for_selector("#calendar .cal-cell", timeout=10000)
        page.wait_for_timeout(300)
        save(page.screenshot(), "calendar.webp", 2880)

        # og.png: the site's own first viewport, which leads with the live demo.
        og = browser.new_context(viewport={"width": 1200, "height": 630}, device_scale_factor=1,
                                 color_scheme="light", timezone_id="America/New_York")
        op = og.new_page()
        op.goto(base)
        op.wait_for_timeout(2500)
        save(op.screenshot(), "og.png")
        icon = browser.new_page(viewport={"width": 180, "height": 180})
        icon.goto(base + "icon.svg")
        save(icon.screenshot(), "apple-touch-icon.png")
        browser.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
