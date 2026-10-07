"""GSI spike: dump every packet Dota sends to gsi_dumps/*.jsonl and print
which fields are actually present.

Run on Windows while a ranked All Pick draft happens:
  python scripts/gsi_dump.py

Then check docs/findings.md — fill in whether draft blocks, team_name,
bans etc. show up in the dumps.
"""
import json
import sys
import time
from pathlib import Path

from flask import Flask, request

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8")) \
    if (ROOT / "config.json").exists() else {}
PORT = int(CFG.get("gsi_port", 3000))
TOKEN = CFG.get("gsi_auth_token", "")

OUT = ROOT / "gsi_dumps"
OUT.mkdir(exist_ok=True)
fp = OUT / (time.strftime("dump_%Y%m%d_%H%M%S") + ".jsonl")

app = Flask("gsi-dump")
seen_keys: set[str] = set()


def flat(d, prefix=""):
    for k, v in (d or {}).items():
        p = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from flat(v, p + ".")
        else:
            yield p


@app.post("/")
def handle():
    data = request.get_json(force=True, silent=True) or {}
    if TOKEN and (data.get("auth") or {}).get("token") != TOKEN:
        return "bad token", 403
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")
    new = set(flat(data)) - seen_keys
    if new:
        seen_keys.update(new)
        print(f"[new keys] {sorted(new)}")
    m = data.get("map") or {}
    print(f"state={m.get('game_state', '?'):45} "
          f"team={(data.get('player') or {}).get('team_name', '?'):8} "
          f"draft={'draft' in data}")
    return "ok", 200


if __name__ == "__main__":
    print(f"GSI dump -> {fp}  (порт {PORT})")
    print("Оставь запущенным на пару рейтинговых драфтов, потом "
          "заполни docs/findings.md")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
