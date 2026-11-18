import React from 'react';

const keys = ['OFF', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', 'SPACE', 'ENTER', 'ESC', 'UP', 'DOWN', 'LEFT', 'RIGHT'];
export default function ButtonBehavior({state, call}) {
  const options = state.gestures || {};
  const update = (button, patch) => call('gestures', {...options, [button]: {...options[button], ...patch}});
  return <section className="mt-6 border-t border-border pt-6">
    <h3 className="font-semibold">Hold and long press</h3>
    <p className="text-sm text-muted mt-2 mb-4">Keyboard mode only. Tap sends immediately by default. With a long-press key, a short tap sends on release; a long press sends only its alternate key once. Hold keeps the mapped key down until release, for steering. Changes pause output.</p>
    <div className="grid sm:grid-cols-2 gap-3">{Object.keys(state.mapping || {}).map(button => {
      const option = options[button] || {};
      return <div key={button} className="rounded-xl border border-border p-4 space-y-3">
        <p className="capitalize font-medium text-sm">{button}</p>
        <label className="flex justify-between text-sm items-center">Behavior<select aria-label={`${button} behavior`} value={option.mode || 'tap'} onChange={e => update(button, {mode:e.target.value})} className="border border-border rounded-lg p-2"><option value="tap">Tap / long press</option><option value="hold">Hold key</option></select></label>
        {option.mode !== 'hold' && <><label className="flex justify-between text-sm items-center">Long-press key<select aria-label={`${button} long press`} value={option.long || 'OFF'} onChange={e => update(button, {long:e.target.value})} className="border border-border rounded-lg p-2">{keys.map(key => <option key={key}>{key}</option>)}</select></label>
        {option.long && option.long !== 'OFF' && <label className="flex justify-between text-sm items-center">Hold duration<select aria-label={`${button} hold duration`} value={option.threshold_ms || 600} onChange={e => update(button, {threshold_ms:Number(e.target.value)})} className="border border-border rounded-lg p-2">{[300,600,1000,1500,2000].map(ms => <option key={ms} value={ms}>{ms} ms</option>)}</select></label>}</>}
      </div>;
    })}</div>
  </section>;
}
