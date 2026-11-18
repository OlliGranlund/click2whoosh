"""Exercise the packaged native UI without radios, devices or keyboard injection."""
import asyncio
import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import font
from types import SimpleNamespace
from ui import App


class MonitorEngine:
    enabled = False
    scanning = False
    mapping = {}

    def __init__(self):
        self.messages = []

    def log(self, message):
        self.messages.append(message)


def run(output, runtime):
    report = {"ok": False, "sizes": [], "errors": []}
    root = tk.Tk()
    try:
        with tempfile.TemporaryDirectory(prefix="click2whoosh-ui-") as temp:
            engine = MonitorEngine()
            app = App(root, runtime, engine=engine, data_dir=Path(temp))
            app.notify_battery_alert = lambda: None
            # Feed the same event contract as a physical notification; no radio is opened.
            app.events.put(("device", ("smoke-right", "Zwift Click", "Click v2 right", -55)))
            app.events.put(("state", ("smoke-right", "Receiving controls")))
            app.events.put(("buttons", ("smoke-right", 10, {"plus"})))
            app.events.put(("log", "UI test: + → K (monitor mode)"))
            app.poll()
            assert app.presses == 1 and app.controller.held["right"] == {"plus"}
            assert not engine.enabled
            assert app.battery_text("smoke-right") == "Unknown"
            app.events.put(("battery", ("smoke-right", 18, __import__("time").time())))
            app.events.put(("battery_alert", ("smoke-right", 18, "low")))
            app.poll()
            root.update()
            assert app.battery_text("smoke-right") == "18%"
            assert "18%" in app.alert_text.get() and app.alert_bar.winfo_ismapped()
            app.dismiss_alerts()
            root.update()
            assert not app.alerts and not app.alert_bar.winfo_ismapped()
            app.sound.set(False)
            app.save_preferences()
            assert json.loads((Path(temp) / "preferences.json").read_text())["battery_sound"] is False
            app.variables["plus"].set("J")
            app.save()
            assert json.loads((Path(temp) / "settings.json").read_text())["plus"] == "J"
            app.reset()
            assert engine.mapping["plus"] == "K"
            for width, height in ((1080, 850), (920, 760), (1440, 1000)):
                root.geometry(f"{width}x{height}")
                root.update()
                for tab in (app.ride, app.maps, app.logs, app.setup):
                    app.tabs.select(tab)
                    root.update()
                    # Every visible control must fit inside the client area.
                    def walk(widget):
                        for child in widget.winfo_children():
                            if child.winfo_ismapped():
                                x = child.winfo_rootx() - root.winfo_rootx()
                                y = child.winfo_rooty() - root.winfo_rooty()
                                if x < -1 or y < -1 or x+child.winfo_width() > root.winfo_width()+1 or y+child.winfo_height() > root.winfo_height()+1:
                                    report["errors"].append(f"{width}x{height} {tab}: {child.winfo_class()} outside client bounds")
                                walk(child)
                    walk(root)
                    if not app.footer.winfo_ismapped():
                        report["errors"].append(f"{width}x{height}: footer clipped")
                    if tab == app.ride and not app.left_help.winfo_ismapped():
                        report["errors"].append(f"{width}x{height}: setup help clipped")
                    if tab == app.maps and not app.maps.winfo_children()[-1].winfo_ismapped():
                        report["errors"].append(f"{width}x{height}: mapping feedback clipped")
                    if tab == app.setup and not app.setup.winfo_children()[-1].winfo_ismapped():
                        report["errors"].append(f"{width}x{height}: MyWhoosh setup controls clipped")
                report["sizes"].append(f"{width}x{height}")
            app.tabs.select(app.ride)
            app.events.put(("buttons", ("smoke-right", 10, set())))
            app.events.put(("state", ("smoke-right", "Disconnected")))
            app.poll()
            assert not app.controller.held["right"]
            assert app.battery_text("smoke-right") == "18% last"
            report["fonts"] = {name: name in font.families(root) for name in ("Urbanist", "DM Mono")}
            report["checks"] = ["live button highlight", "monitor default", "mapping save and reset", "all four tabs at three window sizes", "disconnect clears highlight", "battery percent and low alert", "dismiss alert", "offline battery is last-known", "alert sound preference"]
            report["ok"] = not report["errors"]
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        root.destroy()
        output.write_text(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)
