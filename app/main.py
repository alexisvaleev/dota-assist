"""Точка входа: GSI + CV watcher + оверлей.

Потоки данных:
  draft: CV watcher (или GSI draft в CM/лобби) -> DraftState -> engine
         -> оверлей (топ пиков с разбивкой «почему»)
  game:  GSI -> hero/инвентарь/золото/время + сохранённые пики драфта
         -> engine -> оверлей (предметы)
"""
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtCore import QTimer                    # noqa: E402
from PyQt6.QtWidgets import QApplication           # noqa: E402
from gsi_server import start_gsi_thread            # noqa: E402
from draft_watcher import DraftWatcher             # noqa: E402
from overlay import run_overlay                    # noqa: E402
from paths import layered_file, layered_dir, user_dir, config_file  # noqa: E402
from engine import load_data, DraftState, recommend_picks, recommend_items  # noqa: E402
from engine import team_gaps                                               # noqa: E402
from bootstrap import bootstrap_async              # noqa: E402
import updater                                     # noqa: E402
from version import current as app_version         # noqa: E402

try:
    import keyboard  # глобальные хоткеи (Windows)
except ImportError:
    keyboard = None


def load_config() -> dict:
    p = config_file()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[config] {p}: {e} — беру дефолт")
    ex = layered_file("config.example.json")
    if ex.exists():
        cfg = json.loads(ex.read_text(encoding="utf-8"))
        if str(p).startswith(str(user_dir())):
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                         encoding="utf-8")
            print(f"[config] создан {p} — впиши stratz_token при желании")
        return cfg
    return {"gsi_port": 3000, "gsi_auth_token": ""}


class Coordinator:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.reload_data()
        self.manual_pos: int | None = None   # 1..5 с кнопок
        self.manual_side: str | None = None
        self.last_draft_ids = {"enemy": [], "ally": []}
        self.last_draft_state: dict | None = None
        self._items_key = None
        self._update_info: dict | None = None

    def reload_data(self):
        self.gd = load_data(data_dir=layered_dir("data"),
                            user_dir=user_dir() / "data")
        self.name2id = {
            v.get("name", "").replace("npc_dota_hero_", ""): hid
            for hid, v in self.gd.heroes.items()
        }

    # ---------- helpers ----------

    def hid(self, short: str) -> int | None:
        return self.name2id.get(short)

    def hero_disp(self, hid: int) -> str:
        return self.gd.hero_name(hid)

    def icon_dir(self, hid: int) -> str:
        return self.gd.short_name(hid)

    # ---------- draft ----------

    def on_draft(self, st: dict):
        """st: снимок от watcher'а (имена) или от GSI draft (id через
        draft_picks — уже конвертированы в имена перед вызовом)."""
        self.last_draft_state = st
        enemy_ids = [i for i in (self.hid(n) for n in st["enemy_picks"]) if i]
        ally_ids = [i for i in (self.hid(n) for n in st["ally_picks"]) if i]
        banned = [i for i in (self.hid(n) for n in st.get("bans", [])) if i]
        self.last_draft_ids = {"enemy": enemy_ids, "ally": ally_ids}

        ds = DraftState(
            ally_ids=ally_ids, enemy_ids=enemy_ids, banned_ids=banned,
            my_pos=self.manual_pos,
            unknown_slots=st.get("unknown_slots", 0),
            confidence=st.get("confidence", 1.0),
            source=st.get("source", "cv"),
        )
        recs = recommend_picks(ds, self.gd,
                               bracket=self.cfg.get("mmr_bracket"))
        self.ov.bus.draft_update.emit({
            "phase": ds.phase_label,
            "reliable": ds.reliable,
            "enemy_picks": st["enemy_picks"],
            "ally_picks": st["ally_picks"],
            "bans": st.get("bans", []),
            "unknown_slots": ds.unknown_slots,
            "confidence": ds.confidence,
            "calib": st.get("calib", ""),
            "warnings": team_gaps(ally_ids, self.gd),
            "top": [
                (self.icon_dir(r.hero_id), self.hero_disp(r.hero_id),
                 r.score, r.why())
                for r in recs
            ],
        })

    def recompute_draft(self):
        if self.last_draft_state:
            self.on_draft(self.last_draft_state)

    # ---------- GSI ----------

    def on_gsi(self, st):
        side = self.manual_side or st.team
        if side:
            self.watcher.set_side(side)
        if st.team and not self.manual_side:
            self.ov.bus.side_detected.emit(st.team)

        gsi_draft = bool(st.draft.get("team2") or st.draft.get("team3"))
        self.watcher.enabled = st.in_draft and not gsi_draft

        if st.in_draft:
            if gsi_draft:
                # CM/лобби: пики и баны приходят в GSI — CV не нужен
                dp = st.draft_picks()
                short = lambda i: self.gd.short_name(i)  # noqa: E731
                self.on_draft({
                    "enemy_picks": [short(i) for i in dp["enemy"]],
                    "ally_picks": [short(i) for i in dp["home"]],
                    "bans": [short(i) for i in
                             dp["bans"]["enemy"] + dp["bans"]["home"]],
                    "unknown_slots": 0, "confidence": 1.0, "source": "gsi",
                })
            return

        # в игре -> предметы
        if st.my_hero_id:
            enemies = st.enemy_team_heroes() or self.last_draft_ids["enemy"]
            owned = {
                (v or {}).get("name", "").replace("item_", "")
                for v in (st.items or {}).values() if isinstance(v, dict)
            }
            owned.discard("")
            gold = int((st.raw.get("player") or {}).get("gold", 0))
            key = (st.my_hero_id, tuple(sorted(enemies)),
                   tuple(sorted(owned)), st.clock_time // 30)
            if key == self._items_key:
                return
            self._items_key = key
            enemy_names = [self.gd.short_name(i) for i in enemies]
            items = recommend_items(
                st.my_hero_id, enemy_names, owned, gold,
                max(st.clock_time, 0), self.gd)
            self.ov.bus.items_update.emit({
                "hero": self.hero_disp(st.my_hero_id),
                "enemies": [self.hero_disp(i) for i in enemies],
                "items": items,
            })

    # ---------- run ----------

    def run(self):
        app, self.ov = run_overlay(self.cfg)
        self.watcher = DraftWatcher(
            on_change=self.ov.bus.draft_raw.emit,
            interval_ms=self.cfg.get("capture_interval_ms", 500))
        self.watcher.start()
        gsi = start_gsi_thread(self.cfg["gsi_port"],
                               self.cfg["gsi_auth_token"])
        gsi.on_update(self.ov.bus.gsi_raw.emit)

        # всё, что меняет состояние, исполняется в GUI-потоке через
        # queued-сигналы: CV/Flask потоки только эмитят, не мутируют
        self.ov.bus.draft_raw.connect(self.on_draft)
        self.ov.bus.gsi_raw.connect(self.on_gsi)
        self.ov.bus.quit_app.connect(app.quit)
        self.ov.bus.side_changed.connect(self._side_changed)
        self.ov.bus.pos_changed.connect(self._pos_changed)
        self.ov.bus.calibrate.connect(
            lambda: setattr(self.watcher, "force_calib", True))
        self.ov.bus.update_requested.connect(self._apply_update)

        if keyboard:
            keyboard.add_hotkey(
                "ctrl+shift+d",
                lambda: self.ov.bus.toggle_interactive.emit())
            self.ov.bus.status.emit("Ctrl+Shift+D — режим кликов")
        else:
            self.ov.bus.status.emit("pip install keyboard — для хоткея")

        if self.gd.warnings:
            self.ov.bus.status.emit(
                f"данные: {len(self.gd.warnings)} предупреждений "
                "(см. консоль)")
            for w in self.gd.warnings:
                print(f"[data] {w}")

        # plug&play: при пустом/протухшем кэше скачиваем данные и иконки
        bootstrap_async(
            status_cb=lambda m: self.ov.bus.status.emit(m),
            on_done=self._data_ready)

        # автообновление: раз в запуск смотрим свежий релиз на GitHub
        print(f"[version] {app_version()}")
        updater.check_async(self._update_found)

        sys.exit(app.exec())

    def _data_ready(self):
        """bootstrap закончил: перечитать данные и шаблоны иконок."""
        self.reload_data()
        self.watcher.rec.reload()
        self.recompute_draft()

    def _apply_update(self):
        if not self._update_info:
            return

        def work():
            # dict целиком: внутри url/size/checksums_url для верификации
            if updater.apply_update(
                    self._update_info,
                    lambda m: self.ov.bus.status.emit(m)):
                self.watcher.stop()
                # выход в GUI-потоке: из worker-треда QTimer не сработает
                self.ov.bus.quit_app.emit()

        threading.Thread(target=work, daemon=True).start()

    def _update_found(self, info: dict | None):
        if info:
            self._update_info = info
            self.ov.bus.update_found.emit(info)

    def _side_changed(self, s: str):
        self.manual_side = s
        self.watcher.set_side(s)
        self.recompute_draft()

    def _pos_changed(self, pos: str):
        self.manual_pos = int(pos) if pos else None
        self.recompute_draft()


def main():
    Coordinator(load_config()).run()


if __name__ == "__main__":
    main()
