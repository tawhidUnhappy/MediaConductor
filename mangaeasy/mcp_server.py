"""`mangaeasy mcp` — an MCP (Model Context Protocol) stdio server.

Exposes the mangaEasy pipeline as typed tools any MCP-capable AI assistant
(Claude Code/Desktop, Cursor, ...) can call. Pure stdlib: MCP's stdio
transport is newline-delimited JSON-RPC 2.0, so no SDK dependency is needed,
and every tool call shells out to the corresponding `mangaeasy` subcommand
(via `runtime.cli_command`), so the lazy-import design and process isolation
are untouched.

Tool schemas come from mangaeasy/command_spec.py — the single declarative
table shared with `mangaeasy commands --json --full`. Add/change tools there,
not here.

Register with e.g. `claude mcp add mangaeasy -- mangaeasy mcp`, or in any
client's config: command `mangaeasy`, args `["mcp"]`.

Notes for tool authors: stdout carries ONLY JSON-RPC messages; anything else
goes to stderr. LONG-RUNNING work must go through the `job_start` /
`job_status` tools — a blocking tools/call that runs for minutes to hours
will hit any client's timeout.
"""

from __future__ import annotations

import json
import subprocess
import sys

from mangaeasy import __version__
from mangaeasy.command_spec import JSON_COMMANDS, TOOLS
from mangaeasy.runtime import cli_command, popen_kwargs

PROTOCOL_VERSION = "2024-11-05"
MAX_OUTPUT_CHARS = 8000

# Backwards-compatible alias (tests and external references).
_JSON_COMMANDS = JSON_COMMANDS


def _build_args(tool: str, arguments: dict) -> list[str]:
    cli_name, _desc, props, required, flags = TOOLS[tool]
    missing = [name for name in required if arguments.get(name) in (None, "", [])]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(missing)}")
    args: list[str] = []
    # Iterate in SPEC order, not client-dict order: positionals (e.g.
    # job_start's command + args) must land in the argv position the spec
    # defines, regardless of the JSON key order the client happened to send.
    for prop, (flag, kind) in flags.items():
        value = arguments.get(prop)
        if value is None:
            continue
        if kind == "positional":
            args.append(str(value))
        elif kind == "positional-list":
            args.extend(str(v) for v in value or [])
        elif kind == "flag":
            if value:
                args.append(flag)
        elif kind == "no-flag":
            if value is False:
                args.append(flag)
        elif kind == "list":
            if value:
                args.extend([flag, *[str(v) for v in value]])
        elif kind == "repeat":
            for v in value or []:
                args.extend([flag, str(v)])
        else:  # value
            args.extend([flag, str(value)])
    if cli_name in JSON_COMMANDS:
        args.append("--json")
    return args


def _clip(text: str, limit: int) -> str:
    """Head+tail truncation: errors usually sit at one end or the other."""
    if len(text) <= limit:
        return text
    head = limit // 4
    tail = limit - head
    return text[:head] + f"\n... [{len(text) - limit} chars omitted] ...\n" + text[-tail:]


def _parse_json_report(stdout: str) -> dict | list | None:
    """The report object of a --json command, scanning from the last line up.

    The contract says exactly one JSON object on stdout, but a stray print
    from a dependency after it must not blind the parser — so walk backwards
    to the first parseable JSON line instead of trusting line ordering.
    """
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not (line.startswith("{") or line.startswith("[")):
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def _run_tool(tool: str, arguments: dict) -> tuple[str, bool]:
    """Run the tool's CLI command; returns (text content, is_error)."""
    cli_name = TOOLS[tool][0]
    argv = cli_command(cli_name, *_build_args(tool, arguments))
    print(f"[mcp] run: {' '.join(argv)}", file=sys.stderr, flush=True)
    proc = subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8", errors="replace", **popen_kwargs()
    )
    stdout = proc.stdout or ""
    stderr = (proc.stderr or "").strip()

    result_payload = None
    for line in stdout.splitlines():
        if line.startswith("MANGAEASY_RESULT "):
            try:
                result_payload = json.loads(line[len("MANGAEASY_RESULT "):])
            except ValueError:
                pass

    body: dict = {"exit_code": proc.returncode}
    if result_payload is not None:
        body["result"] = result_payload
    if cli_name in JSON_COMMANDS:
        report = _parse_json_report(stdout)
        if report is not None:
            body["report"] = report
        else:
            body["output"] = _clip(stdout, MAX_OUTPUT_CHARS)
    else:
        body["output"] = _clip(stdout, MAX_OUTPUT_CHARS)
    if stderr:
        body["stderr"] = _clip(stderr, 2000)
    return json.dumps(body, ensure_ascii=False, indent=2), proc.returncode != 0


def _tools_list() -> list[dict]:
    return [
        {
            "name": name,
            "description": desc,
            "inputSchema": {"type": "object", "properties": props, "required": required},
        }
        for name, (_cli, desc, props, required, _flags) in TOOLS.items()
    ]


def _reply(msg_id, result=None, error=None) -> None:
    response: dict = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(msg: dict) -> None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        client_version = params.get("protocolVersion") or PROTOCOL_VERSION
        _reply(msg_id, {
            "protocolVersion": client_version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mangaeasy", "version": __version__},
        })
        return
    if msg_id is None:
        return  # notification (e.g. notifications/initialized) — nothing to answer
    if method == "ping":
        _reply(msg_id, {})
        return
    if method == "tools/list":
        _reply(msg_id, {"tools": _tools_list()})
        return
    if method == "tools/call":
        tool = params.get("name")
        if tool not in TOOLS:
            _reply(msg_id, error={"code": -32602, "message": f"unknown tool: {tool}"})
            return
        try:
            text, is_error = _run_tool(tool, params.get("arguments") or {})
        except ValueError as exc:
            _reply(msg_id, error={"code": -32602, "message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 — must never crash the server loop
            text, is_error = json.dumps({"error": str(exc)}), True
        _reply(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
        return
    _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> int:
    print(f"[mcp] mangaeasy {__version__} MCP server on stdio", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            _handle(msg)
        except Exception as exc:  # noqa: BLE001 — keep serving
            print(f"[mcp] handler error: {exc}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
