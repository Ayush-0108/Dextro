"""Write .env interactively so secrets never need to be pasted anywhere else.

    python scripts/make_env.py            # asks for the Snowflake account, login, password and Gemini key
    python scripts/make_env.py --force    # replace an existing .env (the old one is kept as .env.bak)

Starts from .env.example, fills in the values you type (passwords and keys are not echoed), and writes .env with
permissions 600. .env is git-ignored. Option A (password sign-in) is the default; see .env.example for key pairs.
"""
from __future__ import annotations

import argparse
import getpass
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def normalize_account(raw: str) -> str:
    """Return the identifier the Python connector wants (ORGNAME-ACCOUNTNAME, or a legacy locator.region).

    Accepts ORGNAME-ACCOUNTNAME, ORGNAME.ACCOUNTNAME (the SQL form Snowsight sometimes shows), an
    https://ORG-ACCT.snowflakecomputing.com URL, or a Snowsight address app.snowflake.com/<org>/<account>/....
    """
    a = re.sub(r"^https?://", "", raw.strip())
    m = re.match(r"app\.snowflake\.com/([^/#?]+)/([^/#?]+)", a, re.I)
    if m:
        return f"{m.group(1)}-{m.group(2)}".upper()
    a = re.sub(r"\.snowflakecomputing\.com.*$", "", a.split("/")[0], flags=re.I)
    if not a or not re.fullmatch(r"[A-Za-z0-9_.-]+", a):
        raise ValueError(f"not a Snowflake account identifier: {raw!r} (expected something like ORGNAME-ACCOUNTNAME)")
    parts = a.split(".")
    if len(parts) == 2 and not re.search(r"-\d", parts[1]):   # ORG.ACCOUNT, not locator.region (e.g. ap-south-1)
        return f"{parts[0]}-{parts[1]}"
    return a


def quote(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    raise ValueError("values containing both ' and \" are not supported in .env")


def render_env(template: str, values: dict[str, str]) -> str:
    """Template lines KEY=... (active or commented) get the new value; everything else is kept."""
    out, seen = [], set()
    for line in template.splitlines():
        m = re.match(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", line)
        if m and m.group(1) in values and m.group(1) not in seen:
            out.append(f"{m.group(1)}={quote(values[m.group(1)])}")
            seen.add(m.group(1))
        else:
            out.append(line)
    for k, v in values.items():
        if k not in seen:
            out.append(f"{k}={quote(v)}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    env = ROOT / ".env"
    if env.exists() and not args.force:
        sys.exit(".env already exists; run with --force to replace it (a backup is kept as .env.bak)")
    print("Snowflake account identifier: in Snowsight, click your name (bottom left) > Account >\n"
          "'View account details', and copy 'Account identifier' (looks like ORGNAME-ACCOUNTNAME).")
    values = {
        "SNOWFLAKE_ACCOUNT": normalize_account(input("Account identifier: ")),
        "SNOWFLAKE_USER": input("Snowflake login name: ").strip(),
        "SNOWFLAKE_PASSWORD": getpass.getpass("Snowflake password (not shown): "),
    }
    key = getpass.getpass("Gemini API key (not shown; Enter to add it later): ").strip()
    if key:
        values["GEMINI_API_KEY"] = key
    if env.exists():
        shutil.copy2(env, ROOT / ".env.bak")
    env.write_text(render_env((ROOT / ".env.example").read_text(encoding="utf-8"), values), encoding="utf-8")
    env.chmod(0o600)
    print(f"Wrote {env} (only you can read it). Next: python -m datamind check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
