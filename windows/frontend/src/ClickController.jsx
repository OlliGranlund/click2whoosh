import React, { useId } from 'react';

// Original illustration based on the physical Click v2 layout, not a product photograph.
export default function ClickController({ side, held = [] }) {
  const left = side === 'left';
  const id = useId().replaceAll(':', '');
  const active = new Set(held);
  const keys = left
    ? [['up', 110, 62], ['left', 63, 109], ['right', 157, 109], ['down', 110, 156]]
    : [['y', 110, 62, '#089ec2', 'Y'], ['z', 63, 109, '#e46636', 'Z'], ['a', 157, 109, '#56b985', 'A'], ['b', 110, 156, '#c73e9d', 'B']];
  const shift = left ? 'minus' : 'plus';
  return <figure className="m-0 flex min-w-0 flex-col items-center gap-3">
    <svg viewBox="0 0 220 252" className="w-full max-w-[190px] drop-shadow-[0_8px_9px_#18181b18]" role="img"
      aria-label={`Zwift Click v2 ${side} controller${held.length ? `, pressed: ${held.join(', ')}` : ', no buttons pressed'}`}>
      <defs>
        <linearGradient id={`${id}-body`} x1="0" y1="0" x2=".8" y2="1"><stop stopColor="#303638"/><stop offset="1" stopColor="#15191a"/></linearGradient>
        <linearGradient id={`${id}-pad`} x2="0" y2="1"><stop stopColor="#2b3234"/><stop offset="1" stopColor="#202627"/></linearGradient>
        <pattern id={`${id}-grip`} width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1.1" fill="#080c0d"/><circle cx="3" cy="3.5" r=".55" fill="#3b4345"/></pattern>
      </defs>
      {/* Four mounting ears with strap slots. */}
      {[[37, 32, -45], [183, 32, 45], [37, 184, 45], [183, 184, -45]].map(([x, y, angle], i) =>
        <g key={i} transform={`translate(${x} ${y}) rotate(${angle})`}>
          <rect x="-13" y="-22" width="26" height="44" rx="4" fill="#242b2d" stroke="#424a4c"/>
          <rect x="-9" y="-17" width="18" height="9" rx="2" fill="#090d0e" stroke="#4b5355" strokeWidth=".7"/>
          <rect x="-10" y="-3" width="20" height="19" fill={`url(#${id}-grip)`}/>
        </g>)}
      <path d="M110 8 C130 8 143 18 159 34 L193 69 C218 94 218 123 197 148 L163 183 C153 193 150 201 149 218 C148 235 138 243 110 243 C82 243 72 235 71 218 C70 201 67 193 57 183 L23 148 C2 123 2 94 27 69 L61 34 C77 18 90 8 110 8Z"
        fill={`url(#${id}-body)`} stroke="#454e50" strokeWidth="1.5"/>
      <rect x="102" y="31" width="16" height="4" rx="2" fill="#8d9c9f"/>
      <path d="M110 43 C117 43 122 47 127 52 L167 92 C177 102 177 116 167 126 L127 166 C116 177 104 177 93 166 L53 126 C43 116 43 102 53 92 L93 52 C98 47 103 43 110 43Z"
        fill="#0b1011" stroke="#394244" strokeWidth="2"/>
      <path d="M110 49 Q116 49 122 55 L162 95 Q176 109 162 123 L122 163 Q110 175 98 163 L58 123 Q44 109 58 95 L98 55 Q104 49 110 49Z"
        fill={`url(#${id}-pad)`} stroke="#3c4547" strokeWidth="1"/>
      {keys.map(([key, x, y, color, label]) => <g key={key} data-button={key} data-pressed={active.has(key)}>
        {left ? <>
          <circle cx={x} cy={y} r="17" fill={active.has(key) ? '#0f766e' : 'transparent'} stroke={active.has(key) ? '#5eead4' : 'transparent'} strokeWidth="2"/>
          <path d="M-6 3 L0 -3 L6 3" transform={`translate(${x} ${y}) rotate(${{ up: 0, right: 90, down: 180, left: 270 }[key]})`}
            fill="none" stroke="#e4edef" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
        </> : <>
          <circle cx={x} cy={y} r="22" fill="#0a1011" stroke={active.has(key) ? '#5eead4' : '#424b4d'} strokeWidth={active.has(key) ? 3 : 1}/>
          <circle cx={x} cy={y} r="17" fill={color} stroke={active.has(key) ? '#ffffff' : '#ffffff30'} strokeWidth={active.has(key) ? 2 : 1}/>
          <text x={x} y={y + 7} textAnchor="middle" fontFamily="Segoe UI, sans-serif" fontSize="21" fontWeight="800" fill="white">{label}</text>
        </>}
      </g>)}
      <path d="M82 183 Q110 193 138 183 L135 218 Q134 231 110 231 Q86 231 85 218Z" fill={`url(#${id}-grip)`}
        stroke={active.has(shift) ? '#5eead4' : '#313a3c'} strokeWidth={active.has(shift) ? 3 : 1} data-button={shift} data-pressed={active.has(shift)}/>
      <path d={left ? 'M104 209H116' : 'M104 209H116 M110 203V215'} stroke={active.has(shift) ? '#5eead4' : '#e4edef'} strokeWidth="3" strokeLinecap="round"/>
    </svg>
    <figcaption className="text-xs text-muted">{left ? 'Left controller' : 'Right controller'}</figcaption>
  </figure>;
}
