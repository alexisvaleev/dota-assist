"""Загрузка и валидация data/*.json → GameData.

Формат файлов: {"_meta": {source, fetched_at, patch}, "data": {...}}.
Старый плоский формат (без обёртки) тоже принимается.
Невалидный файл → пустая секция + запись в .warnings — приложение не падает.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


def _num(v) -> float:
    """OpenDota отдаёт games/wins/time строками — приводим."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _unwrap(raw) -> tuple[dict, dict]:
    """Возвращает (data, meta). Плоский файл = data без метаданных."""
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"] or {}, raw.get("_meta") or {}
    return raw if isinstance(raw, dict) else {}, {}


@dataclass
class GameData:
    heroes: dict[int, dict] = field(default_factory=dict)
    # roles[hid] = ["Carry", ...], attack_type[hid] = "Melee" | "Ranged"
    roles: dict[int, list[str]] = field(default_factory=dict)
    attack_type: dict[int, str] = field(default_factory=dict)
    meta: dict[int, dict] = field(default_factory=dict)
    # matchups[a][b] = {games:int, wins:int, wr:float} — wr побед a против b
    matchups: dict[int, dict[int, dict]] = field(default_factory=dict)
    synergies: dict[int, dict[int, dict]] = field(default_factory=dict)
    # positions[hero][pos 1..5] = доля игр на позиции (0..1)
    positions: dict[int, dict[int, float]] = field(default_factory=dict)
    # builds[hero] = [{item, time_s, min, games, wr}]
    builds: dict[int, list[dict]] = field(default_factory=dict)
    item_rules: list[dict] = field(default_factory=list)
    item_prices: dict[str, int] = field(default_factory=dict)
    profile: dict[int, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def hero_name(self, hid: int) -> str:
        h = self.heroes.get(hid) or {}
        return h.get("localized_name") or h.get("name", str(hid))

    def short_name(self, hid: int) -> str:
        h = self.heroes.get(hid) or {}
        return h.get("name", "").replace("npc_dota_hero_", "")


def _load_json(path: Path, warnings: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        warnings.append(f"{path.name}: {e}")
        return {}


def _pairs(raw: dict, warnings: list[str], fname: str) -> dict[int, dict[int, dict]]:
    """matchups/synergies: str-id ключи -> int, games/wins -> int."""
    out: dict[int, dict[int, dict]] = {}
    for a, row in (raw or {}).items():
        try:
            a_i = int(a)
        except (TypeError, ValueError):
            warnings.append(f"{fname}: плохой ключ {a!r}")
            continue
        inner = {}
        for b, v in (row or {}).items():
            try:
                b_i = int(b)
                games = int(_num(v.get("games")))
                wins = int(_num(v.get("wins")))
            except (TypeError, ValueError, AttributeError):
                warnings.append(f"{fname}: плохая запись {a}->{b}")
                continue
            wr = v.get("wr")
            inner[b_i] = {
                "games": games,
                "wins": wins,
                "wr": float(_num(wr)) if wr is not None
                else round(wins / games * 100, 2) if games else 50.0,
            }
        if inner:
            out[a_i] = inner
    return out


def load_data(data_dir: Path, user_dir: Path | None = None) -> GameData:
    """Читает файлы из data_dir; user_dir (appdata) имеет приоритет —
    туда fetch_data кладёт свежие загрузки."""
    warnings: list[str] = []

    def pick(name: str) -> dict:
        for d in ([user_dir, data_dir] if user_dir else [data_dir]):
            if d is None:
                continue
            p = d / name
            if p.exists():
                raw = _load_json(p, warnings)
                if raw:
                    return raw
        return {}

    gd = GameData(warnings=warnings)

    for k, v in _unwrap(pick("heroes.json"))[0].items():
        try:
            hid = int(k)
        except (TypeError, ValueError):
            warnings.append(f"heroes.json: плохой id {k!r}")
            continue
        gd.heroes[hid] = v
        if isinstance(v, dict):
            gd.roles[hid] = [str(r) for r in v.get("roles") or []]
            if v.get("attack_type"):
                gd.attack_type[hid] = str(v["attack_type"])

    for k, v in _unwrap(pick("meta.json"))[0].items():
        try:
            hid = int(k)
            gd.meta[hid] = {
                "wr_all": _num(v.get("wr_all") or v.get("winrate_all")),
                "wr_bracket": {int(b): _num(w) for b, w in
                               (v.get("wr_bracket")
                                or v.get("winrate_by_bracket") or {}).items()},
                "picks": int(_num(v.get("picks") or v.get("pick_count"))),
            }
        except (TypeError, ValueError, AttributeError):
            warnings.append(f"meta.json: плохая запись {k!r}")

    gd.matchups = _pairs(_unwrap(pick("matchups.json"))[0], warnings,
                         "matchups.json")
    gd.synergies = _pairs(_unwrap(pick("synergies.json"))[0], warnings,
                          "synergies.json")

    for k, v in _unwrap(pick("positions.json"))[0].items():
        try:
            gd.positions[int(k)] = {int(p): _num(s) for p, s in v.items()}
        except (TypeError, ValueError, AttributeError):
            warnings.append(f"positions.json: плохая запись {k!r}")

    for k, rows in _unwrap(pick("builds.json"))[0].items():
        try:
            hid = int(k)
        except (TypeError, ValueError):
            warnings.append(f"builds.json: плохой id {k!r}")
            continue
        items = []
        for r in rows or []:
            try:
                # OpenDota itemTimings.time — секунды (450, 720…)
                t_s = int(_num(r.get("time_s") or r.get("time")))
                items.append({
                    "item": str(r["item"]),
                    "time_s": t_s,
                    "min": round(t_s / 60, 1),
                    "games": int(_num(r.get("games"))),
                    "wr": _num(r.get("wr")),
                })
            except (TypeError, ValueError, KeyError):
                warnings.append(f"builds.json: плохая запись у {k}")
        if items:
            gd.builds[hid] = sorted(items, key=lambda x: (x["time_s"],
                                                        -x["games"]))

    it = pick("items.json")
    gd.item_rules = it.get("rules", []) if isinstance(it, dict) else []
    gd.item_prices = {k: int(_num(v)) for k, v in
                      (it.get("prices", {}) if isinstance(it, dict)
                       else {}).items()}

    for k, v in _unwrap(pick("profile.json"))[0].items():
        try:
            gd.profile[int(k)] = {
                "games": int(_num(v.get("games"))),
                "wr": _num(v.get("wr")),
            }
        except (TypeError, ValueError, AttributeError):
            warnings.append(f"profile.json: плохая запись {k!r}")

    return gd


def meta_info(data_dir: Path, user_dir: Path | None = None) -> dict:
    """Когда обновлялись данные — для статуса в оверлее."""
    for d in ([user_dir, data_dir] if user_dir else [data_dir]):
        p = (d or Path()) / "meta.json"
        if p and p.exists():
            try:
                _, m = _unwrap(json.loads(p.read_text(encoding="utf-8")))
                return m
            except Exception:
                pass
    return {}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
