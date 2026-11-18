import React from 'react';
import { Keyboard, Radio } from 'lucide-react';

export const NETWORK_ACTION_LABELS = {
  OFF: 'Do nothing', shift_up: 'Shift up', shift_down: 'Shift down',
  up: 'Navigate up', down: 'Navigate down', look_left: 'Look left', look_right: 'Look right',
  confirm: 'Confirm', back: 'Back', menu: 'Open menu', steer_left: 'Steer left',
  steer_right: 'Steer right', emote: 'Emote', screenshot: 'Screenshot', pause: 'Pause', hud_toggle: 'Toggle interface',
};

export default function ConnectionMethod({ state, call, ready, children }) {
  const network = state.connection_method === 'network';
  const Icon = network ? Radio : Keyboard;
  return <section className="rounded-2xl border border-border bg-white p-5 mb-5">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex gap-3 items-center">
        <span className="rounded-xl bg-teal-50 text-primary p-2.5"><Icon size={20}/></span>
        <div><label htmlFor="connection-method" className="text-sm font-semibold">Connection method</label>
          <p className="text-xs text-muted mt-1">How this app sends your buttons to MyWhoosh.</p></div>
      </div>
      <select id="connection-method" className="border border-border rounded-xl bg-zinc-50 p-3 text-sm"
        value={state.connection_method || 'keyboard'} disabled={!ready || state.connection_busy}
        onChange={event => call('connection_method', event.target.value)}>
        <option value="keyboard" disabled={state.keyboard_available === false}>Keyboard · {state.keyboard_available === false ? 'Windows only' : 'recommended'}</option>
        <option value="network">OpenBikeControl network · experimental</option>
      </select>
    </div>
    {network ? <div className="mt-4 rounded-xl bg-teal-50 p-4 text-sm">
      <p className="font-medium" role="status">{state.connection_busy ? 'Starting network pairing…' : state.network?.status || 'Off'}</p>
      <p className="text-xs text-muted mt-2 leading-relaxed">In MyWhoosh, open the connection screen, choose OpenBikeControl, and pair ClickToWhoosh. Both apps can run on this PC. No keyboard focus is needed. Turn on button output after pairing.</p>
      {!state.connection_busy && <p className="text-xs mt-2 leading-relaxed">
        {state.network?.connected
          ? `A trainer app has connected${state.network.app ? ` (${state.network.app})` : '; its identity has not been reported'}. This does not confirm in-game shifting. Enable output and test + / B in a ride.`
          : 'No trainer app is connected. Button presses cannot reach MyWhoosh through network mode yet. Use Keyboard for the working setup.'}
      </p>}
      {state.network?.address && <p className="text-xs text-muted mt-2">Local endpoint: {state.network.address}:{state.network.port}. If MyWhoosh cannot discover it, check that Windows allows this app on your private network and use Restart pairing. Keep the firewall enabled.</p>}
      <div className="flex flex-wrap justify-between gap-2 mt-3 text-xs">
        <span className="text-amber-800">Experimental · reported not working in MyWhoosh. Use Keyboard for riding.</span>
        <button className="text-primary underline" disabled={!ready || state.connection_busy} onClick={() => call('connection_method', 'network')}>{state.network?.status === 'Off' ? 'Start pairing' : 'Restart pairing'}</button>
      </div>
    </div> : <p className="text-xs text-muted mt-4 leading-relaxed">Uses keyboard shortcuts on this PC. Keep MyWhoosh in front while riding. Connect your Clicks, then turn on button output below.</p>}
    <p className="text-xs text-muted mt-3">Changing methods pauses button output. Only the selected method sends controls.</p>
    {children}
  </section>;
}
