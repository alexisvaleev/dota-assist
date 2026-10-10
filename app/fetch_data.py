"""Скачивает данные героев/матчапов/предметов в <user_dir>/data/*.json.

Источники:
  - OpenDota REST (без ключа): герои, винрейты, матчапы, тайминги предметов,
    позиции через laneRoles, личная статистика по account_id.
  - STRATZ GraphQL (опционально, config.stratz_token): точные позиции,
    матчапы с большими выборками. При любой ошибке — откат на OpenDota.

Все файлы обёрнуты {"_meta": {...}, "data": ...} и пишутся атомарно:
при сбое сети старый кэш не трогаем.

Запуск:
  python scripts/fetch_data.py                  # полное обновление
  python scripts/fetch_data.py --stratz-schema  # дамп схемы STRATZ (отладка)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from paths import user_dir  # noqa: E402
from engine.dataload import _num, now_iso  # noqa: E402

DATA = user_dir() / "data"
OD_API = "https://api.opendota.com/api"
STRATZ_API = "https://api.stratz.com/graphql"

CFG: dict = {}
for p in (user_dir() / "config.json", ROOT / "config.json"):
    if p.exists():
        CFG = json.loads(p.read_text(encoding="utf-8"))
        break


def save(name: str, data, source: str, extra_meta: dict | None = None):
    """Атомарная запись {meta, data}: tmp-файл + rename. Плохие данные
    не затирают предыдущий кэш."""
    meta = {"source": source, "fetched_at": now_iso(),
            **(extra_meta or {})}
    payload = {"_meta": meta, "data": data}
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / (name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, DATA / name)
    print(f"  -> {name} ({source}, {len(data)} записей)")


def stamp_fetched(full: bool = True):
    """Маркер свежести: data/_meta.json {"fetched_at": epoch, "full": bool}.
    bootstrap.data_fresh() читает его, чтобы решить, не пора ли
    перекачать кэш. full=False ставит --quick прогон (только heroes+meta)
    — bootstrap.data_full() тогда докачивает остаток. Атомарно, как save()."""
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = DATA / "_meta.json.tmp"
        tmp.write_text(json.dumps({"fetched_at": time.time(), "full": full}),
                       encoding="utf-8")
        os.replace(tmp, DATA / "_meta.json")
    except Exception as e:
        print(f"  _meta.json: {e}")


# ---------------- OpenDota ----------------

def fetch_heroes(client: httpx.Client) -> dict:
    heroes = client.get(f"{OD_API}/heroes").json()
    return {
        str(h["id"]): {
            "id": h["id"], "name": h["name"],
            "localized_name": h["localized_name"],
            "primary_attr": h["primary_attr"],
            "attack_type": h["attack_type"],
            "roles": h["roles"],
        } for h in heroes
    }


def fetch_meta(client: httpx.Client) -> dict:
    stats = client.get(f"{OD_API}/heroStats").json()
    out = {}
    for s in stats:
        hid = s.get("id") or s.get("hero_id")
        if not hid:
            continue
        wr = {str(b): round(s[f"{b}_win"] / s[f"{b}_pick"] * 100, 2)
              for b in range(1, 9) if s.get(f"{b}_pick")}
        picks = int(_num(s.get("pick_count"))) or \
            sum(int(_num(s.get(f"{b}_pick"))) for b in range(1, 9))
        wins = int(_num(s.get("win_count"))) or \
            sum(int(_num(s.get(f"{b}_win"))) for b in range(1, 9))
        out[str(hid)] = {
            "wr_all": round(wins / picks * 100, 2) if picks else 0,
            "wr_bracket": wr,
            "picks": picks,
        }
    return out


def fetch_matchups(client: httpx.Client, hero_ids: list[int]) -> dict:
    """matchups[a][b] = {games, wins, wr} — винрейт a против b."""
    mx = {}
    for i, hid in enumerate(hero_ids):
        rows = client.get(f"{OD_API}/heroes/{hid}/matchups").json()
        mx[str(hid)] = {
            str(r["hero_id"]): {
                "games": int(_num(r.get("games_played"))),
                "wins": int(_num(r.get("wins"))),
                "wr": round(r["wins"] / r["games_played"] * 100, 2)
                if r.get("games_played") else 50.0,
            }
            for r in rows if r.get("hero_id")
        }
        print(f"  matchups {i + 1}/{len(hero_ids)}", flush=True)
        time.sleep(1.0)
    return mx


def fetch_builds(client: httpx.Client, hero_ids: list[int]) -> dict:
    """itemTimings: time — СЕКУНДЫ, games/wins — СТРОКИ. Приводим."""
    out = {}
    for i, hid in enumerate(hero_ids):
        try:
            rows = client.get(f"{OD_API}/scenarios/itemTimings",
                              params={"hero_id": hid}).json()
        except Exception:
            rows = []
        items = []
        for r in rows:
            games = int(_num(r.get("games")))
            wins = int(_num(r.get("wins")))
            t_s = int(_num(r.get("time")))
            if games <= 20 or not r.get("item"):
                continue
            items.append({
                "item": r["item"],
                "time_s": t_s,
                "min": round(t_s / 60, 1),
                "games": games,
                "wr": round(wins / games * 100, 1),
            })
        items.sort(key=lambda x: (x["time_s"], -x["games"]))
        out[str(hid)] = items
        print(f"  builds {i + 1}/{len(hero_ids)}", flush=True)
        time.sleep(1.0)
    return out


def fetch_lane_roles(client: httpx.Client, hero_ids: list[int],
                     heroes: dict) -> dict:
    """Позиции из laneRoles: lane 1=safe, 2=mid, 3=off, 4=jungle.
    safe-лейн делим между pos1/pos5 по тегу Carry/Support, off — pos3/pos4.
    Грубо, но лучше, чем ничего; STRATZ перезапишет точными данными."""
    out = {}
    for i, hid in enumerate(hero_ids):
        try:
            rows = client.get(f"{OD_API}/scenarios/laneRoles",
                              params={"hero_id": hid}).json()
        except Exception:
            rows = []
        games = {int(_num(r.get("lane_role"))): int(_num(r.get("games")))
                 for r in rows if r.get("lane_role")}
        total = sum(games.values())
        if not total:
            continue
        roles = set(heroes.get(str(hid), {}).get("roles", []))
        carry = "Carry" in roles
        supp = "Support" in roles
        pos = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
        pos[2] += games.get(2, 0)
        safe, off, jung = games.get(1, 0), games.get(3, 0), games.get(4, 0)
        if carry and not supp:
            pos[1] += safe
            pos[3] += off * 0.7
            pos[4] += off * 0.3
        elif supp and not carry:
            pos[5] += safe
            pos[4] += off * 0.6
            pos[3] += off * 0.4
        else:
            pos[1] += safe * 0.5
            pos[5] += safe * 0.5
            pos[3] += off * 0.5
            pos[4] += off * 0.5
        pos[3] += jung * 0.6
        pos[4] += jung * 0.4
        out[str(hid)] = {str(p): round(v / total, 3)
                         for p, v in pos.items() if v}
        print(f"  positions {i + 1}/{len(hero_ids)}", flush=True)
        time.sleep(1.0)
    return out


def fetch_profile(client: httpx.Client) -> dict | None:
    """Личная статистика героев (OpenDota /players/<id>/heroes).
    Требуется config.account_id и открытая статистика."""
    acc = CFG.get("account_id")
    if not acc:
        return None
    try:
        rows = client.get(f"{OD_API}/players/{acc}/heroes").json()
    except Exception as e:
        print(f"  profile: {e}", flush=True)
        return None
    out = {}
    for r in rows:
        g = int(_num(r.get("games")))
        if g:
            out[str(r["hero_id"])] = {
                "games": g,
                "wr": round(r["win"] / g * 100, 1),
            }
    return out


# ---------------- STRATZ (best-effort) ----------------

def stratz_gql(client: httpx.Client, query: str, variables=None) -> dict:
    token = CFG.get("stratz_token")
    if not token:
        raise RuntimeError("нет stratz_token")
    r = client.post(
        STRATZ_API, json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {token}",
                 "User-Agent": "STRATZ_API"}, timeout=60)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(body["errors"][0].get("message", "?"))
    return body["data"]


def stratz_schema_dump(client: httpx.Client):
    """Печатает поля heroStats — нужно один раз, чтобы подобрать запросы."""
    q = "{__type(name:\"HeroStatsQueryType\"){fields{name args{name type{kind name ofType{kind name ofType{kind name}}}}}}}"
    try:
        data = stratz_gql(client, q)
    except Exception as e:
        print(f"STRATZ schema failed: {e}")
        return
    print(json.dumps(data, ensure_ascii=False, indent=2)[:12000])


def fetch_stratz_matchups(client: httpx.Client, hero_ids: list[int],
                          bracket: int | None) -> tuple[dict, dict] | None:
    """Матчапы и синергии из STRATZ matchUp {vs, with}.
    bracket: bracketBasicIds (HERALD=1..IMMORTAL=8), None = все."""
    bracket_arg = f", bracketBasicIds: [{bracket}]" if bracket else ""
    mx, syn = {}, {}
    try:
        for i, hid in enumerate(hero_ids):
            q = """{ heroStats { matchUp(heroId: %d%s, take: 200) {
                vs { heroId2 matchCount winCount winsAverage }
                with { heroId2 matchCount winCount winsAverage } } } }""" \
                % (hid, bracket_arg)
            mu = stratz_gql(client, q)["heroStats"]["matchUp"]
            mx[str(hid)] = {
                str(r["heroId2"]): {
                    "games": int(r["matchCount"]),
                    "wins": int(r["winCount"]),
                    "wr": round(r["winCount"] / r["matchCount"] * 100, 2)
                    if r["matchCount"] else 50.0,
                } for r in (mu.get("vs") or [])
            }
            syn[str(hid)] = {
                str(r["heroId2"]): {
                    "games": int(r["matchCount"]),
                    "wins": int(r["winCount"]),
                    "wr": round(r["winCount"] / r["matchCount"] * 100, 2)
                    if r["matchCount"] else 50.0,
                } for r in (mu.get("with") or [])
            }
            print(f"  stratz matchUp {i + 1}/{len(hero_ids)}", flush=True)
            time.sleep(0.3)
        return mx, syn
    except Exception as e:
        print(f"  STRATZ matchups failed: {e} — остаёмся на OpenDota",
              flush=True)
        return None


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stratz-schema", action="store_true",
                    help="дамп схемы heroStats и выход")
    ap.add_argument("--quick", action="store_true",
                    help="только heroes/meta (без матчапов и билдов)")
    args = ap.parse_args(argv)

    with httpx.Client(timeout=60) as client:
        if args.stratz_schema:
            stratz_schema_dump(client)
            return

        print("heroes…", flush=True)
        heroes = fetch_heroes(client)
        save("heroes.json", heroes, "opendota")
        hero_ids = sorted(int(h) for h in heroes)

        print("meta…", flush=True)
        save("meta.json", fetch_meta(client), "opendota")

        if args.quick:
            stamp_fetched(full=False)
            print("done (quick)")
            return

        # STRATZ matchups покрывают vs+with с большими выборками;
        # если токена нет или запрос упал — OpenDota-only матчапы.
        bracket = CFG.get("mmr_bracket")
        got_stratz = False
        if CFG.get("stratz_token"):
            print("stratz matchups…", flush=True)
            res = fetch_stratz_matchups(client, hero_ids, bracket)
            if res:
                mx, syn = res
                save("matchups.json", mx, "stratz")
                save("synergies.json", syn, "stratz")
                got_stratz = True

        if not got_stratz:
            print("matchups (OpenDota, ~%d мин)…" % len(hero_ids), flush=True)
            save("matchups.json", fetch_matchups(client, hero_ids), "opendota")

        print("positions…", flush=True)
        save("positions.json",
             fetch_lane_roles(client, hero_ids, heroes), "opendota")

        print("builds…", flush=True)
        save("builds.json", fetch_builds(client, hero_ids), "opendota")

        print("profile…", flush=True)
        prof = fetch_profile(client)
        if prof:
            save("profile.json", prof, "opendota")
        else:
            print("  пропущено (нет account_id или профиль закрыт)")

    stamp_fetched()
    print("done")


if __name__ == "__main__":
    sys.exit(main())
