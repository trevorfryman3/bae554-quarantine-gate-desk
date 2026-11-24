"""Copy a Hermes config.yaml into config/ with secrets redacted (line-based, no YAML library needed).

  python config/export_sanitized.py "%LOCALAPPDATA%/hermes/config.yaml"

Any line whose key looks secret (key, token, secret, password, auth, credential, cookie, bearer)
has its value replaced by <REDACTED>; long base64/hex-like values anywhere are redacted too.
Review the output before committing. .env and auth.json are never read.
"""
import re
import sys
from pathlib import Path

SECRET_KEY = re.compile(r"^(\s*-?\s*[\w.-]*(key|token|secret|passw|auth|credential|cookie|bearer)[\w.-]*\s*:\s*)(.+)$", re.I)
LONG_BLOB = re.compile(r"[A-Za-z0-9_\-+/=]{32,}")


def sanitize(text):
    out = []
    for line in text.splitlines():
        m = SECRET_KEY.match(line)
        if m and m.group(3).strip() not in ("", "null", "[]", "{}"):
            line = m.group(1) + "<REDACTED>"
        out.append(LONG_BLOB.sub("<REDACTED>", line))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    src = Path(sys.argv[1]).expanduser()
    if src.name in (".env", "auth.json"):
        sys.exit("refusing to read credential files")
    dst = Path(__file__).resolve().parent / "hermes_config.sanitized.yaml"
    dst.write_text("# Sanitized copy of the Dell's Hermes config (secrets redacted by export_sanitized.py)\n"
                   + sanitize(src.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {dst}; review it before committing")
