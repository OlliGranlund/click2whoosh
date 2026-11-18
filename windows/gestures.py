"""Button gestures with immediate default taps and optional exclusive long taps.

Configuration is captured on the down edge. No release-time action can be
invented by changing a mapping while a physical button is already held.
"""
import time


class Gestures:
    def __init__(self, emit, clock=time.monotonic):
        self.emit, self.clock = emit, clock
        self.pressed = {}
        self.counts = {}

    def _hold(self, action, down, device):
        count = self.counts.get(action, 0)
        if down:
            self.counts[action] = count + 1
            if count == 0:
                if self.emit("down", action, device) is False:
                    self.counts.pop(action, None)
                    return False
            return True
        elif count:
            if count == 1:
                self.counts.pop(action)
                self.emit("up", action, device)
            else:
                self.counts[action] = count - 1

    def buttons(self, device, held, mapping, options):
        now = self.clock()
        for identity in list(self.pressed):
            if identity[0] == device and identity[1] not in held:
                entry = self.pressed.pop(identity)
                if entry["mode"] == "hold" and entry.get("holding"):
                    self._hold(entry["action"], False, device)
                elif entry["long"] != "OFF" and not entry["fired"]:
                    # A release can arrive just before the next scheduler tick.
                    action = entry["long"] if now >= entry["deadline"] else entry["action"]
                    if action != "OFF":
                        self.emit("tap", action, device)
        for button in held:
            identity = (device, button)
            if identity in self.pressed:
                continue
            option = options.get(button, {})
            action = mapping.get(button, "OFF")
            mode = option.get("mode", "tap")
            long = option.get("long", "OFF") if mode == "tap" else "OFF"
            self.pressed[identity] = dict(action=action, mode=mode, long=long, device=device,
                deadline=now + option.get("threshold_ms", 600) / 1000, fired=False)
            if action != "OFF":
                if mode == "hold":
                    self.pressed[identity]["holding"] = self._hold(action, True, device)
                elif long == "OFF":
                    self.emit("tap", action, device)

    def tick(self):
        for entry in list(self.pressed.values()):
            if entry["long"] != "OFF" and not entry["fired"] and self.clock() >= entry["deadline"]:
                entry["fired"] = True
                self.emit("tap", entry["long"], entry["device"])

    def clear(self, device=None):
        for identity in list(self.pressed):
            if device is None or identity[0] == device:
                entry = self.pressed.pop(identity)
                if entry["mode"] == "hold" and entry.get("holding"):
                    self._hold(entry["action"], False, identity[0])
