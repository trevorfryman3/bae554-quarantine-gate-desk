"""Minimal stdio MCP server exposing ONLY the six read-only gate-desk tools to Hermes.

Standard library only (newline-delimited JSON-RPC 2.0). Run: python tools/mcp_server.py
Optional env: QGD_DATA_VERSION (default v1), QGD_SNAPSHOT (e.g. t2_partial).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.gate_tools import TOOL_SPECS, dispatch  # noqa: E402
from tools.world import World  # noqa: E402

PROTOCOL = "2024-11-05"


def handle(world, msg):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification (e.g. notifications/initialized): no reply
        return None
    if method == "initialize":
        res = {"protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL),
               "capabilities": {"tools": {}}, "serverInfo": {"name": "gate-desk", "version": world.version}}
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = {"tools": [{"name": s["function"]["name"], "description": s["function"]["description"],
                          "inputSchema": s["function"]["parameters"]} for s in TOOL_SPECS]}
    elif method == "tools/call":
        p = msg.get("params", {})
        out = dispatch(world, p.get("name"), p.get("arguments") or {})
        res = {"content": [{"type": "text", "text": out}], "isError": out.startswith('{"error"')}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def main():
    world = World(os.environ.get("QGD_DATA_VERSION", "v1"), snapshot=os.environ.get("QGD_SNAPSHOT") or None)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(world, json.loads(line))
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
