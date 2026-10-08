"""Анализ состава: какие командные функции не закрыты пиками союзников.

По ролям OpenDota (heroes.json -> roles). Функция считается закрытой,
если хотя бы один союзник (или кандидат) имеет нужную роль.
Союзников нет — пробелов нет: рано говорить о составе.

Nuker используем как честный прокси маг. урона: attack_type героя
(Melee/Ranged) к типу урона отношения не имеет, а в данных OpenDota
урона по типам нет.
"""
from __future__ import annotations

from .dataload import GameData

# тег -> (роль OpenDota, текст предупреждения); порядок = порядок вывода
FUNCTIONS: dict[str, tuple[str, str]] = {
    "init":    ("Initiator", "нет инициации"),
    "control": ("Disabler",  "нет контроля"),
    "front":   ("Durable",   "нет фронтлайна"),
    "support": ("Support",   "нет саппорта"),
    "nuke":    ("Nuker",     "нет маг. урона (ни одного Nuker)"),
}


def hero_tags(gd: GameData, hid: int) -> set[str]:
    """Какие функции закрывает герой."""
    roles = set(gd.roles.get(hid) or ())
    return {t for t, (role, _) in FUNCTIONS.items() if role in roles}


def needs(ally_ids: list[int], gd: GameData) -> set[str]:
    """Теги функций, не закрытые текущими пиками союзников."""
    if not ally_ids:
        return set()
    covered: set[str] = set()
    for hid in ally_ids:
        covered |= hero_tags(gd, hid)
    return set(FUNCTIONS) - covered


def team_gaps(ally_ids: list[int], gd: GameData) -> list[str]:
    """Предупреждения для оверлея, в порядке FUNCTIONS."""
    miss = needs(ally_ids, gd)
    return [w for t, (_, w) in FUNCTIONS.items() if t in miss]
