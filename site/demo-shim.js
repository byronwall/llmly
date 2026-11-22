// Runs the real llmly frontend with no server, for the site's live demo.
// build_demo.py saved the app's API responses for a fictional set of logs.
// This file answers the app's /api/* fetches from those files, and pins the
// clock to the evening of the demo day so "last 24h" shows that day.
(() => {
  const NOW = Date.UTC(2026, 5, 4, 23, 30); // 2026-06-04 23:30 UTC
  const offset = NOW - Date.now();
  const RealDate = Date;
  class DemoDate extends RealDate {
    constructor(...args) {
      super(...(args.length ? args : [RealDate.now() + offset]));
    }
    static now() {
      return RealDate.now() + offset;
    }
  }
  window.Date = DemoDate;

  const sortKeys = {
    total_input: (s) => -s.total_input,
    recent: (s) => -s.last_event_ts,
    requests: (s) => -s.n_requests,
    duration: (s) => -s.duration_ms,
    uncached: (s) => -(s.total_input - s.total_cached),
    aic: (s) => -(s.cost_available ? s.total_aic : s.total_input),
  };
  const peak = (s) => {
    let m = 0;
    for (const c of s.main || []) m = Math.max(m, c.cum);
    for (const k of s.kids || []) for (const c of k.calls) m = Math.max(m, c.cum_offset);
    return m;
  };
  const cache = {};
  const load = (name) => (cache[name] ??= RealFetch(`api/${name}`).then((r) => r.json()));
  const json = (data) => new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });

  async function sessions(q) {
    const source = ["copilot", "codex", "claude"].includes(q.get("source")) ? q.get("source") : "all";
    const end = Number(q.get("end_ts")) || NOW / 1000;
    const start = Number(q.get("start_ts")) || end - 24 * 3600;
    const min = Number(q.get("min_tokens")) || 0;
    const limit = Number(q.get("limit")) || 50;
    const sort = q.get("sort") || "total_input";
    const key = sortKeys[sort] || sortKeys.total_input;
    const rows = (await load(`sessions-${source}.json`))
      .filter((s) => s._q.t0 <= end && s._q.t1 >= start && s.total_input >= min)
      .sort((a, b) => key(a) - key(b))
      .slice(0, limit);
    return {
      sessions: rows,
      max_tok: Math.max(0, ...rows.map(peak)),
      took_ms: 4,
      start_ts: start,
      end_ts: end,
      min_tokens: min,
      limit,
      sort,
      source,
    };
  }

  const RealFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    const path = url.pathname;
    if (!path.startsWith("/api/")) return RealFetch(input, init);
    if (path === "/api/sessions") return json(await sessions(url.searchParams));
    if (path.startsWith("/api/session/")) {
      const sid = decodeURIComponent(path.slice("/api/session/".length)).replace(":", "_");
      return RealFetch(`api/session/${encodeURIComponent(sid)}.json`);
    }
    if (path === "/api/daily_usage") {
      const src = url.searchParams.get("source") || "all";
      const unit = url.searchParams.get("unit") === "usd" ? "usd" : "aic";
      return json(await load(`daily-${src}-${unit}.json`));
    }
    return new Response("not in the demo", { status: 404 });
  };
})();
