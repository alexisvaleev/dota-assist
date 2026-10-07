"""Доменные типы. Все входы нормализуются сюда — GSI и CV отдают одно и то же."""
from __future__ import annotations

from dataclasses import dataclass, field

# в какой линии стоит противник: моя позиция -> позиции врагов напротив
LANE_OPPONENTS: dict[int, tuple[int, ...]] = {
    1: (3, 4),   # мой сейф vs их оффлейн + роумер
    2: (2,),
    3: (1, 5),   # мой оффлейн vs их керри + хардсап
    4: (1, 5),
    5: (3, 4),
}


@dataclass
class DraftState:
    """Единый снимок драфта. Источники: cv | gsi | manual (поле source)."""
    ally_ids: list[int] = field(default_factory=list)
    enemy_ids: list[int] = field(default_factory=list)
    banned_ids: list[int] = field(default_factory=list)
    my_pos: int | None = None          # 1..5, задаётся кнопками
    unknown_slots: int = 0             # слоты «что-то есть, но не распознано»
    confidence: float = 1.0            # худший match-score среди распознанных
    source: str = "cv"

    @property
    def phase(self) -> int:
        """Ranked AP: баны, потом раунды пиков 2-2-1, враги раскрываются
        после каждого раунда. Фаза = номер моего текущего выбора."""
        n = len(self.enemy_ids)
        if n == 0:
            return 1                   # до первого раскрытия
        if n <= 2:
            return 2                   # видно 1-2 врага
        return 3                       # видно 3-4 врага (5й откроется в конце)

    @property
    def phase_label(self) -> str:
        return {1: "Раунд 1 — мета", 2: "Раунд 2", 3: "Финальный пик"}[
            self.phase]

    @property
    def reliable(self) -> bool:
        """Можно ли доверять распознаванию настолько, чтобы показывать
        контрпики уверенно."""
        return self.unknown_slots == 0 and self.confidence >= 0.80


@dataclass
class Recommendation:
    hero_id: int
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    # breakdown: {"meta": .., "vs": .., "with": .., "pool": ..}

    def why(self) -> str:
        parts = []
        b = self.breakdown
        if b.get("vs"):
            parts.append(f"контр {b['vs']:+.1f}")
        if b.get("with"):
            parts.append(f"синергия {b['with']:+.1f}")
        if b.get("pool"):
            parts.append(f"твой пул {b['pool']:+.1f}")
        if not parts:
            return f"мета {b.get('meta', 0):+.1f}"
        return " · ".join(parts)
