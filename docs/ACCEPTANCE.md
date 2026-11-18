# MyWhoosh release acceptance

Run this against the downloaded executable, not just a development preview. Record the build commit, Windows/MyWhoosh versions, Bluetooth adapter, Click firmware and selected connection method. Leave experimental left recovery off for the initial test. A visible button highlight proves Bluetooth input only; observe the gear change inside a ride separately.

## Keyboard baseline

1. Close other apps connected to the Clicks. Scan and connect the right controller.
2. With output off, press + and B. Both must appear in Diagnostics and the button check; neither should change the game gear.
3. In a MyWhoosh ride with MyShift enabled, verify physical K raises and I lowers the gear.
4. Select Keyboard, enable Send buttons to MyWhoosh, and focus MyWhoosh. Verify ten deliberate + presses and ten B presses change gears in their respective directions. Avoid the gear limits when counting.
5. Focus another app. Controller presses must not type there. Return to MyWhoosh and verify shifting resumes.

## Experimental OpenBikeControl

1. Select OpenBikeControl network. Output must turn off. Pair the advertised ClickToWhoosh controller in MyWhoosh's OpenBikeControl connection screen. Record whether discovery and TCP connection each succeed.
2. Enable output only after pairing. In a ride, verify + raises and B lowers the gear. Record the actual game response, not just the app's connected indicator.
3. Test deliberate taps, a rapid burst, and alternating + / B away from gear limits. Check for missing or extra changes.
4. Turn output off. No further presses should change gears. Turn it on again; earlier presses must not replay.
5. Restart MyWhoosh. Output must turn off when its connection is lost. Pair again and explicitly re-enable output; old shifts must not replay.
6. Switch to Keyboard and back. Only the selected method may send. Verify the two mapping profiles remain independent.
7. If discovery fails, record VPN/network adapters and firewall behavior, then use Restart pairing. Do not disable the firewall globally as a workaround.

## Both controllers and idle behavior

After the right-only baseline, connect the left controller. Record the unlock/recovery method used. Verify minus independently of right B. Leave both idle for at least five minutes, then repeat the button and in-game checks. If experimental recovery is enabled, document its input gaps and reported battery values before and after; battery percentages alone do not measure power consumption.

## Evidence and release decision

For each check record pass, fail or not tested, plus build and reproduction steps. Remove Bluetooth addresses and personal paths before sharing logs. Network mode remains experimental until actual discovery, pairing, shifting and interruption checks pass. Native macOS/Linux unit tests do not establish GUI, Bluetooth or packaging support on those systems.
