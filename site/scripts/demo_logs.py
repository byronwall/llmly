"""Write a fictional set of Copilot, Codex and Claude session logs.

Every project, prompt, file and number here is made up. The site's live demo and
screenshots read only these logs, never a real transcript.

    uv run python site/scripts/demo_logs.py <out-dir>

Writes <out-dir>/copilot (a VS Code workspaceStorage tree), <out-dir>/codex (a
CODEX_HOME with rollouts and state_5.sqlite) and <out-dir>/claude (a Claude config
dir with projects/*/<sid>.jsonl). The output is the same on every run.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

# The demo day. The site opens the viewer on this day.
DEMO_DAY = datetime(2026, 6, 4, tzinfo=timezone.utc)
DAYS = 75

PROJECTS = ["acme-shop", "trailmap", "ledger-api", "pantry"]

PROMPTS = [
    ("acme-shop", "Add JWT auth to the API and write tests for the middleware"),
    ("acme-shop", "Add pagination to the order history screen"),
    ("acme-shop", "Fix the flaky checkout test on CI"),
    ("acme-shop", "Move the cart badge count to a shared store"),
    ("trailmap", "Render elevation profiles for each trail segment"),
    ("trailmap", "Cache map tiles offline for saved trails"),
    ("trailmap", "Investigate the memory leak in the tile worker pool"),
    ("trailmap", "Add a dark map style that follows the OS setting"),
    ("ledger-api", "Refactor the data layer to use the repository pattern"),
    ("ledger-api", "Migrate the nightly ETL jobs off the legacy scheduler"),
    ("ledger-api", "Write docs for the public REST endpoints"),
    ("ledger-api", "Add a health-check endpoint and wire up alerts"),
    ("ledger-api", "Optimize the monthly balance aggregation query"),
    ("pantry", "Parse recipe URLs into an ingredient list"),
    ("pantry", "Add barcode scanning to the add-item flow"),
    ("pantry", "Group the shopping list by store aisle"),
]

FILES = {
    "acme-shop": ["src/server.ts", "src/routes/api.ts", "src/middleware/auth.ts", "src/models/user.ts",
                  "src/cart/store.ts", "test/auth.test.ts", "test/checkout.test.ts", "package.json"],
    "trailmap": ["src/map/tiles.ts", "src/map/worker.ts", "src/trail/profile.ts", "src/theme.css",
                 "src/trail/segments.ts", "test/profile.test.ts"],
    "ledger-api": ["ledger/repo.py", "ledger/models.py", "ledger/api/routes.py", "ledger/etl/jobs.py",
                   "ledger/etl/schedule.py", "docs/api.md", "tests/test_repo.py", "tests/test_etl.py"],
    "pantry": ["app/recipes/parse.ts", "app/scan/Barcode.tsx", "app/list/aisles.ts", "app/list/List.tsx",
               "test/parse.test.ts"],
}

TESTS = {"acme-shop": "pnpm test", "trailmap": "pnpm vitest run", "ledger-api": "uv run pytest", "pantry": "pnpm test"}


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def write_jsonl(path: str, rows: list[dict], mtime_ms: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    os.utime(path, (mtime_ms / 1000, mtime_ms / 1000))


def plan_session(rng: random.Random, project: str, prompt: str, start_ms: int, turns: int, scale: float,
                 compact_at: int | None = None) -> list[dict]:
    """A list of model turns. Each turn has its tool calls (run before it) and token counts."""
    files = FILES[project]
    out = []
    t = start_ms
    ctx = int(rng.uniform(9000, 14000) * scale)
    for i in range(turns):
        tools = []
        if i == 0:
            tools.append(("user", prompt, "", 0))
        n_tools = rng.choice([1, 1, 2, 2, 3]) if i else 1
        for _ in range(n_tools):
            kind = rng.choices(["read", "grep", "edit", "test"], [4, 2, 3, 2])[0]
            f = rng.choice(files)
            if kind == "read":
                tools.append(("read", f, f"{rng.randint(40, 420)} lines", rng.randint(5, 30)))
            elif kind == "grep":
                word = f.rsplit("/", 1)[-1].split(".")[0]
                tools.append(("grep", word, f"{rng.randint(2, 14)} matches across {rng.randint(1, 5)} files", rng.randint(20, 90)))
            elif kind == "edit":
                tools.append(("edit", f, f"+{rng.randint(3, 60)} -{rng.randint(0, 25)} lines", rng.randint(10, 40)))
            else:
                passed = rng.randint(6, 40)
                failed = rng.choice([0, 0, 0, 1, 2])
                tools.append(("test", TESTS[project], f"Tests: {passed} passed, {failed} failed", rng.randint(1500, 9000)))
        t += int(rng.uniform(40, 260) * 1000)
        if compact_at is not None and i == compact_at:
            out.append({"ts": t, "compact": True, "tools": []})
            ctx = int(ctx * 0.35)
            t += 20000
        ctx += int(rng.uniform(2500, 9000) * scale)
        hit = 0.08 if i == 0 else min(0.96, rng.uniform(0.55, 0.97))
        out.append({
            "ts": t, "tools": tools, "input": ctx, "cached": int(ctx * hit),
            "output": int(rng.uniform(250, 2600) * (1 + scale / 3)),
        })
    return out


# ---------- Copilot ----------

def copilot_tool(kind: str, arg: str) -> tuple[str, str]:
    if kind == "read":
        return "readFile", json.dumps({"filePath": arg})
    if kind == "grep":
        return "grepSearch", json.dumps({"query": arg})
    if kind == "edit":
        return "replaceStringInFile", json.dumps({"filePath": arg})
    return "runInTerminal", json.dumps({"command": arg})


def copilot_rows(plan: list[dict], model: str, effort: str, debug: str) -> list[dict]:
    rows = []
    for turn in plan:
        for k, arg, res, dur in turn["tools"]:
            ts = turn["ts"] - 5000
            if k == "user":
                rows.append({"ts": ts, "type": "user_message", "attrs": {"content": arg}})
                continue
            name, args = copilot_tool(k, arg)
            rows.append({"ts": ts, "type": "tool_call", "name": name, "dur": dur, "status": "ok",
                         "attrs": {"args": args, "result": res}})
        if turn.get("compact"):
            rows.append({"ts": turn["ts"], "type": "llm_request", "status": "ok", "attrs": {
                "debugName": "summarizeConversationHistory", "model": model, "inputTokens": 0,
                "cachedTokens": 0, "outputTokens": 0}})
            continue
        uncached = turn["input"] - turn["cached"]
        # About 3 AIC per 100k fresh input tokens, so Copilot sits near the other sources.
        nano = int((uncached * 3 + turn["cached"] * 0.3 + turn["output"] * 15) * 1e5)
        rows.append({"ts": turn["ts"], "type": "llm_request", "status": "ok", "attrs": {
            "debugName": debug, "model": model, "inputTokens": turn["input"], "cachedTokens": turn["cached"],
            "outputTokens": turn["output"], "ttft": 900, "copilotUsageNanoAiu": nano,
            "requestOptions": {"reasoning": {"effort": effort}}}})
    return rows


def write_copilot(root: str, rng: random.Random, sid: str, project: str, prompt: str, start_ms: int,
                  turns: int, scale: float, sub: bool, compact: bool) -> None:
    model = rng.choice(["gpt-5.4", "claude-sonnet-4.6", "gpt-5.4"])
    effort = rng.choice(["medium", "high"])
    d = os.path.join(root, f"ws-{project}", "GitHub.copilot-chat", "debug-logs", sid)
    plan = plan_session(rng, project, prompt, start_ms, turns, scale, compact_at=turns // 2 if compact else None)
    end = plan[-1]["ts"]
    write_jsonl(os.path.join(d, "main.jsonl"), copilot_rows(plan, model, effort, "panel/editAgent"), end)
    if sub:
        sub_plan = plan_session(rng, project, f"Find the tests that cover {rng.choice(FILES[project])}",
                                plan[1]["ts"] + 10000, 3, scale * 0.6)
        write_jsonl(os.path.join(d, "runSubagent-1.jsonl"), copilot_rows(sub_plan, model, effort, "runSubagent"), end)


# ---------- Codex ----------

def codex_tool(kind: str, arg: str) -> tuple[str, str]:
    if kind == "read":
        return "exec_command", json.dumps({"cmd": f"sed -n '1,200p' {arg}"})
    if kind == "grep":
        return "exec_command", json.dumps({"cmd": f"rg -n {arg}"})
    if kind == "edit":
        return "apply_patch", json.dumps({"input": f"*** Update File: {arg}"})
    return "exec_command", json.dumps({"cmd": arg})


def codex_rows(tid: str, project: str, plan: list[dict], model: str, effort: str) -> list[dict]:
    t0 = plan[0]["ts"] - 60000
    rows = [{"timestamp": iso(t0), "type": "session_meta", "payload": {
        "id": tid, "cwd": f"/work/{project}", "source": "cli", "model_provider": "openai"}}]
    rows.append({"timestamp": iso(t0), "type": "turn_context", "payload": {"model": model, "effort": effort}})
    n = 0
    for turn in plan:
        for k, arg, res, _dur in turn["tools"]:
            ts = iso(turn["ts"] - 5000)
            if k == "user":
                rows.append({"timestamp": ts, "type": "event_msg", "payload": {"type": "user_message", "message": arg}})
                continue
            n += 1
            name, args = codex_tool(k, arg)
            rows.append({"timestamp": ts, "type": "response_item", "payload": {
                "type": "function_call", "name": name, "call_id": f"call_{n}", "arguments": args}})
            rows.append({"timestamp": ts, "type": "response_item", "payload": {
                "type": "function_call_output", "call_id": f"call_{n}", "output": res}})
        if turn.get("compact"):
            rows.append({"timestamp": iso(turn["ts"]), "type": "compacted", "payload": {"message": ""}})
            continue
        rows.append({"timestamp": iso(turn["ts"] - 1000), "type": "response_item", "payload": {"type": "reasoning", "summary": []}})
        rows.append({"timestamp": iso(turn["ts"]), "type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": turn["input"], "cached_input_tokens": turn["cached"],
                                 "output_tokens": turn["output"], "reasoning_output_tokens": turn["output"] // 3,
                                 "total_tokens": turn["input"] + turn["output"]}}}})
    return rows


def write_codex(root: str, rng: random.Random, threads: list, edges: list, tid: str, project: str, prompt: str,
                start_ms: int, turns: int, scale: float, sub: bool, compact: bool) -> None:
    model = rng.choice(["gpt-5.5", "gpt-5.5", "gpt-5.4-mini"])
    effort = rng.choice(["medium", "high", "xhigh"])
    plan = plan_session(rng, project, prompt, start_ms, turns, scale, compact_at=turns // 2 if compact else None)

    def add(thread_id: str, plan: list, first: str, source: str, nick=None, role=None, tsrc=None):
        day = datetime.fromtimestamp(plan[0]["ts"] / 1000, timezone.utc)
        path = os.path.join(root, "sessions", day.strftime("%Y/%m/%d"), f"rollout-{day:%Y-%m-%dT%H-%M-%S}-{thread_id}.jsonl")
        write_jsonl(path, codex_rows(thread_id, project, plan, model, effort), plan[-1]["ts"])
        threads.append((thread_id, path, plan[0]["ts"] - 60000, plan[-1]["ts"], source, f"/work/{project}",
                        first, sum(p.get("input", 0) for p in plan), first, nick, role, model, effort, tsrc))

    add(tid, plan, prompt, "cli")
    if sub:
        child = tid[:-4] + "c0de"
        nick = rng.choice(["Curie", "Hopper", "Lovelace", "Noether"])
        sub_plan = plan_session(rng, project, f"Review the diff for {rng.choice(FILES[project])}",
                                plan[1]["ts"] + 15000, 3, scale * 0.7)
        src = json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": tid, "agent_nickname": nick, "agent_role": "reviewer"}}})
        add(child, sub_plan, sub_plan[0]["tools"][0][1], src, nick, "reviewer", "subagent")
        edges.append((tid, child))


def write_codex_db(root: str, threads: list, edges: list) -> None:
    con = sqlite3.connect(os.path.join(root, "state_5.sqlite"))
    con.execute("""create table threads (
        id text primary key, rollout_path text not null, created_at_ms integer not null,
        updated_at_ms integer not null, source text not null, model_provider text not null default 'openai',
        cwd text not null, title text not null, sandbox_policy text not null default 'workspace-write',
        approval_mode text not null default 'on-request', tokens_used integer not null default 0,
        has_user_event integer not null default 1, archived integer not null default 0,
        archived_at integer, git_sha text, git_branch text, git_origin_url text,
        cli_version text not null default '', first_user_message text not null default '',
        agent_nickname text, agent_role text, memory_mode text not null default 'enabled',
        model text, reasoning_effort text, agent_path text, created_at_ms_extra integer,
        updated_at_ms_extra integer, thread_source text, preview text not null default '')""")
    con.execute("create table thread_spawn_edges (parent_thread_id text not null, child_thread_id text primary key, status text not null)")
    con.executemany("""insert into threads (id, rollout_path, created_at_ms, updated_at_ms, source, cwd, title,
        tokens_used, first_user_message, agent_nickname, agent_role, model, reasoning_effort, thread_source)
        values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", threads)
    con.executemany("insert into thread_spawn_edges values (?, ?, 'closed')", edges)
    con.commit()
    con.close()


# ---------- Claude ----------

def claude_tool(kind: str, arg: str) -> tuple[str, dict]:
    if kind == "read":
        return "Read", {"file_path": arg}
    if kind == "grep":
        return "Grep", {"pattern": arg}
    if kind == "edit":
        return "Edit", {"file_path": arg, "old_string": "...", "new_string": "..."}
    return "Bash", {"command": arg, "description": "Run the tests"}


def claude_rows(sid: str, project: str, plan: list[dict], model: str, sidechain: bool = False,
                spawn: str | None = None) -> list[dict]:
    rows = []
    n = 0
    base = {"sessionId": sid, "cwd": f"/work/{project}", "isSidechain": sidechain}
    for ti, turn in enumerate(plan):
        for k, arg, res, _dur in turn["tools"]:
            ts = iso(turn["ts"] - 5000)
            if k == "user":
                rows.append({**base, "type": "user", "timestamp": ts, "message": {"role": "user", "content": arg}})
                continue
            n += 1
            name, inp = claude_tool(k, arg)
            rows.append({**base, "type": "assistant", "timestamp": ts, "requestId": f"req_{sid[:6]}_{ti}_t{n}",
                         "message": {"model": model, "content": [{"type": "tool_use", "id": f"tu_{n}", "name": name, "input": inp}]}})
            rows.append({**base, "type": "user", "timestamp": ts, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"tu_{n}", "content": res}]}})
        if turn.get("compact"):
            rows.append({**base, "type": "system", "subtype": "compact_boundary", "timestamp": iso(turn["ts"])})
            continue
        content = [{"type": "text", "text": "Done with this step."}]
        if spawn and ti == 1:
            content = [{"type": "tool_use", "id": "tu_agent", "name": "Agent", "input": {
                "subagent_type": "Explore", "description": "Map the code paths", "prompt": spawn}}]
        rows.append({**base, "type": "assistant", "timestamp": iso(turn["ts"]), "requestId": f"req_{sid[:6]}_{ti}",
                     "message": {"model": model, "content": content, "stop_reason": "end_turn", "usage": {
                         "input_tokens": max(1, turn["input"] - turn["cached"] - 800),
                         "cache_creation_input_tokens": 800 if ti else 0,
                         "cache_read_input_tokens": turn["cached"], "output_tokens": turn["output"]}}})
        if spawn and ti == 1:
            rows.append({**base, "type": "user", "timestamp": iso(turn["ts"] + 60000), "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_agent", "content": "Mapped 3 code paths.\nagentId: a1b2c3d4"}]}})
    return rows


def write_claude(root: str, rng: random.Random, sid: str, project: str, prompt: str, start_ms: int,
                 turns: int, scale: float, sub: bool, compact: bool) -> None:
    model = rng.choice(["claude-opus-4-7", "claude-sonnet-4-6", "claude-opus-4-7"])
    plan = plan_session(rng, project, prompt, start_ms, turns, scale, compact_at=turns // 2 if compact else None)
    path = os.path.join(root, "projects", f"-work-{project}", f"{sid}.jsonl")
    spawn = f"Map how {rng.choice(FILES[project])} is used" if sub else None
    write_jsonl(path, claude_rows(sid, project, plan, model, spawn=spawn), plan[-1]["ts"])
    if sub:
        sub_plan = plan_session(rng, project, spawn, plan[1]["ts"] + 8000, 4, scale * 0.5)
        sub_path = os.path.join(root, "projects", f"-work-{project}", sid, "subagents", "agent-a1b2c3d4.jsonl")
        write_jsonl(sub_path, claude_rows(sid, project, sub_plan, "claude-haiku-4-5", sidechain=True), plan[-1]["ts"])


# ---------- Schedule ----------

def main(out: str) -> None:
    rng = random.Random(42)
    copilot_root = os.path.join(out, "copilot")
    codex_root = os.path.join(out, "codex")
    claude_root = os.path.join(out, "claude")
    for d in (copilot_root, codex_root, claude_root):
        os.makedirs(d, exist_ok=True)
    threads: list = []
    edges: list = []
    n = 0
    for back in range(DAYS - 1, -1, -1):
        day = DEMO_DAY - timedelta(days=back)
        weekend = day.weekday() >= 5
        # The demo day is busy; other days follow a work week with a slow ramp up.
        count = 10 if back == 0 else (rng.choice([0, 0, 1]) if weekend else rng.choice([1, 2, 3, 3, 4, 5]))
        if back > 50 and rng.random() < 0.5:
            count = max(0, count - 2)
        for _ in range(count):
            n += 1
            project, prompt = rng.choice(PROMPTS)
            hour = rng.uniform(13, 23)  # 9am to 7pm US Eastern
            start = int((day + timedelta(hours=hour)).timestamp() * 1000)
            busy = back == 0
            turns = rng.randint(6, 12) if busy else rng.randint(4, 11)
            scale = rng.uniform(0.6, 2.2)
            sub = rng.random() < (0.75 if busy else 0.45)
            compact = turns >= 7 and rng.random() < (0.7 if busy else 0.5)
            src = ["copilot", "codex", "claude"][n % 3]
            hexid = f"{rng.getrandbits(64):016x}"
            if src == "copilot":
                write_copilot(copilot_root, rng, f"demo-{hexid[:12]}", project, prompt, start, turns, scale, sub, compact)
            elif src == "codex":
                tid = f"019a{hexid[:4]}-{hexid[4:8]}-7000-8000-{hexid[8:12]}0000"
                write_codex(codex_root, rng, threads, edges, tid, project, prompt, start, turns, scale, sub, compact)
            else:
                sid = f"{hexid[:8]}-{hexid[8:12]}-4{hexid[12:15]}-8000-{rng.getrandbits(48):012x}"
                write_claude(claude_root, rng, sid, project, prompt, start, turns, scale, sub, compact)
    write_codex_db(codex_root, threads, edges)
    print(f"wrote {n} fictional sessions to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tmp/demo-logs")
