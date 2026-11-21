"""Check the built site the way a visitor uses it. Run after build_demo.py.

    uv run --with playwright==1.58.0 python site/scripts/check_site.py

Serves site/ under /llmly/ and checks: no sideways scroll at four widths, no
console errors or failed requests, every image, local link and #anchor
resolves, tour tabs work by key and by #tour/<id>, the section below the tour
does not move between tabs, the lightbox opens fitted, zooms, steps and closes,
and the live demo loads charts and opens a session.
"""
from __future__ import annotations

import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture import serve  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        fails.append(what)


def main() -> None:
    srv, base = serve()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-mock-keychain", "--password-store=basic"])
        for scheme in ("light", "dark"):
            for w, h in ((1440, 900), (1100, 900), (800, 900), (390, 844)):
                page = browser.new_page(viewport={"width": w, "height": h}, color_scheme=scheme)
                errors: list[str] = []
                page.on("console", lambda m: m.type == "error" and errors.append(m.text))
                page.on("requestfailed", lambda r: errors.append("failed " + r.url))
                page.on("response", lambda r: r.status >= 400 and errors.append(f"{r.status} {r.url}"))
                page.goto(base)
                page.wait_for_load_state("networkidle")
                sw = page.evaluate("document.documentElement.scrollWidth")
                check(sw == w, f"{scheme} {w}px: scrollWidth {sw}")
                check(not errors, f"{scheme} {w}px: no console errors or failed requests {errors[:3]}")
                page.close()

        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base)
        page.wait_for_load_state("networkidle")

        # Images, local links and anchors.
        srcs = page.evaluate("[...document.images].map(i => i.src).filter(Boolean)")
        broken = [u for u in set(srcs) if page.request.get(u).status != 200]
        check(not broken, f"all {len(set(srcs))} images resolve {broken}")
        anchors = page.evaluate("""[...document.querySelectorAll('a[href^="#"]')].map(a => a.getAttribute('href'))
            .filter(h => h.length > 1 && !document.getElementById(h.slice(1)))""")
        check(not anchors, f"all #anchors exist {anchors}")
        hrefs = page.evaluate("[...document.querySelectorAll('a[href]')].map(a => a.href)")
        for href in sorted(set(hrefs)):
            url = href.split("#")[0]
            if url.startswith(base):
                code = page.request.get(url).status
                check(code == 200, f"local link {url} -> {code}")
        if os.environ.get("CHECK_EXTERNAL"):
            for href in sorted({h.split("#")[0] for h in hrefs if not h.startswith(base)}):
                req = urllib.request.Request(href, method="HEAD", headers={"User-Agent": "link-check"})
                try:
                    code = urllib.request.urlopen(req, timeout=15).status
                except Exception as e:  # noqa: BLE001
                    code = getattr(e, "code", str(e))
                check(code == 200, f"external link {href} -> {code}")

        # Copy buttons keep their width.
        btn = page.locator(".copy").first
        w0 = btn.bounding_box()["width"]
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        btn.click()
        check(btn.inner_text() == "✓ Copied", "copy button confirms")
        check(btn.bounding_box()["width"] == w0, "copy button keeps its width")

        # Tour tabs: keyboard, URL, and no shift below the widget.
        tops = []
        page.click("#tab-grid")
        for tab in ("grid", "turns", "tools", "files", "table", "calendar"):
            page.click(f"#tab-{tab}")
            tops.append(page.evaluate("document.querySelector('#fit').getBoundingClientRect().top + scrollY"))
        check(len(set(tops)) == 1, f"section below the tour stays put {set(tops)}")
        page.focus("#tab-calendar")
        page.keyboard.press("ArrowRight")
        check(page.evaluate("document.activeElement.id") == "tab-grid", "ArrowRight wraps to the first tab")
        page.keyboard.press("End")
        check(page.evaluate("location.hash") == "#tour/calendar", "URL follows the tab")
        page.goto(base + "#tour/tools")
        page.wait_for_timeout(200)
        check(page.is_visible("#panel-tools") and not page.is_visible("#panel-grid"), "#tour/tools opens that tab")

        # Lightbox.
        page.click("#panel-tools .zoomable")
        page.wait_for_function("document.querySelector('#lbImg').naturalWidth > 0")
        box = page.evaluate("""(() => { const r = document.querySelector('#lbImg').getBoundingClientRect();
            const s = document.querySelector('#lbStage').getBoundingClientRect();
            return {w: r.width, h: r.height, sw: s.width, sh: s.height, inline: document.querySelector('#panel-tools img').getBoundingClientRect().width}; })()""")
        fitted = abs(box["w"] - box["sw"]) < 2 or abs(box["h"] - box["sh"]) < 2
        check(fitted and box["w"] <= box["sw"] + 1 and box["h"] <= box["sh"] + 1, f"lightbox opens fitted {box}")
        check(box["w"] >= box["inline"] - 1, "lightbox image is not smaller than the inline image")
        check(page.evaluate("document.activeElement.id") == "lbClose", "focus moves to Close")
        title = page.inner_text("#lbTitle")
        check("by tool" in title.lower(), f"lightbox names the shot: {title}")
        page.mouse.click(720, 400)
        scale = page.evaluate("new DOMMatrix(getComputedStyle(document.querySelector('#lbImg')).transform).a")
        check(scale > box["w"] / 2880 * 1.4, f"click zooms in ({scale:.2f})")
        page.keyboard.press("ArrowRight")
        check("by file" in page.inner_text("#lbTitle").lower(), "ArrowRight steps to the next shot")
        page.keyboard.press("Escape")
        check(not page.evaluate("document.querySelector('#lightbox').open"), "Esc closes")

        # Live demo.
        demo = page.frame_locator(".demo-frame iframe")
        demo.locator(".card").first.wait_for(timeout=10000)
        cards = demo.locator(".card").count()
        check(cards >= 6, f"demo shows {cards} session charts for the demo day")
        demo.locator(".card").first.click()
        demo.locator(".modal-right .dview").first.wait_for(timeout=10000)
        check(True, "demo opens a session detail")
        html = page.content() + open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo", "api", "sessions-all.json")).read()
        check("/Users/" not in html and "/var/folders" not in html, "no local paths in page or demo data")
        browser.close()
    srv.shutdown()
    print(f"\n{len(fails)} failed" if fails else "\nall checks passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
