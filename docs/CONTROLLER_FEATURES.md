# Controller features

These features were informed by [ZwiftBoard](https://github.com/thomaschampagne/zwiftboard), with its MIT notice retained in the app assets. Existing right + / B shifting remains the default. New behavior has software test coverage; live controller/ride acceptance is still required.

## Tap, hold and long press

In **Button mapping**, configure each keyboard button:

- **Tap / long press**, alternate OFF: send the ordinary key immediately on press, once. This is the default; holding a gear button does not repeatedly shift.
- **Tap / long press**, alternate key assigned: a release before the threshold sends the ordinary key; holding to the threshold sends the alternate once, with no ordinary key. The threshold can be 300–2000 ms. This necessarily delays short taps until release.
- **Hold key**: send key down on press, key up on release. Useful for sustained steering. It does not synthesize repeating gear changes. Assign the steering key appropriate to your MyWhoosh version; verify in a ride.

Two physical buttons sharing a held key use reference counts. Disconnecting one source releases only its contribution. Disable, mapping/profile changes and connection-method changes release keys and cancel pending taps. Focus loss cancels pending gestures; old presses are not replayed when focus returns. Rapid taps use separate queued down/up transitions without blocking Bluetooth callbacks. Queued taps are dropped if their controller disconnects or output/focus is lost.

Long-press and held-key configuration currently applies to **Keyboard**. Experimental network mode keeps its separate semantic action mappings and existing held steering behavior.

## Keyboard profiles

Save the current key mappings and gesture settings under a name in **Button mapping**. Loading a profile pauses output without reconnecting Bluetooth. Re-enable output deliberately. These are profiles for MyWhoosh setups, not a claim of support for other training apps.

## Optional left-controller unlock

Under **Setup → Optional left Click unlock**, sign in with your own Zwift account, then reconnect the left Click. This requests a server-signed response to its `FF 03 00` challenge and writes `FF 04 00` followed by that response. Signed-in left sessions use the activation trio; right-only operation retains the working plain RideOn startup.

This is an unofficial integration with Zwift's services and can stop working if their API changes. Right + / B requires no account. Login or a sent reply is not proof the left buttons work: verify minus in the button check, then shifting in MyWhoosh. Experimental restart recovery remains a separate opt-in fallback; leave it off when testing sign-in unlock.

Passwords go directly to Zwift's HTTPS endpoint and are never written to app settings or logs. Access/refresh tokens are encrypted on disk with Windows DPAPI for the current Windows user, in `zwift-session.bin` in the app data folder. No tokens appear in UI snapshots. Removing the saved session deletes the local file and invalidates in-flight results; it does not revoke the token at Zwift. Keep this binary out of shared diagnostics. This feature is currently Windows-only.

Challenge HTTP work runs off the Bluetooth callback. Each session keeps one in-flight solve and only its latest queued challenge, cancels work on teardown, and checks the live connection before writing. Requests have timeouts and response-size limits, reject redirects, and never log credentials, authorization headers or response bodies. An unlock failure does not reset the right pod.

## Ride automation

All options are off by default in **Setup → Streamline your ride**:

- **Keep looking for controllers** repeats scan bursts after **Find & connect** so late-woken controllers can join. **Disconnect all** cancels the search. Bluetooth scan and connect startup operations are serialized; reconnect retries wait for a fresh advertisement.
- **Bring MyWhoosh forward on a press** restores/focuses a matching MyWhoosh process before keyboard output. Windows may refuse focus; such presses are dropped. It does not type into an unrelated app.
- **Start MyWhoosh when a controller connects** launches your explicitly selected MyWhoosh `.exe` once per connection cycle. Existing game windows are detected. A manual **Open MyWhoosh now** action is also available. Store app IDs and scripts are not supported by this launcher.

Saved setup options do not automatically arm button output. The app always starts with output off.
