"""Рекомендации предметов в игре.

Источники:
  builds.json — itemTimings OpenDota: {item, time_s, min, games, wr}.
    Берём предметы, типичное время покупки которых в окне
    [сейчас−5мин, сейчас+10мин]; если окно пусто — топ по популярности.
  items.json — ручные ситуативные правила (if_enemy -> suggest) и цены.

Уже купленное (инвентарь из GSI) исключается. Дорогое помечается,
а не выкидывается — но не предлагаем то, что не накопить в принципе.
"""
from __future__ import annotations

from .dataload import GameData

WINDOW_BACK_S = 300      # предметы, которые "уже пора"
WINDOW_AHEAD_S = 600     # и что собирать дальше
GOLD_HEADROOM = 2500     # "по карману" = цена <= gold + headroom


def recommend_items(
    hero_id: int,
    enemy_names: list[str],
    owned: set[str],
    gold: int,
    clock_s: int,
    gd: GameData,
    top: int = 5,
) -> list[dict]:
    """-> [{item, reason, affordable, need_gold}]"""
    core = gd.builds.get(hero_id, [])
    owned_l = {o.lower() for o in owned}

    def fresh(name: str) -> bool:
        return name.lower() not in owned_l

    timed = [r for r in core
             if clock_s - WINDOW_BACK_S <= r["time_s"] <= clock_s + WINDOW_AHEAD_S
             and fresh(r["item"])]
    timed.sort(key=lambda r: -r["games"])
    rows = [{"item": r["item"], "reason": f"~{r['min']:.0f} мин",
             "games": r["games"]} for r in timed]

    if not rows:
        popular = [r for r in sorted(core, key=lambda x: -x["games"])
                   if fresh(r["item"])]
        rows = [{"item": r["item"], "reason": "популярно",
                 "games": r["games"]} for r in popular[:top]]

    # ситуативные правила
    names = {n.lower() for n in enemy_names}
    for rule in gd.item_rules:
        triggers = {t.lower() for t in rule.get("if_enemy", [])}
        if names & triggers:
            for it in rule.get("suggest", []):
                if fresh(it) and all(r["item"] != it for r in rows):
                    rows.append({"item": it,
                                 "reason": f"против {rule['if_enemy'][0]}",
                                 "games": 0})

    # помечаем доступность по золоту
    out = []
    for r in rows[: top * 2]:
        price = gd.item_prices.get(r["item"], 0)
        out.append({
            "item": r["item"],
            "reason": r["reason"],
            "affordable": price == 0 or price <= gold + GOLD_HEADROOM,
            "need_gold": max(0, price - gold) if price else 0,
        })
    # недоступные — в конец, чтобы не вытесняли то, что можно купить
    out.sort(key=lambda r: (not r["affordable"]))
    return out[:top]
