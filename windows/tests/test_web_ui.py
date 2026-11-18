import unittest
import json
from types import SimpleNamespace
from unittest.mock import Mock
from tempfile import TemporaryDirectory
from pathlib import Path
import time
import app
from web_ui import Api


class BridgeTests(unittest.TestCase):
    def test_gestures_profiles_persist_and_loading_pauses_output(self):
        with TemporaryDirectory() as temp:
            runtime = SimpleNamespace(DEFAULTS=app.DEFAULTS, KEYS=app.KEYS, DATA=Path(temp), Engine=Mock())
            api = Api(runtime)
            self.assertIn("error", api.command("gestures", {"plus":{"threshold_ms":True}}))
            self.assertIn("error", api.command("gestures", {"plus":{"long":"INVALID"}}))
            options = {"plus":{"long":"H","threshold_ms":600,"mode":"tap"},"left":{"mode":"hold"}}
            self.assertTrue(api.command("gestures",options)["ok"])
            self.assertTrue(api.command("save_profile","Ride setup")["ok"])
            self.assertTrue(api.command("gestures",{})["ok"])
            api._state["enabled"] = True
            self.assertTrue(api.command("load_profile","Ride setup")["ok"])
            self.assertFalse(api.snapshot()["enabled"])
            self.assertEqual(api.snapshot()["gestures"]["plus"]["long"],"H")
            restored = Api(runtime)
            self.assertEqual(restored.snapshot()["profiles"],["Ride setup"])
            self.assertEqual(restored.snapshot()["gestures"]["left"]["mode"],"hold")
            self.assertTrue(restored.command("delete_profile","Ride setup")["ok"])
            self.assertEqual(Api(runtime).snapshot()["profiles"],[])

    def test_automation_is_opt_in_validated_and_persisted(self):
        with TemporaryDirectory() as temp:
            runtime = SimpleNamespace(DEFAULTS=app.DEFAULTS, KEYS=app.KEYS, DATA=Path(temp), Engine=Mock())
            api = Api(runtime)
            self.assertFalse(api.snapshot()["automation"]["auto_focus"])
            self.assertIn("error", api.command("automation",{"auto_focus":True}))
            settings = dict(auto_focus=True, background_scan=True, auto_launch=False)
            self.assertTrue(api.command("automation",settings)["ok"])
            self.assertTrue(Api(runtime).snapshot()["automation"]["background_scan"])
            self.assertFalse(Api(runtime).snapshot()["enabled"])

    def test_events_and_stale_battery(self):
        api = Api(app, smoke=True)
        api._event("device", ("right", "Click", "Click v2 right", -60))
        api._event("state", ("right", "Receiving controls"))
        api._event("buttons", ("right", 10, {"plus"}))
        api._event("battery", ("right", 18, time.time()))
        self.assertEqual(api.snapshot()["devices"][0]["battery"], "18%")
        self.assertEqual(api.snapshot()["held"]["right"], ["plus"])
        api._event("state", ("right", "Disconnected"))
        self.assertEqual(api.snapshot()["devices"][0]["battery"], "18% last")
        self.assertEqual(api.snapshot()["held"]["right"], [])

    def test_mapping_validation_and_persistence(self):
        with TemporaryDirectory() as temp:
            runtime = SimpleNamespace(DEFAULTS=app.DEFAULTS, KEYS=app.KEYS, DATA=Path(temp))
            api = Api(runtime, smoke=True)
            api._smoke = False
            api._engine = Mock()
            self.assertIn("error", api.command("mapping", {"plus": "BAD"}))
            mapping = {**app.DEFAULTS, "plus": "J"}
            self.assertTrue(api.command("mapping", mapping)["ok"])
            self.assertEqual(api._engine.mapping["plus"], "J")
            self.assertTrue((Path(temp) / "settings.json").exists())
            self.assertIn("error", api.command("unknown"))

    def test_smoke_disables_device_actions(self):
        api = Api(app, smoke=True)
        self.assertIn("error", api.command("scan"))
        self.assertFalse(api.snapshot()["enabled"])

    def test_left_recovery_preference_preserves_sound_and_reloads(self):
        with TemporaryDirectory() as temp:
            runtime = SimpleNamespace(DEFAULTS=app.DEFAULTS, KEYS=app.KEYS, DATA=Path(temp), Engine=Mock())
            api = Api(runtime)
            self.assertFalse(api.snapshot()["left_restart"])
            self.assertTrue(api.command("left_restart", True)["ok"])
            self.assertTrue(api._engine.left_restart)
            self.assertTrue(api.command("sound", False)["ok"])
            prefs = json.loads((Path(temp) / "preferences.json").read_text())
            self.assertEqual(prefs, {"battery_sound": False, "experimental_left_restart": True})
            reloaded = Api(runtime)
            self.assertTrue(reloaded.snapshot()["left_restart"])
            self.assertFalse(reloaded.snapshot()["sound"])
            self.assertIn("error", reloaded.command("left_restart", "true"))

    def test_restarting_clears_left_highlight_and_marks_battery_last(self):
        api = Api(app, smoke=True)
        api._event("device", ("left", "Click", "Click v2 left", -60))
        api._event("battery", ("left", 100, time.time()))
        api._event("buttons", ("left", 11, {"minus"}))
        api._event("state", ("left", "Experimental restart; reconnecting"))
        state = api.snapshot()
        self.assertEqual(state["held"]["left"], [])
        self.assertEqual(state["devices"][0]["battery"], "100% last")

    def test_fast_taps_survive_between_button_snapshots(self):
        api = Api(app, smoke=True)
        for _ in range(3):
            api._event("buttons", ("left", 11, {"minus"}))
            api._event("buttons", ("left", 11, {"minus"}))  # duplicate notification
            api._event("buttons", ("left", 11, set()))
        api._event("buttons", ("right", 10, {"plus"}))
        api._event("buttons", ("right", 10, set()))
        state = api.button_snapshot()
        self.assertEqual(state["held"], {"left": [], "right": []})
        self.assertEqual(state["counts"], {"left": {"minus": 3}, "right": {"plus": 1}})
        self.assertEqual(api.button_snapshot(), state)  # reading never consumes events
        state["counts"]["left"]["minus"] = 100
        self.assertEqual(api.button_snapshot()["counts"]["left"]["minus"], 3)

    def test_disconnect_invalidates_visual_pulses_and_starts_new_counter_epoch(self):
        api = Api(app, smoke=True)
        api._event("device", ("left", "Click", "Click v2 left", -60))
        api._event("buttons", ("left", 11, {"minus"}))
        before = api.button_snapshot()
        api._event("state", ("left", "Disconnected"))
        after = api.button_snapshot()
        self.assertEqual(after["held"]["left"], [])
        self.assertGreater(after["epochs"]["left"], before["epochs"]["left"])
        self.assertEqual(after["counts"]["left"], {})

    def test_low_battery_cutoff_persists_off_and_requires_fresh_recovered_reading(self):
        with TemporaryDirectory() as temp:
            runtime = SimpleNamespace(DEFAULTS=app.DEFAULTS, KEYS=app.KEYS, DATA=Path(temp), Engine=Mock())
            api = Api(runtime)
            api.command("sound", False)
            api.command("left_restart", True)
            api._event("device", ("left", "Click", "Click v2 left", -60))
            api._event("battery", ("left", 18, time.time()))
            api._event("left_restart_stopped", "Recovery stopped at reported 18%")
            self.assertFalse(api.snapshot()["left_restart"])
            self.assertFalse(api._engine.left_restart)
            self.assertIn("18%", api.snapshot()["recovery_notice"])
            self.assertIn("error", api.command("left_restart", True))
            reloaded = Api(runtime)
            self.assertFalse(reloaded.snapshot()["left_restart"])
            self.assertFalse(reloaded.snapshot()["sound"])
            api._event("battery", ("left", 100, time.time()))
            self.assertFalse(api.snapshot()["left_restart"])
            self.assertTrue(api.command("left_restart", True)["ok"])
            self.assertIsNone(api.snapshot()["recovery_notice"])

    def test_connection_choice_persistence_and_pairing_gate(self):
        with TemporaryDirectory() as temp:
            runtime = SimpleNamespace(DEFAULTS=app.DEFAULTS, KEYS=app.KEYS, DATA=Path(temp), Engine=Mock())
            api = Api(runtime)
            self.assertTrue(api.command("connection_method", "network")["ok"])
            self.assertFalse(api.snapshot()["enabled"])
            self.assertTrue(api.snapshot()["connection_busy"])
            self.assertIn("error", api.command("connection_method", "keyboard"))
            api._event("connection_method", "network")
            api._engine.network.connected = False
            self.assertIn("error", api.command("enable", True))
            api._engine.network.connected = True
            self.assertTrue(api.command("enable", True)["ok"])
            api._event("network", {"connected": False, "status": "Waiting for MyWhoosh pairing"})
            self.assertFalse(api.snapshot()["enabled"])
            self.assertFalse(api._engine.enabled)
            self.assertEqual(Api(runtime).snapshot()["connection_method"], "network")
            self.assertIn("error", api.command("connection_method", "invalid"))

    def test_network_mapping_is_separate_validated_and_pauses_output(self):
        with TemporaryDirectory() as temp:
            runtime = SimpleNamespace(DEFAULTS=app.DEFAULTS, KEYS=app.KEYS, DATA=Path(temp), Engine=Mock())
            api = Api(runtime)
            self.assertIn("error", api.command("network_mapping", {"plus": "invalid"}))
            mapping = {**api.snapshot()["network_mapping"], "a": "back"}
            api._state["enabled"] = True
            self.assertTrue(api.command("network_mapping", mapping)["ok"])
            self.assertFalse(api.snapshot()["enabled"])
            self.assertEqual(api.snapshot()["mapping"], app.DEFAULTS)
            self.assertEqual(Api(runtime).snapshot()["network_mapping"]["a"], "back")
