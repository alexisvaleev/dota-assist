"""Entry point: wires GSI server + draft watcher + overlay together.

Modes switch automatically on GSI game_state:
  draft phases  -> draft_watcher active, overlay shows pick suggestions
  in game       -> watcher idle, overlay shows item recommendations
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from gsi_server import start_gsi_thread          # noqa: E402
from draft_watcher import DraftWatcher           # noqa: E402
from recommender import Recommender              # noqa: E402
from overlay import run_overlay                  # noqa: E402

try:
    import keyboard  # global hotkeys (Windows)
except ImportError:
    keyboard = None


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    rec = Recommender(my_bracket=cfg.get("mmr_bracket"))

    app, ov = run_overlay(cfg)
    gsi = start_gsi_thread(cfg["gsi_port"], cfg["gsi_auth_token"])

    def display_name(hid_or_short):
        hid = hid_or_short if isinstance(hid_or_short, int) \
            else rec.hero_id(hid_or_short)
        h = rec.heroes.get(str(hid)) if hid else None
        return h["localized_name"] if h else str(hid_or_short)

    manual_role = [None]     # set via overlay position buttons
    manual_side = [None]     # set via overlay side button

    def on_picks(st: dict):
        enemy_ids = [rec.hero_id(n) for n in st["enemy_picks"]]
        enemy_ids = [i for i in enemy_ids if i]
        ally_ids = [rec.hero_id(n) for n in st["ally_picks"]]
        ally_ids = [i for i in ally_ids if i]
        top = rec.recommend_picks(
            enemy_ids=enemy_ids, ally_ids=ally_ids, banned_ids=[],
            my_role=manual_role[0] or st.get("my_role"),
            enemy_roles=st.get("enemy_roles", []),
        )
        ov.bus.draft_update.emit({
            "enemy_picks": st["enemy_picks"],
            "unknown_slots": st.get("unknown_slots", []),
            "top3": [
                (
                    rec.heroes[str(cid)]["name"].replace("npc_dota_hero_", ""),
                    display_name(cid), score, why,
                )
                for cid, score, why in top
            ],
        })

    watcher = DraftWatcher(on_change=on_picks,
                           interval_ms=cfg.get("capture_interval_ms", 500))
    watcher.start()

    last_draft = {"enemy_ids": [], "ally_ids": []}
    _orig_on_picks = on_picks

    def on_picks(st: dict):  # noqa: F811 — wrap to persist draft results
        last_state[0] = st
        _orig_on_picks(st)
        last_draft["enemy_ids"] = [
            rec.hero_id(n) for n in st["enemy_picks"] if rec.hero_id(n)]
        last_draft["ally_ids"] = [
            rec.hero_id(n) for n in st["ally_picks"] if rec.hero_id(n)]

    watcher.on_change = on_picks
    last_items_key = [None]
    last_state = [None]

    def recompute():
        if last_state[0]:
            on_picks(last_state[0])

    ov.bus.side_changed.connect(
        lambda s: (manual_side.__setitem__(0, s),
                   watcher.set_side(s), recompute()))
    ov.bus.role_changed.connect(
        lambda r: (manual_role.__setitem__(0, r or None), recompute()))

    def on_gsi(st):
        # manual side override wins; otherwise follow GSI team_name
        side = manual_side[0] or st.team
        watcher.set_side(side)
        if st.team and manual_side[0] is None:
            ov.bus.side_detected.emit(st.team)
        watcher.enabled = st.in_draft

        # CM/lobby drafts come through GSI directly — feed the same pipeline
        if st.in_draft and st.draft:
            dp = st.draft_picks()
            if dp["enemy"] or dp["home"]:
                on_picks({
                    "enemy_picks": [
                        rec.heroes.get(str(i), {}).get("name", "")
                        .replace("npc_dota_hero_", "")
                        for i in dp["enemy"]
                    ],
                    "ally_picks": [
                        rec.heroes.get(str(i), {}).get("name", "")
                        .replace("npc_dota_hero_", "")
                        for i in dp["home"]
                    ],
                    "enemy_roles": [],
                    "my_role": None,
                    "unknown_slots": [],
                })
            return

        # in game -> item recommendations (recompute only on change)
        if not st.in_draft and st.my_hero_id:
            # spectator payloads carry all 10 heroes; own games don't —
            # reuse what the draft watcher captured on the pick screen.
            enemies = st.enemy_team_heroes() or last_draft["enemy_ids"]
            key = (st.my_hero_id, tuple(sorted(enemies)),
                   st.clock_time // 60)
            if key != last_items_key[0]:
                last_items_key[0] = key
                names = [
                    rec.heroes.get(str(i), {}).get("name", "")
                    .replace("npc_dota_hero_", "")
                    for i in enemies
                ]
                gold = (st.raw.get("player") or {}).get("gold", 0)
                items = rec.recommend_items(
                    st.my_hero_id, names,
                    gold=gold, clock_min=st.clock_time // 60)
                ov.bus.items_update.emit({
                    "hero": display_name(st.my_hero_id),
                    "enemies": names,
                    "items": items,
                })

    gsi.on_update(on_gsi)

    # global hotkey: Ctrl+Shift+D toggles click-through <-> interactive
    if keyboard:
        keyboard.add_hotkey(
            "ctrl+shift+d",
            lambda: ov.bus.toggle_interactive.emit())
        ov.bus.status.emit("Ctrl+Shift+D — режим кликов")
    else:
        ov.bus.status.emit("pip install keyboard — для хоткея")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
