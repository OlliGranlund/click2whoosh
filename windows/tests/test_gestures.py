import unittest
from gestures import Gestures


class GestureTests(unittest.TestCase):
    def test_failed_hold_does_not_release_another_sources_successful_hold(self):
        accepted = False
        events = []
        def emit(event, action, device):
            if event == "down" and not accepted:
                return False
            events.append((event, action))
        gestures = Gestures(emit)
        options = {"plus":{"mode":"hold"}}
        gestures.buttons("failed",{"plus"},dict(plus="A"),options)
        accepted = True
        gestures.buttons("working",{"plus"},dict(plus="A"),options)
        gestures.clear("failed")
        self.assertEqual(events,[("down","A")])
        gestures.clear("working")
        self.assertEqual(events,[("down","A"),("up","A")])

    def setUp(self):
        self.events = []
        self.now = 0
        self.g = Gestures(lambda event, action, device: self.events.append((event, action)), lambda: self.now)
        self.mapping = dict(plus="K", b="I")

    def test_default_taps_are_immediate_and_duplicates_do_not_repeat(self):
        self.g.buttons("right", {"plus"}, self.mapping, {})
        self.g.buttons("right", {"plus"}, self.mapping, {})
        self.g.buttons("right", set(), self.mapping, {})
        self.g.buttons("right", {"plus"}, self.mapping, {})
        self.assertEqual(self.events, [("tap", "K"), ("tap", "K")])

    def test_short_and_long_are_exclusive_and_threshold_release_is_handled(self):
        options = dict(plus=dict(long="H", threshold_ms=600))
        self.g.buttons("right", {"plus"}, self.mapping, options)
        self.now = .2
        self.g.buttons("right", set(), self.mapping, options)
        self.assertEqual(self.events, [("tap", "K")])
        self.g.buttons("right", {"plus"}, self.mapping, options)
        self.now = .9
        self.g.tick()
        self.g.tick()
        self.g.buttons("right", set(), self.mapping, options)
        self.assertEqual(self.events, [("tap", "K"), ("tap", "H")])
        self.g.buttons("right", {"plus"}, self.mapping, options)
        self.now = 2
        self.g.buttons("right", set(), self.mapping, options)
        self.assertEqual(self.events[-1], ("tap", "H"))

    def test_shared_hold_released_after_last_source_and_disconnect(self):
        mapping = dict(plus="A", b="A")
        options = dict(plus=dict(mode="hold"), b=dict(mode="hold"))
        self.g.buttons("one", {"plus", "b"}, mapping, options)
        self.g.buttons("two", {"plus"}, mapping, options)
        self.g.buttons("one", {"b"}, mapping, options)
        self.g.clear("two")
        self.assertEqual(self.events, [("down", "A")])
        self.g.clear("one")
        self.assertEqual(self.events, [("down", "A"), ("up", "A")])

    def test_clear_cancels_pending_long_and_short_and_mapping_is_captured(self):
        self.g.buttons("right", {"plus"}, self.mapping, dict(plus=dict(long="H")))
        self.g.clear()
        self.now = 4
        self.g.tick()
        self.assertEqual(self.events, [])
        self.g.buttons("right", {"plus"}, self.mapping, dict(plus=dict(long="H")))
        self.now = 4.1
        self.g.buttons("right", set(), dict(plus="Z"), {})
        self.assertEqual(self.events, [("tap", "K")])
