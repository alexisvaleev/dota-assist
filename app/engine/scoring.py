"""Скоринг кандидатов на пик.

score = w_meta·(wr_base−50)
      + Σ_enemy w_lane·adv(cand, e)
      + w_syn·Σ_ally syn(cand, a)
      + w_pool·pool_bonus(cand)
      + min(w_comp·|закрытые_пробелы|, comp_cap)

adv = (wr(cand vs e) − wr_base(cand)) · n/(n+K)   — сжатие по числу игр:
4 победы в 4 играх ≠ +50, а почти ноль.
w_lane > 1 если враг вероятно стоит против меня в линии (по positions.json).
"""
from __future__ import annotations

from .composition import hero_tags, needs
from .dataload import GameData
from .models import DraftState, Recommendation, LANE_OPPONENTS

SHRINK_K = 200.0        # игр для полного доверия к матчапу
LANE_W = 1.6            # вес матчапа с вероятным лайн-оппонентом
META_W = 1.0
SYN_W = 0.6
POOL_W = 0.5            # макс. бонус за личный пул (в очках)
POOL_GAMES_FULL = 25    # сколько игр на герое = полное доверие
MIN_POS_SHARE = 0.08    # герой играет мою позицию реже 8% -> не кандидат
COMP_W = 0.8            # бонус за каждую закрытую функцию команды
COMP_CAP = 1.5          # макс. бонус за состав (в очках)


def base_wr(gd: GameData, hid: int, bracket: int | None = None) -> float:
    m = gd.meta.get(hid)
    if not m:
        return 50.0
    if bracket and m["wr_bracket"].get(bracket):
        return m["wr_bracket"][bracket]
    return m["wr_all"] or 50.0


def pos_share(gd: GameData, hid: int, pos: int) -> float:
    """Доля игр героя на позиции pos; нет данных -> 1.0 (не фильтруем)."""
    p = gd.positions.get(hid)
    return p.get(pos, 0.0) if p else 1.0


def has_pos_data(gd: GameData) -> bool:
    return bool(gd.positions)


def _adv(gd: GameData, cid: int, eid: int, base_c: float) -> float:
    row = gd.matchups.get(cid, {}).get(eid)
    if not row or not row["games"]:
        return 0.0
    return (row["wr"] - base_c) * row["games"] / (row["games"] + SHRINK_K)


def _syn(gd: GameData, cid: int, aid: int, base_c: float) -> float:
    row = gd.synergies.get(cid, {}).get(aid)
    if not row or not row["games"]:
        return 0.0
    return (row["wr"] - base_c) * row["games"] / (row["games"] + SHRINK_K)


def _lane_weight(gd: GameData, eid: int, my_pos: int | None) -> float:
    """Насколько враг eid вероятно окажется против моей позиции."""
    if not my_pos or not gd.positions.get(eid):
        return 1.0
    p = gd.positions[eid]
    share = sum(p.get(x, 0.0) for x in LANE_OPPONENTS[my_pos])
    return 1.0 + (LANE_W - 1.0) * min(share, 1.0)


def _pool_bonus(gd: GameData, cid: int, base_c: float) -> float:
    pr = gd.profile.get(cid)
    if not pr or not pr["games"]:
        return 0.0
    conf = min(pr["games"] / POOL_GAMES_FULL, 1.0)
    return conf * max(-8.0, min(8.0, pr["wr"] - base_c))


def recommend_picks(
    st: DraftState,
    gd: GameData,
    bracket: int | None = None,
    top: int = 5,
) -> list[Recommendation]:
    taken = set(st.enemy_ids) | set(st.ally_ids) | set(st.banned_ids)
    filter_pos = bool(st.my_pos) and has_pos_data(gd)
    need = needs(st.ally_ids, gd)

    out: list[Recommendation] = []
    for cid in gd.heroes:
        if cid in taken:
            continue
        if filter_pos and pos_share(gd, cid, st.my_pos) < MIN_POS_SHARE:
            continue

        b_c = base_wr(gd, cid, bracket)
        meta = META_W * (b_c - 50.0)

        vs = sum(_lane_weight(gd, e, st.my_pos) * _adv(gd, cid, e, b_c)
                 for e in st.enemy_ids)
        syn = SYN_W * sum(_syn(gd, cid, a, b_c) for a in st.ally_ids)
        pool = POOL_W * _pool_bonus(gd, cid, b_c)
        comp = min(COMP_W * len(need & hero_tags(gd, cid)), COMP_CAP)

        out.append(Recommendation(
            hero_id=cid,
            score=meta + vs + syn + pool + comp,
            breakdown={"meta": meta, "vs": vs, "with": syn,
                       "pool": pool, "comp": comp},
        ))

    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top]
