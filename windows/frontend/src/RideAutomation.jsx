import React from 'react';

export default function RideAutomation({state,call}) {
  const settings = state.automation || {};
  const update = (key,value) => call('automation', {auto_focus:!!settings.auto_focus, background_scan:!!settings.background_scan, auto_launch:!!settings.auto_launch, [key]:value});
  return <section className="rounded-xl border border-border p-5 space-y-4">
    <h3 className="font-semibold text-sm">Streamline your ride</h3>
    {[['background_scan','Keep looking for controllers','After Find & connect, repeat scan bursts so controllers woken later can join. Disconnect all stops the search.'],['auto_focus','Bring MyWhoosh forward on a press','Optional: restore and focus the running MyWhoosh window before sending a key. Presses are dropped if Windows does not allow focus.'],['auto_launch','Start MyWhoosh when a controller connects','Choose its executable below. Runs once per connection cycle; existing game windows are left running.']].map(([key,label,description])=><label key={key} className="flex items-start gap-3"><input type="checkbox" aria-label={label} checked={!!settings[key]} disabled={key!=='background_scan'&&state.keyboard_available===false} onChange={e=>update(key,e.target.checked)} className="mt-1 accent-teal-700"/><span><span className="text-sm font-medium">{label}</span><span className="block text-xs text-muted mt-1">{description}</span></span></label>)}
    {state.keyboard_available!==false&&<div className="space-y-2"><p className="text-xs text-muted break-all">{settings.program || 'No MyWhoosh executable selected'}</p><button onClick={()=>call('choose_program')} className="text-xs text-primary underline mr-4">Choose MyWhoosh .exe</button><button disabled={!settings.program} onClick={()=>call('launch_program')} className="text-xs text-primary underline disabled:opacity-50">Open MyWhoosh now</button></div>}
  </section>;
}
