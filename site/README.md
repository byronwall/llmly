# llmly site

The landing page at <https://byronwall.github.io/llmly/>. It is static: `index.html`, `site.css`, `site.js`, `images/`, `llms.txt`.

## Live demo

`site/demo/` is build output and is not committed. It holds the real viewer (`llmly/templates/index.html` and `llmly/static/`) plus the API answers that llmly computes from a fictional log set. `demo-shim.js` answers the viewer's `/api/*` requests from those files and pins the clock to 4 June 2026, so the default "last 24h" window shows the demo day.

```sh
uv run python site/scripts/build_demo.py      # writes site/demo/ and site/demo/stats.json
```

`site/scripts/demo_logs.py` writes the fictional Copilot, Codex and Claude logs. Every project, prompt and file name in it is made up. Never point the build or the capture at real logs.

## Preview under the Pages base path

```sh
mkdir -p tmp/pages && ln -sfn ../../site tmp/pages/llmly
pnpm dlx http-server@14.1.1 tmp/pages -p 5180 -c-1
```

Open <http://localhost:5180/llmly/>. The `site` entry in `.claude/launch.json` runs the same server.

## Screenshots

```sh
uv run --with playwright==1.58.0 --with pillow python site/scripts/capture.py
```

About 30 seconds. It rebuilds the demo and writes WebP shots at 2x to `site/images/`, plus `og.png` and `apple-touch-icon.png`. The demo clock is pinned, so a reshoot gives the same images.

The numbered pins on the chart card in `index.html` are percentages of `images/card.webp`. Check them after a reshoot.

## Checks

```sh
uv run --with playwright==1.58.0 --with pillow python site/scripts/check_site.py
```

Run after `build_demo.py`. It checks four widths in light and dark mode, links and anchors, the tour tabs, the lightbox and the live demo. Set `CHECK_EXTERNAL=1` to check external links too.

## Deploy

`.github/workflows/pages.yml` runs `build_demo.py` and publishes `site/` on each push to `main` that changes `site/` or `llmly/`.
