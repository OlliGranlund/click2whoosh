import React,{useState} from 'react';

export default function MappingProfiles({state,call}) {
  const [name,setName] = useState(''),[selected,setSelected] = useState('');
  return <section className="rounded-xl bg-zinc-50 p-4 mb-5 space-y-3">
    <h3 className="font-medium text-sm">Keyboard profiles</h3>
    <p className="text-xs text-muted">Save short-press keys and hold/long-press behavior together. Loading pauses output and keeps Bluetooth connected. Profiles apply to the MyWhoosh keyboard method.</p>
    <div className="flex flex-wrap gap-3 items-center"><input aria-label="New profile name" value={name} maxLength={40} onChange={e=>setName(e.target.value)} placeholder="e.g. Right Click only" className="rounded-lg border border-border p-2 text-sm"/><button disabled={!name.trim()} className="text-xs text-primary underline" onClick={()=>call('save_profile',name)}>Save current settings</button></div>
    {!!state.profiles?.length&&<div className="flex flex-wrap gap-3 items-center"><select aria-label="Saved keyboard profile" value={selected} onChange={e=>setSelected(e.target.value)} className="rounded-lg border border-border p-2 text-sm"><option value="">Choose profile</option>{state.profiles.map(profile=><option key={profile}>{profile}</option>)}</select><button disabled={!state.profiles.includes(selected)} className="text-xs text-primary underline" onClick={()=>call('load_profile',selected)}>Load profile</button><button disabled={!state.profiles.includes(selected)} className="text-xs text-muted underline" onClick={()=>{call('delete_profile',selected);setSelected('')}}>Delete saved profile</button></div>}
  </section>;
}
