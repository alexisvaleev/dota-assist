"""Тесты чистого ядра: dataload, scoring, items — без Qt/cv2/Flask."""
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from engine.dataload import load_data          # noqa: E402
from engine.models import DraftState            # noqa: E402
from engine.scoring import recommend_picks      # noqa: E402
from engine.items import recommend_items        # noqa: E402
from engine.composition import team_gaps        # noqa: E402


def write(d: Path, name: str, obj):
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def make_data(tmp: Path, **kw) -> Path:
    write(tmp, "heroes.json", {"data": kw.get("heroes", {
        "1": {"name": "npc_dota_hero_aa", "localized_name": "AA",
              "roles": ["Support"]},
        "2": {"name": "npc_dota_hero_bb", "localized_name": "BB",
              "roles": ["Carry"]},
        "3": {"name": "npc_dota_hero_cc", "localized_name": "CC",
              "roles": ["Carry"]},
        "4": {"name": "npc_dota_hero_dd", "localized_name": "DD",
              "roles": ["Support"]},
        "5": {"name": "npc_dota_hero_ee", "localized_name": "EE",
              "roles": ["Mid"]},
    })})
    write(tmp, "meta.json", {"data": kw.get("meta", {
        "1": {"wr_all": 50, "wr_bracket": {}, "picks": 100},
        "2": {"wr_all": 55, "wr_bracket": {}, "picks": 100},
        "3": {"wr_all": 48, "wr_bracket": {}, "picks": 100},
        "4": {"wr_all": 51, "wr_bracket": {}, "picks": 100},
        "5": {"wr_all": 52, "wr_bracket": {}, "picks": 100},
    })})
    write(tmp, "matchups.json", {"data": kw.get("matchups", {})})
    write(tmp, "synergies.json", {"data": kw.get("synergies", {})})
    write(tmp, "positions.json", {"data": kw.get("positions", {})})
    write(tmp, "builds.json", {"data": kw.get("builds", {})})
    write(tmp, "items.json", kw.get("items",
                                    {"rules": [], "prices": {}}))
    if "profile" in kw:
        write(tmp, "profile.json", {"data": kw["profile"]})
    return tmp


class DataLoad(unittest.TestCase):
    def test_str_numbers_and_seconds(self):
        """games/wins строками, time в секундах — реальный формат
        OpenDota itemTimings."""
        with tempfile.TemporaryDirectory() as td:
            d = make_data(Path(td), builds={
                "1": [{"item": "blink", "time": "450", "games": "733",
                       "wins": "388"}]})
            gd = load_data(d)
        r = gd.builds[1][0]
        self.assertEqual(r["games"], 733)
        self.assertEqual(r["time_s"], 450)
        self.assertAlmostEqual(r["min"], 7.5)

    def test_flat_and_wrapped(self):
        """Плоский heroes.json без обёртки тоже читается."""
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "heroes.json").write_text(json.dumps(
                {"9": {"name": "x", "localized_name": "X"}}))
            gd = load_data(t)
        self.assertIn(9, gd.heroes)

    def test_bad_file_warns_not_crashes(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            make_data(t)
            (t / "matchups.json").write_text("{broken", encoding="utf-8")
            gd = load_data(t)
            self.assertTrue(gd.warnings)
            self.assertEqual(gd.matchups, {})


class Phases(unittest.TestCase):
    def test_phase_by_reveal_count(self):
        s = DraftState()
        self.assertEqual(s.phase, 1)
        s.enemy_ids = [1, 2]
        self.assertEqual(s.phase, 2)
        s.enemy_ids = [1, 2, 3, 4]
        self.assertEqual(s.phase, 3)


class Scoring(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_phase1_meta_order(self):
        """Без врагов — сортировка по винрейту меты."""
        make_data(self.tmp)
        gd = load_data(self.tmp)
        top = recommend_picks(DraftState(), gd)
        self.assertEqual(top[0].hero_id, 2)      # wr_all 55 — макс
        self.assertIn("мета", top[0].why())

    def test_shrinkage_tiny_sample(self):
        """4 победы в 4 играх не должны давать +50."""
        make_data(self.tmp, matchups={
            "2": {"10": {"games": 4, "wins": 4, "wr": 100.0}},
        })
        gd = load_data(self.tmp)
        st = DraftState(enemy_ids=[10])
        top = recommend_picks(st, gd, top=10)
        bb = next(r for r in top if r.hero_id == 2)
        # 4/(4+200) ≈ 0.02 — вклад матчапа ≈ (100−55)*0.02 ≈ +0.9, не +45
        self.assertLess(bb.breakdown["vs"], 2.0)
        self.assertGreater(bb.breakdown["vs"], 0.0)

    def test_adv_subtracts_candidate_base(self):
        """wr 54 vs враг: слабый в мете кандидат (base 48) получает больше
        за матчап, чем сильный (base 55)."""
        make_data(self.tmp, matchups={
            "2": {"10": {"games": 5000, "wins": 2700, "wr": 54.0}},
            "3": {"10": {"games": 5000, "wins": 2700, "wr": 54.0}},
        })
        gd = load_data(self.tmp)
        st = DraftState(enemy_ids=[10])
        top = recommend_picks(st, gd, top=10)
        vs = {r.hero_id: r.breakdown["vs"] for r in top}
        self.assertGreater(vs[3], vs[2])   # 54−48 > 54−55

    def test_taken_and_banned_excluded(self):
        make_data(self.tmp)
        gd = load_data(self.tmp)
        st = DraftState(banned_ids=[2])
        ids = [r.hero_id for r in recommend_picks(st, gd, top=10)]
        self.assertNotIn(2, ids)
        st = DraftState(enemy_ids=[2])
        ids = [r.hero_id for r in recommend_picks(st, gd, top=10)]
        self.assertNotIn(2, ids)

    def test_pos_filter(self):
        """С positions.json герой без игр на моей позиции отсеивается."""
        make_data(self.tmp, positions={
            "1": {"5": 0.9}, "2": {"1": 0.9}, "3": {"1": 0.9},
            "4": {"5": 0.9}, "5": {"2": 0.9},
        })
        gd = load_data(self.tmp)
        st = DraftState(my_pos=1)
        ids = [r.hero_id for r in recommend_picks(st, gd, top=10)]
        self.assertIn(2, ids)          # керри
        self.assertIn(3, ids)
        self.assertNotIn(1, ids)       # чистый саппорт
        self.assertNotIn(5, ids)       # чистый мид

    def test_no_pos_data_no_filter(self):
        make_data(self.tmp)            # positions пустой
        gd = load_data(self.tmp)
        st = DraftState(my_pos=1)
        ids = [r.hero_id for r in recommend_picks(st, gd, top=10)]
        self.assertIn(1, ids)          # без данных фильтр не режет

    def test_lane_weight(self):
        """Враг-оффлейнер сильнее влияет на пик керри, чем враг-керри."""
        make_data(self.tmp,
                  positions={"10": {"3": 0.95}, "11": {"1": 0.95},
                             "2": {"1": 0.9}},
                  matchups={
                      "2": {"10": {"games": 5000, "wins": 3000, "wr": 60.0},
                            "11": {"games": 5000, "wins": 3000, "wr": 60.0}},
                  })
        gd = load_data(self.tmp)
        # вклад матчапа у кандидата 2 против оффлейнера (10) должен быть
        # больше, чем против керри (11): моя позиция — 1 (сейф)
        r10 = recommend_picks(DraftState(enemy_ids=[10], my_pos=1),
                              gd, top=10)
        r11 = recommend_picks(DraftState(enemy_ids=[11], my_pos=1),
                              gd, top=10)
        vs10 = next(r.breakdown["vs"] for r in r10 if r.hero_id == 2)
        vs11 = next(r.breakdown["vs"] for r in r11 if r.hero_id == 2)
        self.assertGreater(vs10, vs11)

    def test_pool_bonus(self):
        make_data(self.tmp, profile={"3": {"games": 100, "wr": 62.0}})
        gd = load_data(self.tmp)
        top = recommend_picks(DraftState(), gd, top=10)
        cc = next(r for r in top if r.hero_id == 3)
        self.assertGreater(cc.breakdown["pool"], 0)

    def test_synergy(self):
        make_data(self.tmp, synergies={
            "3": {"1": {"games": 3000, "wins": 1800, "wr": 60.0}}})
        gd = load_data(self.tmp)
        st = DraftState(ally_ids=[1])
        top = recommend_picks(st, gd, top=10)
        cc = next(r for r in top if r.hero_id == 3)
        self.assertGreater(cc.breakdown["with"], 0)


class Composition(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_roles_loaded(self):
        make_data(self.tmp, heroes={
            "1": {"name": "x", "localized_name": "X",
                  "roles": ["Initiator"], "attack_type": "Melee"}})
        gd = load_data(self.tmp)
        self.assertEqual(gd.roles[1], ["Initiator"])
        self.assertEqual(gd.attack_type[1], "Melee")

    def test_no_allies_no_warnings(self):
        make_data(self.tmp)
        gd = load_data(self.tmp)
        self.assertEqual(team_gaps([], gd), [])

    def test_missing_roles_warned(self):
        """Один саппорт в команде: закрыт только его тег."""
        make_data(self.tmp)
        gd = load_data(self.tmp)
        gaps = team_gaps([1], gd)
        self.assertIn("нет инициации", gaps)
        self.assertIn("нет контроля", gaps)
        self.assertIn("нет фронтлайна", gaps)
        self.assertTrue(any("маг" in g for g in gaps))
        self.assertNotIn("нет саппорта", gaps)

    def test_balanced_team_no_warnings(self):
        make_data(self.tmp, heroes={
            str(i): {"name": f"h{i}", "localized_name": f"H{i}",
                     "roles": [role]}
            for i, role in enumerate(
                ["Initiator", "Disabler", "Durable", "Support", "Nuker"],
                start=1)})
        gd = load_data(self.tmp)
        self.assertEqual(team_gaps([1, 2, 3, 4, 5], gd), [])

    def test_gap_filler_scores_higher(self):
        """Равные по мете кандидаты: закрывающий пробел выше."""
        make_data(self.tmp, heroes={
            "1": {"name": "s", "localized_name": "Sup",
                  "roles": ["Support"]},
            "2": {"name": "i", "localized_name": "Ini",
                  "roles": ["Initiator"]},
            "3": {"name": "c", "localized_name": "Car",
                  "roles": ["Carry"]},
            "4": {"name": "f", "localized_name": "Flex",
                  "roles": ["Initiator", "Disabler", "Durable", "Nuker"]},
        }, meta={str(i): {"wr_all": 52, "wr_bracket": {}, "picks": 100}
                 for i in range(1, 5)})
        gd = load_data(self.tmp)
        top = recommend_picks(DraftState(ally_ids=[1]), gd, top=10)
        by_id = {r.hero_id: r for r in top}
        self.assertAlmostEqual(by_id[2].breakdown["comp"], 0.8)
        self.assertEqual(by_id[3].breakdown["comp"], 0)
        self.assertGreater(by_id[2].score, by_id[3].score)
        self.assertIn("состав", by_id[2].why())
        self.assertAlmostEqual(by_id[4].breakdown["comp"], 1.5)  # cap


class Items(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)
        make_data(self.tmp, builds={
            "1": [
                {"item": "treads", "time_s": 450, "games": 900, "wr": 51},
                {"item": "bkb", "time_s": 1500, "games": 800, "wr": 53},
                {"item": "daedalus", "time_s": 2400, "games": 300, "wr": 55},
            ]},
            items={"rules": [{"if_enemy": ["dd"], "suggest": ["nullifier"]}],
                   "prices": {"treads": 1400, "bkb": 4050,
                              "daedalus": 5100, "nullifier": 4375}},
        )
        self.gd = load_data(self.tmp)

    def tearDown(self):
        self.td.cleanup()

    def test_window_seconds(self):
        """На 20-й минуте (1200с) окно 900-1800с: попадает bkb (1500),
        не treads (450) и не daedalus (2400)."""
        out = recommend_items(1, [], set(), 5000, 1200, self.gd)
        items = [r["item"] for r in out]
        self.assertIn("bkb", items)
        self.assertNotIn("treads", items)
        self.assertNotIn("daedalus", items)

    def test_owned_excluded(self):
        out = recommend_items(1, [], {"bkb"}, 5000, 1200, self.gd)
        self.assertNotIn("bkb", [r["item"] for r in out])

    def test_situational_rule(self):
        out = recommend_items(1, ["dd"], set(), 5000, 1200, self.gd)
        self.assertIn("nullifier", [r["item"] for r in out])

    def test_affordability_flag(self):
        out = recommend_items(1, [], set(), 1000, 1200, self.gd)
        bkb = next(r for r in out if r["item"] == "bkb")
        self.assertFalse(bkb["affordable"])
        self.assertGreater(bkb["need_gold"], 0)


if __name__ == "__main__":
    unittest.main()
