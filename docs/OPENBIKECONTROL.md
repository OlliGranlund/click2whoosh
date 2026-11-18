# MyWhoosh connection: keyboard and OpenBikeControl

## Decision

Target **OpenBikeControl mDNS/TCP** as the preferred longer-term integration. Keep the current ride-tested keyboard transport as an explicit fallback until network integration is verified with MyWhoosh. Running both apps on the same computer is supported by the network architecture; it does not require another device.

The Connections tab now selects Keyboard or experimental OpenBikeControl network. The latter starts a real mDNS/TCP endpoint, parses app information incrementally, honors reported action capabilities, and sends standard button transitions. Simulated loopback tests pass; actual MyWhoosh discovery, pairing and gear changes remain to be verified.

## Why the existing toggle exists

Monitoring and button output are separate. Bluetooth input and the visual button check work while output is off. Enabling output allows mapped Windows key taps, only when MyWhoosh is the foreground process. Turning output off leaves controllers connected for diagnostics. The label “MyWhoosh controls” did not explain that distinction.

The interface calls the action **Send buttons to MyWhoosh**. Keyboard mode explains its foreground requirement. Network mode shows waiting/connected/error state and MyWhoosh pairing instructions. Changing modes, mapping network actions or losing the TCP peer pauses output. The two methods never send simultaneously.

## What the open protocol provides

The [OpenBikeControl specification](https://github.com/OpenBikeControl/openbikecontrol-protocol) lists MyWhoosh as implemented. Its [mDNS transport](https://github.com/OpenBikeControl/openbikecontrol-protocol/blob/main/MDNS.md) advertises `_openbikecontrol._tcp.local.` with controller identity and service UUID TXT fields. The trainer app discovers the controller endpoint and opens TCP; button messages carry standard action IDs and pressed/released states. App information can describe the connected trainer app and supported actions. This protocol is MIT licensed, separately from BikeControl's application and private modules.

BikeControl's [MyWhoosh setup](https://bikecontrol.app/use-gamepads-with-mywhoosh/) describes network use on the same computer or another device. In MyWhoosh, the rider enables the OpenBikeControl connection on the pairing screen. MyWhoosh Link is a separate integration; it is not interchangeable with OpenBikeControl.

## Tradeoffs

| | Keyboard fallback | OpenBikeControl mDNS/TCP |
| --- | --- | --- |
| Same-device use | Yes | Yes |
| Foreground / elevation dependencies | Yes | No OS key injection needed |
| Semantic actions | Keys depend on app/screen | Standard shift/navigation action IDs |
| Initial setup | Enable MyShift and output | Discover and pair in MyWhoosh |
| Failure modes | Focus, privileges, key bindings | Discovery, firewall, VPN/network adapters, stale sessions |
| Desktop reuse | Separate input backend per OS | Shared network transport with platform discovery testing |

Network transport changes only the **ClickToWhoosh → MyWhoosh** link. It does not unlock the left Click or remove its BLE restart gaps or uncertain battery behavior.

## Acceptance gates before making network default (not yet default)

- Confirm the current protocol revision and interoperable TCP message framing, including fragmented/coalesced reads. TCP reads do not preserve message boundaries; do not treat each read as one packet.
- Advertise a stable olli.works controller identity and validate same-host discovery on Windows and macOS.
- Pair in MyWhoosh and verify actual up/down gear changes, steering/navigation support and app-reported capability handling.
- Preserve every press/release transition, including rapid taps and simultaneous physical buttons mapped to the same action.
- On disable, BLE loss, TCP loss or transport switching, release active actions and discard queued input. Never replay shifts after reconnect.
- Exercise MyWhoosh restarts, controller sleep/recovery, network interruptions and idle sessions. Show actionable connection state in the UI.
- Keep network exposure intentional, restrict accepted peers appropriately, bound buffers and parsing, and stop advertisements/listeners on shutdown.

Do not present a discovery advertisement or passing simulated socket test as proof that MyWhoosh integration works.

Use the [release acceptance checklist](ACCEPTANCE.md) to record the live pairing, shifting and interruption results against a specific build.

## Current implementation boundaries

On Windows, discovery now registers through installed Apple Bonjour (`dnssd.dll`); it does not bundle Bonjour. Missing Bonjour is reported as a setup error. The TCP listener binds all IPv4 interfaces because Bonjour's machine hostname can resolve to multiple adapters. Use a trusted private network and appropriate firewall rules. Other platforms use Zeroconf on the default-route IPv4 interface. Advertising starts only after network is selected (or a saved network method is restored). Only one trainer-app peer is served; this protocol is not authenticated or encrypted. Incoming messages are bounded and validated. No OS keys are injected in network mode.

Local investigation reproduced a Windows lookup failure for the previous in-process Zeroconf hostname. With native Bonjour registration, OS hostname resolution and a real TCP status read succeeded on the same PC. This fixes a demonstrated discovery compatibility problem, but live MyWhoosh pairing and shifting still need retesting. Use Restart pairing after a network change.

Held steering uses press/release state across devices. Other actions use one immediate press/release pair for every distinct physical press. Haptic commands are consumed but not forwarded to Click hardware. Zero app-reported supported buttons means all, as specified. A TCP connection without app information is shown with unknown identity rather than labelled as confirmed MyWhoosh.
