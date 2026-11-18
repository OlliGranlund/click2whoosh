import asyncio
import unittest
from keyboard import Keyboard


class OutputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.keyboard = Keyboard.__new__(Keyboard)
        self.keyboard._held = set()
        self.keyboard._active = set()
        self.keyboard._pulsing = set()
        self.keyboard._tap_tasks = {}
        self.keyboard._tap_locks = {}
        self.events = []
        self.keyboard.send = lambda key, up=False: self.events.append((key, up))
        self.keyboard.target_active = lambda: True

    async def asyncTearDown(self):
        await self.keyboard.clear()

    async def test_rapid_taps_preserve_transitions_without_blocking_loop(self):
        for _ in range(3):
            self.keyboard.queue_tap("K", lambda:True, "right")
        await asyncio.sleep(.005)
        self.assertEqual(self.events, [("K", False)])
        await asyncio.gather(*list(self.keyboard._tap_tasks))
        self.assertEqual(self.events, [("K", False), ("K", True)] * 3)

    async def test_disconnect_drops_queued_shifts_and_preserves_other_pods_hold(self):
        self.keyboard.hold("A", True)
        for _ in range(3):
            self.keyboard.queue_tap("K", lambda:True, "right")
        await asyncio.sleep(.005)
        await self.keyboard.clear_device("right")
        self.assertEqual(self.events.count(("K", False)), 1)
        self.assertEqual(self.events.count(("K", True)), 1)
        self.assertNotIn(("A", True), self.events)
        self.keyboard.hold("A", False)
        self.assertEqual(self.events[-1], ("A", True))

    async def test_pending_taps_respect_output_disable_and_focus(self):
        enabled = True
        for _ in range(3):
            self.keyboard.queue_tap("K", lambda:enabled)
        await asyncio.sleep(.005)
        enabled = False
        await asyncio.gather(*list(self.keyboard._tap_tasks))
        self.assertEqual(self.events, [("K",False),("K",True)])
        self.keyboard.target_active = lambda:False
        self.keyboard.queue_tap("K", lambda:True)
        await asyncio.gather(*list(self.keyboard._tap_tasks))
        self.assertEqual(len(self.events), 2)
