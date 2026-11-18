"""Bundled React/Tailwind interface over the existing Bluetooth engine."""
import json
import os
from pathlib import Path
import threading
import time
import uuid
import re
import webview
from openbikecontrol import ACTIONS, DEFAULT_MAPPING as NETWORK_DEFAULTS
from desktop import keyboard_available, open_folder, battery_attention


class Api:
    def __init__(self, runtime, smoke=False):
        self._runtime = runtime
        self._lock = threading.RLock()
        self._state = dict(devices=[], logs=[], mapping=dict(runtime.DEFAULTS), enabled=False,
                          scanning=False, alerts=[], sound=True, left_restart=False, recovery_notice=None, held={},
                          connection_method="keyboard" if keyboard_available() else "network", keyboard_available=keyboard_available(),
                          connection_busy=False, network_mapping=dict(NETWORK_DEFAULTS),
                          network=dict(status="Off", connected=False), gestures={},
                          unlock=dict(ready=False, busy=False, message="Optional Zwift sign-in for the left Click."))
        self._state["automation"] = dict(auto_focus=False, background_scan=False, auto_launch=False, program="")
        self._profiles = {}
        self._state["profiles"] = []
        self._connection_id = uuid.uuid4().hex
        self._devices = {}
        self._last_battery = {}
        self._press_counts = {"left": {}, "right": {}}
        self._button_epochs = {"left": 0, "right": 0}
        self._smoke = smoke
        self._engine = None
        self._window = None
        start_saved_network = False
        if not smoke:
            runtime.DATA.mkdir(parents=True, exist_ok=True)
            for name, key in (("settings.json", "mapping"), ("preferences.json", "sound")):
                try:
                    saved = json.loads((runtime.DATA / name).read_text())
                    if key == "mapping" and isinstance(saved, dict):
                        self._state[key].update({k: v for k, v in saved.items() if k in runtime.DEFAULTS and v in runtime.KEYS})
                    elif key == "sound":
                        self._state[key] = saved.get("battery_sound", True) is True
                        self._state["left_restart"] = saved.get("experimental_left_restart", False) is True
                except (OSError, ValueError, AttributeError):
                    pass
            try:
                connection = json.loads((runtime.DATA / "connection.json").read_text())
                if connection.get("method") in ("keyboard", "network"):
                    self._state["connection_method"] = connection["method"] if keyboard_available() else "network"
                    start_saved_network = self._state["connection_method"] == "network"
                if isinstance(connection.get("mapping"), dict):
                    self._state["network_mapping"].update({k: v for k, v in connection["mapping"].items() if k in NETWORK_DEFAULTS and isinstance(v, str) and v in ACTIONS})
                identity = connection.get("id", "")
                if isinstance(identity, str) and len(identity) == 32 and all(c in "0123456789abcdef" for c in identity):
                    self._connection_id = identity
            except (OSError, ValueError, AttributeError):
                pass
            self._engine = runtime.Engine(self._event)
            self._state["unlock"]["ready"] = self._engine.unlock.ready is True
            try:
                options = json.loads((runtime.DATA / "gestures.json").read_text())
                self._state["gestures"] = self._validate_gestures(options)
            except (OSError, ValueError, TypeError):
                pass
            self._engine.gesture_options = dict(self._state["gestures"])
            try:
                saved = json.loads((runtime.DATA / "automation.json").read_text())
                for key in ("auto_focus", "background_scan", "auto_launch"):
                    self._state["automation"][key] = saved.get(key) is True
                program = saved.get("program", "")
                if isinstance(program, str):
                    self._state["automation"]["program"] = program
            except (OSError, ValueError, AttributeError):
                pass
            for key, value in self._state["automation"].items():
                setattr(self._engine, key, value)
            try:
                saved = json.loads((runtime.DATA / "profiles.json").read_text())
                if isinstance(saved, dict):
                    for name, profile in saved.items():
                        if re.fullmatch(r"[\w -]{1,40}", name) and isinstance(profile, dict):
                            mapping = profile.get("mapping")
                            if isinstance(mapping, dict) and set(mapping) == set(runtime.DEFAULTS) and all(isinstance(v, str) and v in runtime.KEYS for v in mapping.values()):
                                self._profiles[name] = dict(mapping=mapping, gestures=self._validate_gestures(profile.get("gestures", {})))
                    self._state["profiles"] = sorted(self._profiles)
            except (OSError, ValueError, TypeError):
                pass
            self._engine.mapping = dict(self._state["mapping"])
            self._engine.left_restart = self._state["left_restart"]
            self._engine.network_mapping = dict(self._state["network_mapping"])
            if start_saved_network:
                self._state["connection_busy"] = True
                self._engine.submit(self._engine.set_connection_method("network", self._connection_id))

    def _event(self, kind, value):
        with self._lock:
            if kind == "device":
                address, name, label, _ = value
                self._devices.setdefault(address, dict(address=address, name=label, state="Discovered", battery="Unknown"))
            elif kind == "state":
                address, state = value
                if address in self._devices:
                    self._devices[address]["state"] = state
                    if state in ("Disconnected", "Connecting", "Experimental restart; reconnecting"):
                        side = "right" if "right" in self._devices[address]["name"].lower() else "left"
                        self._state["held"][side] = []
                        self._press_counts[side] = {}
                        self._button_epochs[side] += 1
            elif kind == "buttons":
                address, device_kind, buttons = value
                side = "right" if device_kind in (2, 7, 10) else "left"
                previous = set(self._state["held"].get(side, []))
                for button in set(buttons) - previous:
                    counts = self._press_counts[side]
                    counts[button] = counts.get(button, 0) + 1
                self._state["held"][side] = sorted(buttons)
            elif kind == "battery":
                address, level, timestamp = value
                if level is not None:
                    self._last_battery[address] = (level, timestamp)
                    if level > 20:
                        self._state["alerts"] = [a for a in self._state["alerts"] if a["address"] != address]
                    else:
                        for alert in self._state["alerts"]:
                            if alert["address"] == address:
                                alert.update(level=level, stage="critical" if level <= 10 else "low")
                if address in self._devices:
                    self._devices[address]["battery_current"] = level
            elif kind == "battery_alert":
                address, level, stage = value
                self._state["alerts"] = [a for a in self._state["alerts"] if a["address"] != address]
                self._state["alerts"].append(dict(address=address, level=level, stage=stage, name=self._devices.get(address, {}).get("name", "Controller")))
                if not self._smoke:
                    battery_attention(self._window, self._state["sound"])
            elif kind == "network":
                self._state["network"] = value
                if not value.get("connected") and self._state["connection_method"] == "network":
                    self._state["enabled"] = False
                    if self._engine:
                        self._engine.enabled = False
            elif kind == "connection_method":
                self._state["connection_method"] = value
                self._state["connection_busy"] = False
            elif kind == "output_enabled":
                self._state["enabled"] = value
            elif kind == "unlock_status":
                self._state["unlock"] = value
            elif kind == "left_restart_stopped":
                self._state["left_restart"] = False
                self._state["recovery_notice"] = value
                if self._engine:
                    self._engine.left_restart = False
                if not self._smoke:
                    try:
                        self._save("preferences.json", dict(battery_sound=self._state["sound"], experimental_left_restart=False))
                    except OSError as exc:
                        self._state["logs"].append(f"Could not save disabled recovery preference: {exc}")
            elif kind == "log":
                self._state["logs"].append(time.strftime("%H:%M:%S  ") + value)
                self._state["logs"] = self._state["logs"][-500:]

    def snapshot(self):
        with self._lock:
            for address, device in self._devices.items():
                last = self._last_battery.get(address)
                fresh = last and time.time() - last[1] <= 120 and device.get("battery_current") is not None and device["state"] not in ("Disconnected", "Connecting", "Experimental restart; reconnecting")
                device["battery"] = f"{last[0]}%" if fresh else f"{last[0]}% last" if last else "Unknown"
            self._state["devices"] = list(self._devices.values())
            self._state["scanning"] = bool(self._engine and self._engine.scanning)
            return json.loads(json.dumps(self._state))

    def button_snapshot(self):
        """Small, read-only feed: retain taps that ended between UI polls."""
        with self._lock:
            return json.loads(json.dumps(dict(held=self._state["held"],
                                             counts=self._press_counts,
                                             epochs=self._button_epochs)))

    def command(self, action, value=None):
        if self._smoke:
            return {"error": "Device actions are disabled during the UI check."}
        with self._lock:
            if action in ("scan", "right", "disconnect"):
                fn = {"scan": self._engine.scan, "right": self._engine.connect_right, "disconnect": self._engine.disconnect}[action]
                self._engine.submit(fn())
            elif action == "connect" and value in self._devices:
                self._engine.submit(self._engine.connect([value]))
            elif action == "enable" and isinstance(value, bool):
                if value and self._state["connection_method"] == "keyboard" and not keyboard_available():
                    return {"error": "Keyboard output is Windows-only. Choose OpenBikeControl network."}
                if self._state["connection_busy"]:
                    return {"error": "Wait for the connection method to finish changing."}
                if value and self._state["connection_method"] == "network" and not self._engine.network.connected:
                    return {"error": "Pair ClickToWhoosh from MyWhoosh's OpenBikeControl connection screen first."}
                self._engine.enabled = self._state["enabled"] = value
                if not value:
                    self._engine.submit(self._engine.clear_output())
            elif action == "connection_method" and value in ("keyboard", "network"):
                if value == "keyboard" and not keyboard_available():
                    return {"error": "Keyboard output is currently Windows-only."}
                if self._state["connection_busy"]:
                    return {"error": "The previous connection change is still in progress."}
                self._save_connection(method=value)
                self._engine.enabled = self._state["enabled"] = False
                self._state["connection_method"] = value
                self._state["connection_busy"] = True
                self._engine.submit(self._engine.set_connection_method(value, self._connection_id))
            elif action in ("network_mapping", "network_reset"):
                mapping = dict(NETWORK_DEFAULTS) if action == "network_reset" else value
                if not isinstance(mapping, dict) or set(mapping) != set(NETWORK_DEFAULTS) or any(not isinstance(v, str) or v not in ACTIONS for v in mapping.values()):
                    return {"error": "Invalid OpenBikeControl action mapping"}
                self._save_connection(mapping=mapping)
                self._engine.enabled = self._state["enabled"] = False
                self._engine.submit(self._engine.clear_network_buttons())
                self._engine.network_mapping = dict(mapping)
                self._state["network_mapping"] = dict(mapping)
            elif action in ("mapping", "reset"):
                mapping = dict(self._runtime.DEFAULTS) if action == "reset" else value
                if not isinstance(mapping, dict) or set(mapping) != set(self._runtime.DEFAULTS) or any(v not in self._runtime.KEYS for v in mapping.values()):
                    return {"error": "Invalid key mapping"}
                self._save("settings.json", mapping)
                if action == "reset":
                    self._save("gestures.json", {})
                    self._state["gestures"] = {}
                    self._engine.gesture_options = {}
                self._engine.enabled = self._state["enabled"] = False
                self._engine.submit(self._engine.clear_output())
                self._engine.mapping = dict(mapping)
                self._state["mapping"] = dict(mapping)
            elif action == "gestures":
                try:
                    options = self._validate_gestures(value)
                except (ValueError, TypeError):
                    return {"error": "Invalid button behavior settings"}
                self._save("gestures.json", options)
                self._engine.enabled = self._state["enabled"] = False
                self._engine.submit(self._engine.clear_output())
                self._engine.gesture_options = options
                self._state["gestures"] = options
            elif action == "zwift_login":
                if not keyboard_available():
                    return {"error": "Zwift sign-in is currently Windows-only"}
                if self._state["unlock"]["busy"]:
                    return {"error": "Sign-in is already in progress"}
                if not isinstance(value, dict) or not isinstance(value.get("email"), str) or not isinstance(value.get("password"), str) or not value["email"].strip() or not value["password"] or len(value["email"]) > 320 or len(value["password"]) > 1024:
                    return {"error": "Enter your Zwift email and password"}
                self._state["unlock"]["busy"] = True
                self._engine.submit(self._engine.zwift_login(value["email"].strip(), value["password"]))
            elif action == "zwift_forget":
                self._engine.submit(self._engine.zwift_forget())
            elif action == "automation":
                if not isinstance(value, dict) or set(value) != {"auto_focus", "background_scan", "auto_launch"} or any(type(v) is not bool for v in value.values()):
                    return {"error": "Invalid automation settings"}
                settings = dict(self._state["automation"], **value)
                self._save("automation.json", settings)
                self._state["automation"] = settings
                for key, enabled in value.items():
                    setattr(self._engine, key, enabled)
            elif action == "choose_program":
                if not self._window or not keyboard_available():
                    return {"error": "Choose a MyWhoosh executable in the Windows app"}
                paths = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=("MyWhoosh executable (*.exe)",))
                if paths:
                    path = Path(paths[0])
                    if path.suffix.lower() != ".exe" or not path.name.lower().startswith("mywhoosh"):
                        return {"error": "Select the MyWhoosh .exe"}
                    settings = dict(self._state["automation"], program=str(path))
                    self._save("automation.json", settings)
                    self._state["automation"] = settings
                    self._engine.program = str(path)
            elif action == "launch_program":
                self._engine.submit(self._engine.launch_program())
            elif action == "save_profile":
                if not isinstance(value, str) or not re.fullmatch(r"[\w -]{1,40}", value.strip()) or len(self._profiles) >= 30 and value.strip() not in self._profiles:
                    return {"error": "Use a profile name of 1–40 letters, numbers, spaces or hyphens (maximum 30 profiles)"}
                name = value.strip()
                profiles = dict(self._profiles)
                profiles[name] = dict(mapping=dict(self._state["mapping"]), gestures=dict(self._state["gestures"]))
                self._save("profiles.json", profiles)
                self._profiles = profiles
                self._state["profiles"] = sorted(profiles)
            elif action == "load_profile" and isinstance(value, str) and value in self._profiles:
                profile = self._profiles[value]
                self._save("settings.json", profile["mapping"])
                self._save("gestures.json", profile["gestures"])
                self._engine.enabled = self._state["enabled"] = False
                self._engine.submit(self._engine.clear_output())
                self._engine.mapping = dict(profile["mapping"])
                self._engine.gesture_options = dict(profile["gestures"])
                self._state["mapping"] = dict(profile["mapping"])
                self._state["gestures"] = dict(profile["gestures"])
            elif action == "delete_profile" and isinstance(value, str) and value in self._profiles:
                profiles = dict(self._profiles)
                profiles.pop(value)
                self._save("profiles.json", profiles)
                self._profiles = profiles
                self._state["profiles"] = sorted(profiles)
            elif action in ("sound", "left_restart") and isinstance(value, bool):
                if action == "left_restart" and value:
                    for address, (level, _) in self._last_battery.items():
                        if self._devices.get(address, {}).get("name") == "Click v2 left" and level <= 20:
                            return {"error": f"Left controller last reported {level}% battery. Let it rest and reconnect to refresh the reading before enabling recovery."}
                preferences = dict(battery_sound=self._state["sound"], experimental_left_restart=self._state["left_restart"])
                preferences["battery_sound" if action == "sound" else "experimental_left_restart"] = value
                self._save("preferences.json", preferences)
                self._state[action] = value
                if action == "left_restart":
                    self._state["recovery_notice"] = None
                    self._engine.left_restart = value
                    self._engine.log("Experimental left-controller restart " + ("enabled (45 seconds; unverified RESET payload)." if value else "disabled."))
            elif action == "folder":
                open_folder(self._runtime.DATA)
            elif action == "dismiss_alert":
                self._state["alerts"] = [a for a in self._state["alerts"] if a["address"] != value]
            else:
                return {"error": "Unsupported action"}
        return {"ok": True}

    def _save(self, filename, value):
        path = self._runtime.DATA / filename
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, indent=2))
        temp.replace(path)

    def _validate_gestures(self, value):
        if not isinstance(value, dict) or set(value) - set(self._runtime.DEFAULTS):
            raise ValueError("Unknown buttons")
        result = {}
        for button, option in value.items():
            if not isinstance(option, dict) or option.get("mode", "tap") not in ("tap", "hold") or option.get("long", "OFF") not in self._runtime.KEYS:
                raise ValueError("Invalid behavior")
            threshold = option.get("threshold_ms", 600)
            if type(threshold) is not int or not 300 <= threshold <= 2000:
                raise ValueError("Invalid threshold")
            result[button] = dict(mode=option.get("mode", "tap"), long=option.get("long", "OFF"), threshold_ms=threshold)
        return result

    def _save_connection(self, method=None, mapping=None):
        self._save("connection.json", dict(id=self._connection_id,
                   method=method or self._state["connection_method"],
                   mapping=mapping if mapping is not None else self._state["network_mapping"]))


def run(runtime, smoke_output=None):
    import sys
    api = Api(runtime, smoke=smoke_output is not None)
    page = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets/web/index.html"
    window = webview.create_window("ClickToWhoosh · olli.works", str(page), js_api=api, width=1160, height=860, min_size=(820, 650), background_color="#f8fafb")
    api._window = window
    def close():
        if api._engine:
            api._engine.enabled = False
            api._engine.submit(api._engine.shutdown()).result(timeout=15)
            api._engine.loop.call_soon_threadsafe(api._engine.loop.stop)
    window.events.closed += close
    if smoke_output:
        def check():
            report = {"ok": False}
            try:
                time.sleep(1)
                report = window.evaluate_js("({ok:document.querySelectorAll('[role=tab]').length===4 && document.body.innerText.includes('Find & connect Clicks') && document.body.innerText.includes('olli.works') && document.body.innerText.includes('Send buttons to MyWhoosh') && document.getElementById('connection-method')?.options.length===2 && document.getElementById('controls').getBoundingClientRect().bottom < window.innerHeight && typeof window.pywebview?.api?.button_snapshot==='function', tabs:document.querySelectorAll('[role=tab]').length, renderer:'React / Tailwind 4 / Radix'})")
                window.evaluate_js("document.querySelectorAll('[role=tab]')[1].dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}))")
                time.sleep(.2)
                report["gestures"] = window.evaluate_js("!!document.querySelector('[aria-label=\"plus long press\"]') && !!document.querySelector('[aria-label=\"Saved keyboard profile\"], [aria-label=\"New profile name\"]')")
                window.evaluate_js("document.querySelectorAll('[role=tab]')[3].dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}))")
                time.sleep(.2)
                report["setup"] = window.evaluate_js("!!document.querySelector('[aria-label=\"Zwift password\"]') && !!document.querySelector('[aria-label=\"Keep looking for controllers\"]')")
                report["ok"] = report["ok"] and report["gestures"] and report["setup"]
            except Exception as exc:
                report["error"] = str(exc)
            finally:
                Path(smoke_output).write_text(json.dumps(report, indent=2))
                window.destroy()
        window.events.loaded += lambda: threading.Thread(target=check, daemon=True).start()
    webview.start(gui="edgechromium" if __import__("sys").platform == "win32" else None)
