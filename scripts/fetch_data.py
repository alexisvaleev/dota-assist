"""Fetch hero/matchup/item data into data/*.json.

Sources:
  - OpenDota REST (free, no key): heroes list, per-bracket winrates, matchups.
  - STRATZ GraphQL (optional, config.stratz_token): position-aware matchup
    and item purchase stats. Best-effort — schema fields are verified live;
    on any error the OpenDota data is kept.

Run:  python scripts/fetch_data.py
"""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OD_API = "https://api.opendota.com/api"
STRATZ_API = "https://api.stratz.com/graphql"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8")) \
    if (ROOT / "config.json").exists() else {}


def fetch_heroes(client: httpx.Client) -> dict[int, dict]:
    """hero_id -> {id, name, localized_name, primary_attr, attack_type, roles}"""
    heroes = client.get(f"{OD_API}/heroes").json()
    out = {}
    for h in heroes:
        out[h["id"]] = {
            "id": h["id"],
            "name": h["name"],                     # npc_dota_hero_axe
            "localized_name": h["localized_name"],
            "primary_attr": h["primary_attr"],
            "attack_type": h["attack_type"],
            "roles": h["roles"],
        }
    return out


def fetch_meta(client: httpx.Client) -> dict[int, dict]:
    """hero_id -> {winrate_all, winrate_by_bracket{1..8}, pick_count}
    Bracket 1..8 ≈ Herald..Immortal."""
    stats = client.get(f"{OD_API}/heroStats").json()
    out = {}
    for s in stats:
        hid = s.get("id") or s.get("hero_id")
        if not hid:
            continue
        wr = {}
        for b in range(1, 9):
            p, w = s.get(f"{b}_pick", 0), s.get(f"{b}_win", 0)
            if p:
                wr[b] = round(w / p * 100, 2)
        picks = s.get("pick_count") or sum(s.get(f"{b}_pick", 0) for b in range(1, 9))
        wins = s.get("win_count") or sum(s.get(f"{b}_win", 0) for b in range(1, 9))
        out[hid] = {
            "winrate_all": round(wins / picks * 100, 2) if picks else 0,
            "winrate_by_bracket": wr,
            "pick_count": picks,
        }
    return out


def fetch_matchups(client: httpx.Client, hero_ids: list[int]) -> dict:
    """matchups[a][b] = games a-vs-b, wins -> winrate of a vs b (0..100)."""
    mx = {}
    for i, hid in enumerate(hero_ids):
        rows = client.get(f"{OD_API}/heroes/{hid}/matchups").json()
        mx[str(hid)] = {
            str(r["hero_id"]): {
                "games": r["games_played"],
                "wins": r["wins"],
                "wr": round(r["wins"] / r["games_played"] * 100, 2)
                if r["games_played"] else 50.0,
            }
            for r in rows
        }
        print(f"  matchups {i + 1}/{len(hero_ids)}", flush=True)
        time.sleep(1.0)  # be polite to free API
    return mx


def fetch_builds(client: httpx.Client, hero_ids: list[int]) -> dict:
    """Item timings per hero -> data/builds.json.
    /scenarios/itemTimings returns [{item, time, wins, games}]:
    'time' is average purchase minute, wins/games let us rank items."""
    out = {}
    for i, hid in enumerate(hero_ids):
        try:
            rows = client.get(
                f"{OD_API}/scenarios/itemTimings",
                params={"hero_id": hid}).json()
        except Exception:
            rows = []
        out[str(hid)] = [
            {
                "item": r["item"],
                "time": r["time"],
                "wr": round(r["wins"] / r["games"] * 100, 1)
                if r.get("games") else 0,
                "games": r.get("games", 0),
            }
            for r in rows if r.get("games", 0) > 20  # drop noise
        ]
        out[str(hid)].sort(key=lambda x: (x["time"], -x["games"]))
        print(f"  builds {i + 1}/{len(hero_ids)}", flush=True)
        time.sleep(1.0)
    return out


def fetch_stratz_items(client: httpx.Client) -> dict | None:
    """Best-effort: top purchased items per hero from STRATZ.
    Schema may drift — treat as optional, fall back to items_template.json."""
    token = CFG.get("stratz_token")
    if not token:
        return None
    query = """
    query HeroItems {
      heroStats {
        itemPurchase(gameVersionId: null) {
          items { itemId winRate matchCount positionIds: position }
        }
      }
    }"""
    try:
        r = client.post(
            STRATZ_API,
            json={"query": query},
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "STRATZ_API",
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  STRATZ items failed ({e}) — используем шаблон", flush=True)
        return None


def main():
    DATA.mkdir(exist_ok=True)
    with httpx.Client(timeout=30) as client:
        print("heroes…", flush=True)
        heroes = fetch_heroes(client)
        (DATA / "heroes.json").write_text(
            json.dumps(heroes, ensure_ascii=False, indent=1), encoding="utf-8")

        print("meta…", flush=True)
        meta = fetch_meta(client)
        (DATA / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

        print("matchups…", flush=True)
        mx = fetch_matchups(client, sorted(heroes))
        (DATA / "matchups.json").write_text(
            json.dumps(mx, ensure_ascii=False), encoding="utf-8")

        print("builds (itemTimings)…", flush=True)
        builds = fetch_builds(client, sorted(heroes))
        (DATA / "builds.json").write_text(
            json.dumps(builds, ensure_ascii=False), encoding="utf-8")

        print("items…", flush=True)
        items = fetch_stratz_items(client)
        if items:
            (DATA / "items_stratz_raw.json").write_text(
                json.dumps(items, ensure_ascii=False), encoding="utf-8")
        else:
            print("  → STRATZ недоступен; базовые билды уже в builds.json, "
                  "ситуативные правила — data/items.json", flush=True)
    print("done")


if __name__ == "__main__":
    sys.exit(main())
