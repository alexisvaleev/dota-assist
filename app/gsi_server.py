"""GSI listener: receives game state POSTs from the Dota 2 client.

Exposes parsed snapshots via callbacks and a thread-safe `latest` property.
Works in a background thread; consumers read `latest` or subscribe via
`on_update`.
"""
import json
import threading
from typing import Callable, Optional

from flask import Flask, request

DRAFT_STATES = {
    "DOTA_GAMERULES_STATE_HERO_SELECTION",
    "DOTA_GAMERULES_STATE_STRATEGY_TIME",
    "DOTA_GAMERULES_STATE_TEAM_SHOWCASE",
}

# состояния, где драфта заведомо нет — CV можно не гонять
_NO_DRAFT_STATES = {
    "DOTA_GAMERULES_STATE_INIT",
    "DOTA_GAMERULES_STATE_WAIT_FOR_PLAYERS_TO_LOAD",
    "DOTA_GAMERULES_STATE_PRE_GAME",
    "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
    "DOTA_GAMERULES_STATE_POST_GAME",
    "DOTA_GAMERULES_STATE_DISCONNECT",
}


def draft_cv_needed(st: "GameState") -> bool:
    """True — CV-вотчер должен работать (fail-open).

    False только когда GSI доказал «драфта нет» либо когда он сам
    отдаёт пики (CM/лобби — там CV не нужен). GSI мёртв или молчит —
    функция не вызывается, watcher.enabled держит дефолт True: экран
    остаётся единственным источником драфта.
    """
    if st.draft.get("team2") or st.draft.get("team3"):
        return False
    if st.game_state in _NO_DRAFT_STATES:
        return False
    if not st.game_state and not st.my_hero_id and not st.team:
        return False            # главное меню — нечего распознавать
    return True


class GameState:
    """Parsed view over one GSI payload."""

    def __init__(self, raw: dict):
        self.raw = raw
        m = raw.get("map") or {}
        self.game_state = m.get("game_state", "")
        self.match_id = m.get("matchid", 0)
        self.clock_time = m.get("clock_time", 0)

        p = raw.get("player") or {}
        # Your own team is your own info — always present, incl. draft phase.
        self.team = p.get("team_name", "")  # "radiant" | "dire" | ""

        self.draft = raw.get("draft") or {}
        self.hero = raw.get("hero") or {}
        self.items = raw.get("items") or {}

    @property
    def in_draft(self) -> bool:
        return self.game_state in DRAFT_STATES or bool(self.draft.get("pick"))

    @property
    def my_hero_id(self) -> int:
        return self.hero.get("id", 0) or 0

    def draft_picks(self) -> dict:
        """Return {'home': [...hero_ids], 'enemy': [...hero_ids], 'bans': {...}}
        populated only when GSI supplies draft data (CM/lobby/spectator)."""
        out = {"home": [], "enemy": [], "bans": {"home": [], "enemy": []}}
        for key in ("team2", "team3"):
            t = self.draft.get(key) or {}
            side = "home" if t.get("home_team") else "enemy"
            for i in range(5):
                hid = t.get(f"pick{i}_id", 0)
                if hid:
                    out[side].append(hid)
            for i in range(7):
                hid = t.get(f"ban{i}_id", 0)
                if hid:
                    out["bans"][side].append(hid)
        return out

    def enemy_team_heroes(self) -> list[int]:
        """Enemy hero ids — ONLY populated for spectator/lobby GSI payloads.
        In your own ranked games GSI exposes just your hero; for that case
        callers must reuse the picks the draft watcher already captured."""
        h = self.hero or {}
        mine_is_team3 = self.team == "dire"  # team2=radiant, team3=dire in GSI
        enemy_key = "team2" if mine_is_team3 else "team3"
        return [
            d["id"] for d in (h.get(enemy_key) or {}).values() if d.get("id")
        ]


class GsiServer:
    def __init__(self, port: int, auth_token: str):
        self.port = port
        self.auth_token = auth_token
        self._state = GameState({})
        self._lock = threading.Lock()
        self._listeners: list[Callable[[GameState], None]] = []

        self.app = Flask("dota-assist-gsi")
        self.app.add_url_rule("/", view_func=self._handle, methods=["POST"])

    def _handle(self):
        data = request.get_json(force=True, silent=True) or {}
        tok = (data.get("auth") or {}).get("token")
        if tok != self.auth_token:
            return "bad token", 403
        st = GameState(data)
        with self._lock:
            self._state = st
        for cb in self._listeners:
            try:
                cb(st)
            except Exception:
                pass
        return "ok", 200

    @property
    def latest(self) -> GameState:
        with self._lock:
            return self._state

    def on_update(self, cb: Callable[[GameState], None]):
        self._listeners.append(cb)

    def run(self):
        # Quiet flask logging
        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        try:
            self.app.run(host="127.0.0.1", port=self.port, threaded=True)
        except OSError as e:
            # порт занят вторым экземпляром — живём без GSI (CV работает)
            print(f"[gsi] порт {self.port}: {e} — GSI отключён")


def start_gsi_thread(port: int, token: str) -> GsiServer:
    srv = GsiServer(port, token)
    t = threading.Thread(target=srv.run, daemon=True, name="gsi")
    t.start()
    return srv
