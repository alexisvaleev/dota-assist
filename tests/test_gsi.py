"""Парсинг GSI-пакетов + endpoint. Реалистичные payload'ы inline."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from gsi_server import GameState, GsiServer, draft_cv_needed  # noqa: E402


RANKED_DRAFT = {
    "provider": {"name": "Dota 2", "appid": 570},
    "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
            "matchid": "0", "clock_time": 0, "name": "start"},
    "player": {"steamid": "7656", "name": "me", "team_name": "radiant"},
    "auth": {"token": "t"},
}

CM_DRAFT = {
    "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
    "player": {"team_name": "radiant"},
    "draft": {
        "team2": {"home_team": True, "pick0_id": 1, "pick1_id": 2,
                  "ban0_id": 10},
        "team3": {"home_team": False, "pick0_id": 5, "pick1_id": 6,
                  "pick2_id": 7, "ban0_id": 11},
    },
    "auth": {"token": "t"},
}

IN_GAME = {
    "map": {"game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 1250},
    "player": {"team_name": "radiant", "gold": 3200},
    "hero": {"id": 1, "team2": {"0": {"id": 1}, "1": {"id": 2}},
             "team3": {"0": {"id": 5}, "1": {"id": 6}}},
    "items": {"slot0": {"name": "item_tango"},
              "slot1": {"name": "item_power_treads"}},
    "auth": {"token": "t"},
}


class Parse(unittest.TestCase):
    def test_ranked_draft(self):
        st = GameState(RANKED_DRAFT)
        self.assertTrue(st.in_draft)
        self.assertEqual(st.team, "radiant")
        self.assertEqual(st.my_hero_id, 0)        # герой ещё не выбран

    def test_cm_draft_picks_and_bans(self):
        st = GameState(CM_DRAFT)
        dp = st.draft_picks()
        self.assertEqual(dp["home"], [1, 2])
        self.assertEqual(dp["enemy"], [5, 6, 7])
        self.assertEqual(dp["bans"]["enemy"], [11])
        self.assertEqual(dp["bans"]["home"], [10])

    def test_enemy_heroes_spectator_shape(self):
        st = GameState(IN_GAME)
        self.assertFalse(st.in_draft)
        self.assertEqual(sorted(st.enemy_team_heroes()), [5, 6])

    def test_clock_and_gold(self):
        st = GameState(IN_GAME)
        self.assertEqual(st.clock_time, 1250)
        self.assertEqual(st.raw["player"]["gold"], 3200)


class CvGate(unittest.TestCase):
    """draft_cv_needed: CV гоняем, пока GSI не доказал «драфта нет»."""

    def test_ranked_draft_needs_cv(self):
        self.assertTrue(draft_cv_needed(GameState(RANKED_DRAFT)))

    def test_gsi_supplied_draft_disables_cv(self):
        self.assertFalse(draft_cv_needed(GameState(CM_DRAFT)))

    def test_in_game_off(self):
        self.assertFalse(draft_cv_needed(GameState(IN_GAME)))

    def test_menu_off(self):
        # пустой payload: ни state, ни героя, ни команды — меню
        self.assertFalse(draft_cv_needed(GameState({})))

    def test_postgame_off(self):
        st = GameState({"map": {"game_state":
                                "DOTA_GAMERULES_STATE_POST_GAME"}})
        self.assertFalse(draft_cv_needed(st))

    def test_unknown_state_fail_open(self):
        # неизвестное состояние — лучше лишний раз снять экран,
        # чем промолчать на реальном драфте
        st = GameState({"map": {"game_state": "DOTA_GAMERULES_STATE_FUTURE"},
                        "player": {"team_name": "dire"}})
        self.assertTrue(draft_cv_needed(st))


class Endpoint(unittest.TestCase):
    def test_post_ok_and_bad_token(self):
        srv = GsiServer(port=0, auth_token="t")
        c = srv.app.test_client()
        r = c.post("/", json=RANKED_DRAFT)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(srv.latest.in_draft)

        r = c.post("/", json={"auth": {"token": "wrong"}})
        self.assertEqual(r.status_code, 403)

    def test_listener_called(self):
        srv = GsiServer(port=0, auth_token="t")
        got = []
        srv.on_update(lambda st: got.append(st.game_state))
        srv.app.test_client().post("/", json=IN_GAME)
        self.assertEqual(got, ["DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"])


if __name__ == "__main__":
    unittest.main()
