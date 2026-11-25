"""Add (or replace) the gate_desk MCP server in a Hermes config.yaml, line-based, no YAML library.

  python config/merge_hermes_mcp.py "%LOCALAPPDATA%/hermes/config.yaml" [--from-backup]

Removes every top-level `mcp_servers` and `tools` entry (inline `{}` or an indented block) and appends
exactly one of each: the MCP server pointing at THIS repo's tools/mcp_server.py and the running Python, and
`tools.tool_search.enabled: 'off'`. Hermes v0.23 otherwise hides MCP tool schemas behind a `tool_search`
bridge once they exceed 5% of the context window, and the 4B model then never calls them; the scripted
harness always sends all six schemas, so parity needs them eager too.
Writes <config>.bak-bae554 first (unless it already exists); --from-backup starts from that backup.
Other settings are kept line-for-line.
shortcut: replaces any existing top-level `tools:` block wholesale; fine for a config that has none (the Dell's).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = "[find_request, get_request, get_zone_rules, get_person_records, get_area_reports, check_policy]"


def merge(text, python, server):
    out, skipping = [], False
    for line in text.splitlines():
        if line[:1] not in (" ", "\t", "", "#", "-"):  # a new top-level key
            skipping = line.split(":", 1)[0].strip() in ("mcp_servers", "tools")
        if not skipping:
            out.append(line)
    while out and not out[-1].strip():
        out.pop()
    block = ["", "mcp_servers:", "    gate_desk:", f"        command: '{python}'", "        args:",
             f"            - '{server}'", "        tools:", f"            include: {TOOLS}",
             "            prompts: false", "            resources: false",
             "", "tools:", "    tool_search:", "        enabled: 'off'"]
    return "\n".join(out + block) + "\n"


if __name__ == "__main__":
    cfg = Path(sys.argv[1]).expanduser()
    bak = cfg.with_name(cfg.name + ".bak-bae554")
    if not bak.exists():
        bak.write_bytes(cfg.read_bytes())
    src = bak if "--from-backup" in sys.argv else cfg
    new = merge(src.read_text(encoding="utf-8"), Path(sys.executable).as_posix(), (REPO / "tools" / "mcp_server.py").as_posix())
    assert new.count("\nmcp_servers:") == 1 and new.count("\ntools:") == 1
    cfg.write_text(new, encoding="utf-8", newline="\n")
    print(f"updated {cfg} (backup: {bak})\n" + "\n".join(new.splitlines()[-14:]))
