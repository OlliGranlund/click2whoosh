import React, {useState} from 'react';

export default function ZwiftUnlock({state, call}) {
  const [email,setEmail] = useState(''), [password,setPassword] = useState('');
  const status = state.unlock || {};
  const submit = event => {
    event.preventDefault();
    const credentials = {email,password};
    setPassword('');
    call('zwift_login', credentials);
  };
  return <section className="rounded-xl border border-border p-5 space-y-3">
    <h3 className="text-sm font-semibold">Optional left Click unlock</h3>
    <p className="text-xs text-muted leading-relaxed">Sign in directly to Zwift to request its signed controller-unlock response. This unofficial integration needs internet and may change. Your password is sent to Zwift over HTTPS and is not saved. Session tokens are encrypted for your Windows user. Right + / B works without sign-in.</p>
    <p role="status" className="text-sm">{status.message}{status.ready ? ' · Session available' : ''}</p>
    {!status.ready && <form onSubmit={submit} className="flex flex-wrap gap-2">
      <input aria-label="Zwift email" autoComplete="username" type="email" required value={email} onChange={e=>setEmail(e.target.value)} placeholder="Zwift email" className="border border-border rounded-lg p-2 text-sm"/>
      <input aria-label="Zwift password" autoComplete="off" type="password" required value={password} onChange={e=>setPassword(e.target.value)} placeholder="Zwift password" className="border border-border rounded-lg p-2 text-sm"/>
      <button disabled={status.busy} className="rounded-lg bg-primary text-white px-4 py-2 text-sm disabled:opacity-50">{status.busy ? 'Signing in…' : 'Sign in to Zwift'}</button>
    </form>}
    <button disabled={status.busy} onClick={()=>{setPassword('');call('zwift_forget')}} className="text-xs text-primary underline">Remove saved session</button>
    <p className="text-xs text-muted">After signing in, reconnect the left controller. A sent reply is not proof of unlock: verify − in the button check. Removing the saved session does not revoke tokens at Zwift.</p>
  </section>;
}
