"""Screen-capture loop during the draft: reads calibrated slot regions,
recognizes hero portraits + role icons, emits a state diff event.

Side mapping: GSI player.team_name decides which calibrated column is
'enemy'. Radiant = left column by default; flips via config/hotkey.
"""
import threading
import time
from typing import Callable

import mss
import numpy as np

from recognizer import Recognizer, load_calibration


def _crop(mon_img: np.ndarray, box: list[int]) -> np.ndarray:
    x, y, w, h = box
    return mon_img[y:y + h, x:x + w]


class DraftWatcher(threading.Thread):
    def __init__(self, on_change: Callable[[dict], None], interval_ms: int = 500):
        super().__init__(daemon=True, name="draft-watcher")
        self.on_change = on_change
        self.interval = interval_ms / 1000
        self.rec = Recognizer()
        self.cal = load_calibration()
        self.rec.threshold = self.cal.get("match_threshold", 0.82)

        self.enabled = False
        self.my_side = "radiant"        # set from GSI each tick
        self.state = {                  # what we last reported
            "enemy_picks": [], "ally_picks": [],
            "enemy_roles": [], "my_role": None,
            "unknown_slots": [],
        }
        # anti-flicker: a hero must win 2 of last 3 frames to count
        self._history: dict[tuple[str, int], list[str | None]] = {}
        self._stop_flag = threading.Event()

    def _stable(self, key: tuple[str, int], hero: str | None) -> str | None:
        h = self._history.setdefault(key, [])
        h.append(hero)
        del h[:-3]
        votes = [v for v in h if v]
        if len(votes) >= 2 and votes.count(votes[0]) < len(votes):
            # different heroes tied -> treat as uncertain
            top = max(set(votes), key=votes.count)
            return top if votes.count(top) >= 2 else None
        return votes[0] if len(votes) >= 2 else None

    def set_side(self, team_name: str):
        if team_name in ("radiant", "dire"):
            self.my_side = team_name

    def _read_side(self, img, side_key: str):
        """Return (hero_names, roles, unknown_idx list) for one column."""
        heroes, roles, unknown = [], [], []
        for i, slot in enumerate(self.cal[side_key]["slots"]):
            pc = _crop(img, slot["portrait"])
            hero, score = self.rec.hero(pc)
            hero = self._stable((side_key, i), hero)
            if hero:
                heroes.append(hero)
            elif pc.std() > 8:  # something drawn but unrecognized
                heroes.append(None)
                unknown.append(i)
            else:
                heroes.append(None)
            rc = _crop(img, slot["role"])
            roles.append(self.rec.role(rc))
        return heroes, roles, unknown

    def _tick(self, sct):
        img = np.asarray(sct.grab(sct.monitors[0]))[:, :, :3]  # BGR, no alpha
        # Radiant renders left; flip via calibration if a mode inverts it.
        radiant_key = "team_right" if self.cal.get("radiant_on_right") \
            else "team_left"
        dire_key = "team_left" if radiant_key == "team_right" else "team_right"
        enemy_key = radiant_key if self.my_side == "dire" else dire_key
        ally_key = dire_key if self.my_side == "dire" else radiant_key

        e_heroes, e_roles, e_unk = self._read_side(img, enemy_key)
        a_heroes, a_roles, _ = self._read_side(img, ally_key)

        my_role = next((r for r in a_roles if r), None)

        # keep pick<->role alignment: drop empty slots as pairs
        enemy_pairs = [(h, r) for h, r in zip(e_heroes, e_roles) if h]

        new = {
            "enemy_picks": [h for h, _ in enemy_pairs],
            "ally_picks": [h for h in a_heroes if h],
            "enemy_roles": [r for _, r in enemy_pairs],
            "my_role": my_role,
            "unknown_slots": e_unk,
        }
        if new != self.state:
            self.state = new
            self.on_change(new)

    def run(self):
        with mss.mss() as sct:
            while not self._stop_flag.is_set():
                if self.enabled:
                    try:
                        self._tick(sct)
                    except Exception as e:
                        print(f"[draft_watcher] {e}")
                time.sleep(self.interval)

    def stop(self):
        self._stop_flag.set()
