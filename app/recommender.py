"""Recommendation engine — offline, pure JSON lookups.

Pick phase modes:
  phase 1 (no enemy picks revealed): top heroes by patch winrate
  phases 2-3: sum of matchup winrates vs revealed enemies, weighted by
              lane-opponent role; candidates filtered by bans/picks/roles.

Item phase: core build + situational rules triggered by enemy composition.
"""
import json
from pathlib import Path

from paths import resource_dir

DATA = resource_dir("data")

# lane opponent: my role -> enemy roles that laned against me
LANE_OPPONENT = {
    "carry": ["offlane"],
    "mid": ["mid"],
    "offlane": ["carry"],
    "soft_support": ["hard_support"],
    "hard_support": ["soft_support"],
}


def _load(name: str, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


class Recommender:
    def __init__(self, my_bracket: int | None = None):
        self.heroes = _load("heroes.json", {})          # id -> info
        self.meta = _load("meta.json", {})              # id -> winrates
        self.matchups = _load("matchups.json", {})      # a -> b -> wr
        self.items = _load("items.json", {})            # situational rules
        self.builds = _load("builds.json", {})          # hero_id -> item stats
        self.name2id = {
            v["name"].replace("npc_dota_hero_", ""): int(k)
            for k, v in self.heroes.items()
        }
        self.my_bracket = my_bracket  # 1..8, None = overall

    # ---------- draft ----------

    def hero_id(self, short_name: str) -> int | None:
        return self.name2id.get(short_name)

    def meta_score(self, hid: int) -> float:
        m = self.meta.get(str(hid))
        if not m:
            return 50.0
        if self.my_bracket:
            return m["winrate_by_bracket"].get(str(self.my_bracket),
                                               m["winrate_all"])
        return m["winrate_all"]

    def matchup_score(self, cid: int, eid: int) -> float:
        return self.matchups.get(str(cid), {}).get(str(eid), {}).get("wr", 50.0)

    def recommend_picks(
        self,
        enemy_ids: list[int],
        ally_ids: list[int],
        banned_ids: list[int],
        my_role: str | None,
        enemy_roles: list[str | None],
        top: int = 3,
    ) -> list[tuple[int, float, str]]:
        """Returns [(hero_id, score, reason)] sorted desc."""
        taken = set(enemy_ids) | set(ally_ids) | set(banned_ids)
        lane_opp_roles = set(LANE_OPPONENT.get(my_role or "", []))
        lane_eids = [
            eid for eid, r in zip(enemy_ids, enemy_roles)
            if eid and r in lane_opp_roles
        ]
        out = []
        for hid_s, h in self.heroes.items():
            cid = int(hid_s)
            if cid in taken:
                continue
            base = self.meta_score(cid)
            if not enemy_ids:
                out.append((cid, base, f"мета {base:.1f}%"))
                continue
            score = base * 0.5  # prior keeps meta-relevant heroes afloat
            for eid, r in zip(enemy_ids, enemy_roles):
                w = 2.0 if r in lane_opp_roles else 1.0
                score += w * (self.matchup_score(cid, eid) - 50.0)
            why = f"матчапы {score - base * 0.5:+.1f}"
            out.append((cid, score, why))
        out.sort(key=lambda t: t[1], reverse=True)
        return out[:top]

    # ---------- in game ----------

    def recommend_items(
        self,
        my_hero_id: int,
        enemy_hero_names: list[str],
        gold: int,
        clock_min: int,
        top: int = 5,
    ) -> list[str]:
        """Core build auto-derived from itemTimings (data/builds.json) +
        situational rules from items.json. Items sorted by avg purchase
        time; we suggest the next timed items ahead of clock_min."""
        core = self.builds.get(str(my_hero_id), [])
        # items typically bought within the next ~10 min of game time
        out = [
            r["item"] for r in core
            if clock_min - 5 <= r["time"] <= clock_min + 10
        ]
        if not out:  # fallback: overall most popular for the hero
            out = [r["item"] for r in
                   sorted(core, key=lambda x: -x["games"])[:5]]

        names = {n.lower() for n in enemy_hero_names}
        for rule in self.items.get("rules", []):
            triggers = {t.lower() for t in rule.get("if_enemy", [])}
            if names & triggers:
                for it in rule.get("suggest", []):
                    if it not in out:
                        out.append(it)

        # cheap filter: don't suggest items way above current gold pool
        prices = self.items.get("prices", {})
        affordable = [i for i in out if prices.get(i, 0) <= gold + 3000]
        return affordable[:top] if affordable else out[:top]
