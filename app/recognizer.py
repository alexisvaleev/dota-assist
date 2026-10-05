"""OpenCV template matching: crop -> best hero/role match.

Templates come from data/icons/<hero_name>/*.png — every arcana/persona
variant extracted from the VPK lives in the same folder, so any rendered
variant has a template.
"""
import json
from pathlib import Path

import cv2
import numpy as np

from paths import resource_dir, resource

ICONS = resource_dir("data/icons")

ROLE_NAMES = ["carry", "mid", "offlane", "soft_support", "hard_support"]


class Recognizer:
    def __init__(self):
        self.threshold = 0.82
        self.hero_templates: dict[str, list[tuple[Path, np.ndarray]]] = {}
        self.role_templates: dict[str, np.ndarray] = {}
        self._load()

    def _load(self):
        for hero_dir in ICONS.iterdir() if ICONS.exists() else []:
            if not hero_dir.is_dir() or hero_dir.name == "roles":
                continue
            tpls = []
            for f in hero_dir.glob("*.png"):
                img = cv2.imread(str(f))
                if img is not None:
                    tpls.append((f, img))
            if tpls:
                self.hero_templates[hero_dir.name] = tpls
        roles_dir = ICONS / "roles"
        if roles_dir.exists():
            for name in ROLE_NAMES:
                f = roles_dir / f"{name}.png"
                if f.exists():
                    img = cv2.imread(str(f))
                    if img is not None:
                        self.role_templates[name] = img

    @staticmethod
    def _match(crop: np.ndarray, tpl: np.ndarray) -> float:
        """Resize template to crop and score via normalized correlation."""
        if crop.size == 0 or tpl.size == 0:
            return 0.0
        t = cv2.resize(tpl, (crop.shape[1], crop.shape[0]))
        res = cv2.matchTemplate(crop, t, cv2.TM_CCOEFF_NORMED)
        return float(res.max())

    def hero(self, crop: np.ndarray) -> tuple[str | None, float]:
        best_name, best_score = None, 0.0
        for name, tpls in self.hero_templates.items():
            for _, tpl in tpls:
                s = self._match(crop, tpl)
                if s > best_score:
                    best_name, best_score = name, s
        if best_score >= self.threshold:
            return best_name, best_score
        return None, best_score

    def role(self, crop: np.ndarray) -> str | None:
        best_name, best_score = None, 0.0
        for name, tpl in self.role_templates.items():
            s = self._match(crop, tpl)
            if s > best_score:
                best_name, best_score = name, s
        return best_name if best_score >= 0.8 else None


def load_calibration() -> dict:
    p = resource("app/calibration.json")
    return json.loads(p.read_text(encoding="utf-8"))
