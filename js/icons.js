/**
 * Small inline icon set. Keeping these local means the app works offline and
 * every icon inherits the current text colour.
 */

const PATHS = {
  arrowRight: '<path d="M4 12h15"/><path d="m13 6 6 6-6 6"/>',
  arrowLeft: '<path d="M20 12H5"/><path d="m11 18-6-6 6-6"/>',
  arrowUpRight: '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5 8.5 8.5 0 1 0 20.5 14.6Z"/>',
  sparkles: '<path d="m12 3 1.3 4.2L17.5 8l-4.2 1.3L12 13.5l-1.3-4.2L6.5 8l4.2-.8L12 3Z"/><path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z"/><path d="m5.5 13 .6 1.9 1.9.6-1.9.6L5.5 18l-.6-1.9-1.9-.6 1.9-.6.6-1.9Z"/>',
  lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><path d="M12 14v2"/>',
  check: '<path d="m5 12 4.5 4.5L19 6.5"/>',
  play: '<path d="M8 5.5v13l11-6.5-11-6.5Z"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  stepBack: '<path d="M18 6v12L8 12l10-6Z"/><path d="M6 5v14"/>',
  stepForward: '<path d="M6 6v12l10-6L6 6Z"/><path d="M18 5v14"/>',
  reset: '<path d="M4 10a8 8 0 1 1 2.3 7.2"/><path d="M4 4v6h6"/>',
  zoomIn: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5M10.5 7.5v6M7.5 10.5h6"/>',
  zoomOut: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5M7.5 10.5h6"/>',
  fit: '<path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h9M17 18h3"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="15" cy="18" r="2"/>',
  plug: '<path d="M9 3v5M15 3v5"/><path d="M6 8h12v3a6 6 0 0 1-12 0V8Z"/><path d="M12 17v4"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="m3 3 18 18"/><path d="M10.5 6A9 9 0 0 1 12 5.9c6 0 9.5 6.1 9.5 6.1a17 17 0 0 1-3.3 4.1M6.3 7.8A17 17 0 0 0 2.5 12S6 18.1 12 18.1a9 9 0 0 0 3.5-.7"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  code: '<path d="m8 9-4 3 4 3M16 9l4 3-4 3M13 5l-2 14"/>',
  flow: '<rect x="3" y="3" width="7" height="5" rx="1.2"/><path d="M6.5 8v3.5h11V15"/><path d="M11 11.5V18h5"/><rect x="3" y="16" width="7" height="5" rx="1.2"/><rect x="14" y="16" width="7" height="5" rx="1.2"/>',
  tree: '<rect x="3" y="3" width="7" height="5" rx="1.2"/><rect x="14" y="9" width="7" height="5" rx="1.2"/><rect x="3" y="16" width="7" height="5" rx="1.2"/><path d="M10 5.5h1.5a2 2 0 0 1 2 2V10M10 18.5h1.5a2 2 0 0 0 2-2V14"/>',
  trace: '<circle cx="12" cy="12" r="8.5"/><path d="m10 8.5 6 3.5-6 3.5v-7Z"/>',
  data: '<circle cx="5.5" cy="6" r="2.5"/><circle cx="18.5" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8 6h8M7 8l4 7.5M17 8l-4 7.5"/>',
  warning: '<path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v5M12 17.2v.1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.2v.1"/>',
  book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H7a3 3 0 0 0-3 3V5.5Z"/><path d="M7 16h13"/>',
  keyboard: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M10.3 10h.01M13.7 10h.01M17 10h.01M7 13.5h.01M10.3 13.5h.01M13.7 13.5h.01M17 13.5h.01M8 16.5h8"/>',
  external: '<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M19 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  refresh: '<path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 8.1A7 7 0 0 1 19 9M4.9 15.9A7 7 0 0 0 18 15"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 16 9 5 9-5"/>',
  terminal: '<path d="m5 8 4 4-4 4M12 16h7"/>',
  send: '<path d="m21 3-7.5 18-3.4-7.1L3 10.5 21 3Z"/><path d="M10.1 13.9 21 3"/>',
  server: '<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01"/>',
  cpu: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  home: '<path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  flag: '<path d="M5 21V4"/><path d="M5 4h11l-1.5 4L16 12H5"/>'
};

export function icon(name, size = 18, className = '') {
  const paths = PATHS[name] ?? PATHS.info;
  return `<svg class="icon ${className}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths}</svg>`;
}

export function brandMark(size = 26) {
  return `<svg class="brand-mark" width="${size}" height="${size}" viewBox="0 0 28 28" fill="none" aria-hidden="true" focusable="false">
    <path d="M14 2.2 26 23.3H2L14 2.2Z" fill="currentColor" opacity=".16"/>
    <path d="M14 2.2 26 23.3H14V2.2Z" fill="var(--accent)"/>
    <path d="M14 2.2 2 23.3h12V2.2Z" fill="currentColor"/>
    <path d="M14 2.2v21.1" stroke="var(--surface)" stroke-width="1.2" opacity=".65"/>
  </svg>`;
}

export function spinner(size = 16) {
  return `<svg class="spinner-icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity=".22" stroke-width="2.4"/><path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>`;
}
