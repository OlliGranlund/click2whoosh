# Technical notes

ClickToWhoosh is a free cycling companion by [olli.works](https://olli.works). This document describes the current source; rolling release binaries can lag behind it. See the [README](../README.md) for setup and release status.

## Battery status and alerts

Each connection reads the standard Bluetooth Battery Level characteristic if it exists, subscribes to battery notifications when supported, and refreshes readable battery levels every 60 seconds. Zwift battery notification/status packets (`0x19` / `0x1a`, percentage field 2) are also supported. Charging-state-only or invalid messages never become a false 0% reading. Some firmware may not report battery levels; those rows show **Unknown**.

At **20% or lower**, a low-battery banner appears; at **10% or lower**, it escalates to critical. The app sounds a configurable alert and flashes its taskbar button without raising a window or stealing focus from MyWhoosh. Disable the sound in **Setup**. **Dismiss** clears the current banner; a later escalation can alert again.

Warnings do not repeat on every notification, poll or reconnect. They rearm after recovery to 25% (low) or 15% (critical), or when the app restarts. A disconnected, newly reconnecting, or more-than-two-minute-old reading is explicitly marked **last** instead of presented as a current measurement. Monitoring does not charge batteries, modify firmware or estimate remaining ride time.

## MyWhoosh configuration

No extra key-remapping software or custom MyWhoosh bindings are needed for the default shifting profile. Enable **Virtual Gear Shifting / MyShift** in MyWhoosh settings, pair your trainer there, and start a ride. First try I and K on a physical keyboard and watch the gear display; then enable controls here and keep MyWhoosh in the foreground. **K = up**, **I = down**, using BikeControl's MyWhoosh mapping. Our + and −/B defaults already send those keys.

MyWhoosh's [official MyShift guide](https://mywhoosh.com/myshift-mywhooshs-virtual-shifting-explained/) documents I/K controls; its [4.0.1 release notes](https://www.mywhoosh.com/new-features-more-control-and-the-best-indoor-cycling-yet-mywhoosh-4-0-0/) document the MyShift settings toggle. If the physical keys do not work, fix the MyShift/trainer setup before changing Click mappings. Other keys and steering behavior depend on the current MyWhoosh screen/version; steering here is still a short tap.

Newer MyWhoosh also supports a direct **OpenBikeControl network** connection. That is a separate integration, described by [BikeControl's official setup guide](https://bikecontrol.app/blog/mywhoosh-bikecontrol-partnership/). Select experimental OpenBikeControl network on the Connections tab to advertise the endpoint. It removes OS key injection from that route; actual MyWhoosh interoperability is still pending hardware verification. Keyboard remains the default tested fallback.

## Click v2 compatibility

Both Click v2 pods can be discovered and have independent connection state. The right controller provides both shift directions with **+ / B**. The app sends plain `RideOn` on startup and every three seconds to the right pod; reconnects start with fresh button state.

The left pod can require activation in Zwift before it sends input. Connect it in Zwift, verify its buttons there, then close Zwift and reconnect here. Activation behavior depends on firmware. This application does not implement a server-signed unlock bridge or modify firmware. A Bluetooth connection or handshake alone does not prove button input works; the app reports when valid button packets arrive.

### Experimental left-controller recovery

Under **Setup**, turn on **Experimental left Click recovery** to try keeping the left pod usable without a Zwift unlock. This preference saves locally and is **off by default**. Every 45 seconds after starting a left connection, the app attempts a payload-free `0x18` RESET command on the controller's control characteristic, waits up to two seconds for a reboot disconnect, then closes and reconnects only that pod. Enabling it on an older connection makes the next recovery check due immediately. The right pod continues its normal keep-alive and can still shift with + / B.

This is an independently written experiment, **not BikeControl's private implementation**. The public protocol defines RESET as opcode 24, and BikeControl documents periodic restarts, but the exact command payload and 45-second timing are hypotheses. A successful Bluetooth write or reconnection does not prove that the controller rebooted or its input window was renewed. Diagnostics distinguishes an observed disconnect from a connection cycle without one. An unsupported reset command is logged as a failure and normal reconnect backoff applies.

If the left controller reports **20% battery or less**, experimental recovery turns off and stays off, including after restarting the app. The app shows a notice and retains normal + / B operation on the right. A later higher battery reading does not automatically re-enable resets; check the battery and turn recovery on manually if appropriate. A low last-known reading also prevents enabling recovery until a new reading above 20% arrives. Unknown battery readings do not get treated as zero.

During the initial hardware test, resets caused real left-side disconnects and reconnections, and the user confirmed both controllers responded after idle. The left battery estimate fluctuated from 100% down to 18% and returned to 100% after resting; both Bluetooth battery and Zwift battery messages carried the low values. That establishes fluctuating reported percentages, not measured capacity loss or a measured power budget. The long-term power cost of repeated resets remains unverified.

Expect a gap in left-button input during recovery; its duration depends on Bluetooth and firmware. Presses during that gap are discarded. A paddle held across a scheduled restart must be released before it can shift again. **Disconnect all**, closing the app, or turning the option off stops further scheduled attempts (an already-sent reset cannot be undone). Battery readings remain marked as last during recovery until refreshed.

To evaluate it, first check that − produces input immediately after connecting, enable recovery, and check − after at least three restart cycles. Look for both fresh `minus → I` events and actual MyWhoosh gear changes. If input remains absent, turn recovery off and use + / B, or unlock through Zwift. Initial testing observed a disconnect after RESET and subsequent reconnection. Reliable recovery across firmware versions and its power cost remain unverified.

Initial testing used Click v2 firmware 1.0.1. Both controllers produced button events, + / B changed gears in MyWhoosh, and both controllers responded after an idle test with experimental left recovery enabled. Saved physical packets for all ten Click v2 buttons, release, and a 100% battery report have been replayed successfully through the current decoders and retained as address-free regression fixtures. These fixtures validate wire-format decoding. They do not establish compatibility across firmware versions or long-duration reliability. The faster visual feedback and low-battery recovery cutoff have device-free test coverage; hardware acceptance of those changes is ongoing.

## Logs and settings

Stored locally in `%LOCALAPPDATA%\ClickToWhoosh\` on Windows (Application Support on macOS; XDG state storage on Linux):

- `settings.json`: saved button mappings.
- `preferences.json`: battery alert sound and experimental left recovery preferences.
- `connection.json`: chosen output method, independent network action mappings and a random software-controller identity.
- `diagnostics.log`: connection steps, firmware, raw Bluetooth packets, decoded button presses and input failures. Rotates at 2 MB with two backups.

The visible log is bounded. **Copy log** copies only the visible activity log; the log folder contains detailed packet diagnostics. Logs can include Bluetooth addresses and local paths; review before sharing them.

**Disconnect** cancels discovery and reconnect tasks. Closing the application disconnects the devices. No key presses are replayed after reconnect.
