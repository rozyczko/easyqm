// Generates the EasyQuantum mock-ups in the EasyApp light theme and renders them with headless Edge.
// Usage: node build.js        (writes ../NN_name.png)
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const OUT = path.resolve(__dirname, '..');
const SCALE = 1.5;

// Font Awesome 5 Free Solid code points (same glyph set EasyApp uses through `fontIcon: "name"`)
const FA = {
  home: 'f015', archive: 'f187', atom: 'f5d2', tasks: 'f0ae', calculator: 'f1ec', 'clipboard-list': 'f46d',
  cog: 'f013', save: 'f0c7', undo: 'f0e2', 'question-circle': 'f059', bug: 'f188',
  'plus-circle': 'f055', upload: 'f093', 'arrow-circle-right': 'f0a9', rocket: 'f135', circle: 'f111',
  'play-circle': 'f144', stop: 'f04d', eye: 'f06e', download: 'f019', 'sync-alt': 'f2f1', 'folder-open': 'f07c',
  search: 'f002', ruler: 'f545', expand: 'f065', 'arrows-alt': 'f0b2', backspace: 'f55a', 'align-left': 'f036',
  comment: 'f075', plus: 'f067', minus: 'f068', 'level-down-alt': 'f3be', 'th-list': 'f00b', 'check-circle': 'f058',
  'project-diagram': 'f542', 'draw-polygon': 'f5ee', tag: 'f02b', 'external-link-alt': 'f35d', 'file-alt': 'f15c',
  'chart-line': 'f201', 'sliders-h': 'f1de', 'external': 'f35d', 'file-export': 'f56e', 'file-code': 'f1c9',
  microchip: 'f2db', 'long-arrow-alt-right': 'f30b', pen: 'f304', cube: 'f1b2', 'table': 'f0ce', 'dot-circle': 'f192',
  'arrow-right': 'f061', 'hourglass-half': 'f252', 'check': 'f00c', 'times': 'f00d', 'minus-square': 'f146',
  'layer-group': 'f5fd', 'angle-right': 'f105', 'play': 'f04b', 'folder': 'f07c', 'chart-bar': 'f080', 'cogs': 'f085',
};
const ic = (n, cls = '') => `<i class="${cls}">&#x${FA[n]};</i>`;
const sub = s => s.replace(/_(\d+)/g, '<sub>$1</sub>');

/* ---------- chrome ---------- */
const STEPS = [
  ['Home', 'home'], ['Project', 'archive'], ['Sample', 'atom'], ['Calculations', 'tasks'], ['Method', 'calculator'], ['Summary', 'clipboard-list'],
];
function appbar(active) {
  const tabs = STEPS.map(([t, ico], i) =>
    `<div class="tab ${i === active ? 'active' : ''}"><span class="ico">${ic(ico)}</span><span class="lbl">${t}</span></div>`).join('');
  return `<div class="appbar">
    <div class="left"><div class="abtn">${ic('save')}</div><div class="abtn">${ic('undo')}</div></div>
    <div class="tabs">${tabs}</div>
    <div class="right"><div class="abtn">${ic('cog')}</div><div class="abtn">${ic('question-circle')}</div><div class="abtn">${ic('bug')}</div></div>
  </div>`;
}
const titlebar = `<div class="titlebar"><div class="ti"></div>EasyQuantum<div class="wc"><span>&#x2014;</span><span>&#x25A1;</span><span>&#x2715;</span></div></div>`;
function status(items) {
  return `<div class="status">${items.map(([ico, k, v]) => `<div class="it">${ic(ico)}<span class="k">${k}</span><span class="v">${v}</span></div>`).join('')}</div>`;
}
const statusItem = {
  project: ['archive', 'Project', 'benzene_b3lyp'],
  sample: ['atom', 'Sample', sub('C_6H_6') + ', 12 atoms'],
  calcs: ['tasks', 'Calculations', '3 selected'],
  engine: ['calculator', 'Engine', 'ORCA 6.0.1'],
  saved: ['save', 'Saved', '11:52'],
};
function page({ active, main, side, sideTabs = ['Basic controls', 'Extra controls'], foot = true, statusItems, height = 1000 }) {
  const bodyH = height - 2 - 31 - 77 - 36; // borders, title bar, app bar, status bar
  const st = sideTabs.map((t, i) => `<div class="t ${i === 0 ? 'on' : ''}">${t}</div>`).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css"></head><body>
  <div class="win" style="height:${height}px">${titlebar}${appbar(active)}
    <div class="body" style="height:${bodyH}px">
      <div class="main">${main}</div>
      <div class="side"><div class="tabbar side-t">${st}</div>${side}${foot ? `<div class="foot"><div class="btn">${ic('arrow-circle-right')}Continue</div></div>` : ''}</div>
    </div>${status(statusItems)}</div></body></html>`;
}

/* ---------- small builders ---------- */
const grp = (title, body, o = {}) => {
  const open = o.open !== false;
  return `<div class="grp ${open ? '' : 'col'}"><div class="gh ${open ? 'open' : ''}"><span class="car">${FA.play ? ic('play') : ''}</span>${o.icon ? `<span class="gi">${ic(o.icon)}</span>` : ''}${title}${o.note ? `<span class="note">${o.note}</span>` : ''}</div>${open ? `<div class="gb">${body}</div>` : ''}</div>`;
};
const row = (l, c, cls = '') => `<div class="row ${cls}"><div class="l">${l}</div><div class="c">${c}</div></div>`;
const inp = (v, o = {}) => `<div class="inp ${o.ro ? 'ro' : ''} ${o.foc ? 'foc' : ''}">${v}${o.unit ? `<span class="u">${o.unit}</span>` : ''}</div>`;
const combo = v => `<div class="inp">${v}<span class="car">&#xf0d7;</span></div>`;
const chk = (on, dis) => `<span class="chk ${on ? 'on' : ''} ${dis ? 'dis' : ''}">${on ? '&#xf00c;' : ''}</span>`;
const chkRow = (l, on) => `<div class="row tight"><div class="c" style="gap:10px">${chk(on)}<span>${l}</span></div></div>`;
const btn = (ico, t, cls = '', ic2 = '') => `<div class="btn ${cls}">${ico ? ic(ico, ic2) : ''}${t}</div>`;
const field = (l, v) => row(l, v);

/* ---------- molecule viewer (SVG) ---------- */
function molecule(w, h) {
  const cx = w / 2, cy = h / 2 - 10, R = 105, RH = 178;
  const ang = k => (-90 + 60 * k) * Math.PI / 180;
  const order = [0, 5, 4, 3, 2, 1]; // C1 top, then counter-clockwise
  const C = [], H = [];
  for (let k = 0; k < 6; k++) {
    const a = ang(k); // k=0 top, clockwise on screen
    C.push([cx + R * Math.cos(a), cy + R * Math.sin(a)]);
    H.push([cx + RH * Math.cos(a), cy + RH * Math.sin(a)]);
  }
  // atom naming: C1 top, C2 upper-left, C3 lower-left, C4 bottom, C5 lower-right, C6 upper-right
  const idx = [0, 5, 4, 3, 2, 1];
  let s = `<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">
    <defs><radialGradient id="bg" cx="50%" cy="46%" r="70%"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#f1f1f1"/></radialGradient></defs>
    <rect width="${w}" height="${h}" fill="url(#bg)"/>`;
  for (let n = 0; n < 6; n++) {
    const a = C[idx[n]], b = C[idx[(n + 1) % 6]];
    const sel = n === 0;
    s += `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${sel ? '#00a3e3' : '#9aa3a8'}" stroke-width="${sel ? 12 : 10}" stroke-linecap="round"/>`;
  }
  for (let n = 0; n < 6; n++) {
    const a = C[idx[n]], h2 = H[idx[n]];
    s += `<line x1="${a[0]}" y1="${a[1]}" x2="${h2[0]}" y2="${h2[1]}" stroke="#c4c9cc" stroke-width="7" stroke-linecap="round"/>`;
  }
  for (let n = 0; n < 6; n++) {
    const a = C[idx[n]], sel = n <= 1;
    s += `<circle cx="${a[0]}" cy="${a[1]}" r="26" fill="${sel ? '#2b7a96' : '#5d6468'}" stroke="${sel ? '#00a3e3' : 'none'}" stroke-width="3"/>
      <text x="${a[0]}" y="${a[1] + 5}" text-anchor="middle" font-size="14" font-weight="bold" style="fill:#fff">C${n + 1}</text>`;
  }
  for (let n = 0; n < 6; n++) {
    const a = H[idx[n]];
    s += `<circle cx="${a[0]}" cy="${a[1]}" r="17" fill="#f4f4f4" stroke="#b5bbbf" stroke-width="2"/>
      <text x="${a[0]}" y="${a[1] + 4}" text-anchor="middle" font-size="12" style="fill:#666">H${n + 7}</text>`;
  }
  // measurement label on C1-C2
  const m = [(C[idx[0]][0] + C[idx[1]][0]) / 2, (C[idx[0]][1] + C[idx[1]][1]) / 2];
  s += `<g><rect x="${m[0] - 96}" y="${m[1] - 44}" width="86" height="26" rx="2" fill="#fff" stroke="#d6d6d6"/><text x="${m[0] - 53}" y="${m[1] - 26}" text-anchor="middle" font-size="14" style="fill:#00a3e3;font-weight:bold">1.3915 &#197;</text></g>`;
  // axes gizmo
  const gx = 60, gy = h - 70;
  s += `<line x1="${gx}" y1="${gy}" x2="${gx + 52}" y2="${gy}" stroke="#F44336" stroke-width="2"/><text x="${gx + 58}" y="${gy + 4}" font-size="13" style="fill:#F44336">x</text>
    <line x1="${gx}" y1="${gy}" x2="${gx}" y2="${gy - 52}" stroke="#4CAF50" stroke-width="2"/><text x="${gx - 4}" y="${gy - 58}" font-size="13" style="fill:#4CAF50">y</text>
    <line x1="${gx}" y1="${gy}" x2="${gx - 30}" y2="${gy + 30}" stroke="#03A9F4" stroke-width="2"/><text x="${gx - 42}" y="${gy + 42}" font-size="13" style="fill:#03A9F4">z</text>`;
  return s + '</svg>';
}

/* ---------- IR spectrum (SVG, EasyApp chart colours) ---------- */
function irChart(w, h) {
  const L = 54, R = 16, T = 14, B = 52, pw = w - L - R, ph = h - T - B;
  const X = v => L + (v - 400) / (3700 - 400) * pw, Y = v => T + ph - v / 100 * ph;
  let s = `<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg"><rect width="${w}" height="${h}" fill="#fff"/>`;
  for (let v = 0; v <= 100; v += 25) s += `<line x1="${L}" x2="${w - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#eee"/><text x="${L - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="12.5">${v}</text>`;
  for (let v = 500; v <= 3500; v += 500) s += `<line y1="${T}" y2="${T + ph}" x1="${X(v)}" x2="${X(v)}" stroke="#eee"/><text x="${X(v)}" y="${T + ph + 18}" text-anchor="middle" font-size="12.5">${v}</text>`;
  s += `<line x1="${L}" x2="${L}" y1="${T}" y2="${T + ph}" stroke="#ddd"/><line x1="${L}" x2="${w - R}" y1="${T + ph}" y2="${T + ph}" stroke="#ddd"/>`;
  const sticks = [[673, 98], [850, 3], [1035, 5], [1178, 12], [1480, 6], [1530, 2], [3040, 9], [3062, 46], [3070, 38], [3085, 6]];
  for (const [x, y] of sticks) s += `<line x1="${X(x)}" x2="${X(x)}" y1="${Y(0)}" y2="${Y(y)}" stroke="coral" stroke-width="2"/>`;
  s += `<text x="${w / 2 + 20}" y="${h - 10}" text-anchor="middle" font-size="13.5">Wavenumber (cm&#8315;&#185;)</text>`;
  s += `<text transform="translate(14 ${T + ph / 2}) rotate(-90)" text-anchor="middle" font-size="13.5">IR intensity (rel. %)</text>`;
  // hover tooltip like EasyApp charts
  s += `<g><rect x="${X(673) + 12}" y="${Y(98) + 2}" width="106" height="44" rx="2" fill="#fff" stroke="#d6d6d6"/><text x="${X(673) + 22}" y="${Y(98) + 20}" font-size="12.5">&#957; 673 cm&#8315;&#185;</text><text x="${X(673) + 22}" y="${Y(98) + 37}" font-size="12.5" style="fill:#888">C-H wag &#183; A&#8322;u</text></g>`;
  return s + '</svg>';
}

/* =====================================================================
   01 Project
   ===================================================================== */
function projectPage() {
  const rows = [
    ['benzene_b3lyp', 'C_6H_6', 'ORCA', 'SPE, Opt, Freq', ['green', 'Completed'], 'today 11:52', true],
    ['water_dimer_mp2', '(H_2O)_2', 'PSI4', 'Opt, Freq', ['blue', 'Running'], 'today 10:30'],
    ['si_bulk_pbe', 'Si (Fd-3m)', 'CASTEP', 'SPE, Band structure', ['orange', 'Engine not found'], 'yesterday'],
    ['azobenzene_tddft', 'C_12H_10N_2', 'ORCA', 'Opt, Excited states', ['green', 'Completed'], '2026-10-21'],
    ['caffeine_test', 'C_8H_10N_4O_2', 'PSI4', 'SPE', ['red', 'Failed (SCF)'], '2026-10-19'],
  ].map(r => `<tr class="${r[6] ? 'sel' : ''}"><td>${r[0]}</td><td>${sub(r[1])}</td><td>${r[2]}</td><td>${r[3]}</td><td><span class="pill ${r[4][0]}">${r[4][1]}</span></td><td class="minor">${r[5]}</td></tr>`).join('');
  const main = `<div style="padding:21px 31px 0">
    <div class="title-xl">benzene_b3lyp</div>
    <div class="kv" style="margin-top:21px">
      <b>Description:</b><span>Benzene optimisation + frequencies, B3LYP-D3/def2-TZVP, ORCA</span>
      <b>Location:</b><span class="mono">~/projects/benzene_b3lyp/</span>
      <b>Created:</b><span>2026-10-28 09:14</span>
      <b>Last modified:</b><span>2026-10-28 11:52</span>
      <b>Sample:</b><span>${sub('C_6H_6')} &#183; 12 atoms &#183; molecular (non-periodic)</span>
      <b>Calculations:</b><span>Single point &#183; Geometry optimisation &#183; Frequencies</span>
      <b>Engine:</b><span>ORCA 6.0.1 (local)</span>
      <b>Status:</b><span><span class="pill green">Completed</span></span>
    </div></div>
    <div style="padding:28px 31px 0">
      <div class="sh" style="padding:0;height:35px">${ic('circle', '')}<span>Recent projects</span></div>
      <table class="tbl" style="margin-top:6px"><thead><tr><th>Name</th><th>Sample</th><th>Engine</th><th>Calculations</th><th>Status</th><th>Modified</th></tr></thead><tbody>${rows}</tbody></table>
    </div>`;
  const side = grp('Get started', `<div class="btnrow">${btn('plus-circle', 'Create a new project', 'half')}${btn('upload', 'Open an existing project', 'half')}</div>
      <div class="hint">Without a project, results are kept in a temporary folder and can be saved later (Continue).</div>`, { icon: 'rocket' })
    + grp('Project details', field('Name:', inp('benzene_b3lyp')) + field('Description:', inp('Benzene optimisation + ...'))
      + field('Location:', inp('~/projects/benzene_b3lyp')) + `<div class="row"><div class="c" style="gap:10px">${chk(true)}<span>Auto-save</span></div></div>`, { icon: 'pen' })
    + grp('Examples', `<table class="tbl"><tbody>${[['Water molecule (H_2O)', 'xyz'], ['Benzene (C_6H_6)', 'xyz'], ['Silicon bulk', 'cif &#183; periodic'], ['NaCl rock salt', 'cif &#183; periodic']].map(r => `<tr><td>${sub(r[0])}</td><td class="minor">${r[1]}</td></tr>`).join('')}</tbody></table>`, { icon: 'layer-group' });
  return page({ active: 1, main, side, sideTabs: ['Basic controls'], statusItems: [statusItem.project, statusItem.sample, statusItem.engine, statusItem.saved] });
}

/* =====================================================================
   02 Sample
   ===================================================================== */
function samplePage() {
  const atoms = [
    ['C1', 'C', '0.0000', '1.3915', '0.0000'], ['C2', 'C', '1.2051', '0.6958', '0.0000'], ['C3', 'C', '1.2051', '-0.6958', '0.0000'],
    ['C4', 'C', '0.0000', '-1.3915', '0.0000'],
  ].map((a, i) => `<tr class="${i < 2 ? 'sel' : ''}"><td class="n">${i + 1}</td><td>${a[0]}</td><td>${a[1]}</td><td class="r">${a[2]}</td><td class="r">${a[3]}</td><td class="r">${a[4]}</td><td class="c">${chk(false)}</td></tr>`).join('');
  const tools = `<div class="toolbar" style="position:absolute;top:56px;right:21px;z-index:2">
      <div class="tool on" title="Ball and stick">${ic('project-diagram')}</div><div class="tool">${ic('draw-polygon')}</div><div class="tool">${ic('circle')}</div><div class="gap"></div>
      <div class="tool on">${ic('tag')}</div><div class="tool on">${ic('ruler')}</div><div class="gap"></div>
      <div class="tool">${ic('arrows-alt')}</div><div class="tool">${ic('expand')}</div><div class="tool">${ic('backspace')}</div></div>`;
  const main = `<div class="tabbar"><div class="t on">Viewer</div><div class="t">Atoms</div><div class="t">Bonds</div><div class="t">Cell</div></div>
    <div style="position:relative;flex:1">${tools}${molecule(1015, 857 - 43 - 36)}
      <div style="position:absolute;left:0;right:0;bottom:0;height:36px;background:rgba(255,255,255,.9);border-top:1px solid #eee;display:flex;align-items:center;padding:0 21px;gap:36px;color:#777">
        <span>Selected: <b style="color:#333">C1&#8211;C2</b></span><span>Distance: <b style="color:#333">1.3915 &#197;</b></span><span style="margin-left:auto">Rotate: drag &#183; Zoom: wheel &#183; Pan: right-drag</span></div></div>`;
  const side = grp('Structure', `<div style="margin-bottom:8px">${btn('upload', 'Load structure from file...', 'wide')}</div>
      ${field('Source:', inp('benzene.xyz &#183; ' + sub('C_6H_6') + ' &#183; 12 atoms', { ro: true }))}
      <div class="row"><div class="c" style="gap:10px">${chk(false)}<span>Periodic</span><span style="color:#aaa">molecule</span></div></div>`, { icon: 'atom' })
    + grp('Atoms', `<table class="tbl"><thead><tr><th class="n"></th><th>Label</th><th>El.</th><th class="r">x (&#197;)</th><th class="r">y (&#197;)</th><th class="r">z (&#197;)</th><th class="c">Fix</th></tr></thead><tbody>${atoms}</tbody></table>
      <div class="btnrow" style="margin:8px 0 0;gap:8px">${btn('plus', 'Add atom', 'sm')}${btn('minus', 'Remove', 'sm')}<span style="margin-left:auto;align-self:center;color:#aaa">12 atoms &#183; Cartesian &#183; &#197;</span></div>`, { icon: 'th-list' })
    + grp('Electronic state', field('Charge:', inp('0')) + field('Multiplicity:', combo('1 (singlet)')), { icon: 'sliders-h', note: 'D6h (detected)' })
    + grp('Unit cell', '', { open: false, icon: 'cube', note: 'disabled' })
    + grp('Display', '', { open: false, icon: 'eye' });
  return page({ active: 2, main, side, statusItems: [statusItem.project, statusItem.sample, statusItem.engine, statusItem.saved] });
}

/* =====================================================================
   03 Calculations
   ===================================================================== */
function calcPage() {
  const R = (on, dis, name, desc, res, note) => `<tr class="${on ? 'sel' : ''} ${dis ? 'dim' : ''}"><td class="c" style="width:44px">${chk(on, dis)}</td><td style="width:170px"><b>${name}</b></td><td class="minor" style="width:270px">${desc}</td><td style="width:250px">${res}</td><td>${note}</td></tr>`;
  const tag = t => `<span class="pill tag">${t}</span>`;
  const table = `<table class="tbl tall"><thead><tr><th></th><th>Calculation</th><th>Description</th><th>Main results</th><th>Requires / notes</th></tr></thead><tbody>
    ${R(1, 0, 'Single point energy', 'Total electronic energy at the given geometry', 'E<sub>total</sub>, orbital energies, HOMO&#8211;LUMO gap, dipole', '&#8212;')}
    ${R(1, 0, 'Geometry optimisation', 'Relax atomic positions (and cell for periodic systems) to a minimum', 'Optimised structure, E<sub>final</sub>, convergence trace', '&#8212;')}
    ${R(1, 0, 'Vibrational frequencies', 'Harmonic frequencies, IR intensities, thermochemistry', '&#957;<sub>i</sub>, IR/Raman intensities, ZPE, G(T), imaginary modes', 'Runs after optimisation')}
    ${R(0, 0, 'Excited states (TD-DFT)', 'Vertical excitation energies and oscillator strengths', 'E<sub>exc</sub>, f, UV-Vis spectrum', 'ORCA, PSI4 only')}
    ${R(0, 0, 'Electronic properties', 'Population analysis and multipoles', 'Mulliken / L&#246;wdin / Hirshfeld charges, dipole, quadrupole', '&#8212;')}
    ${R(0, 0, 'NMR shielding', 'GIAO chemical shielding tensors', '&#963;<sub>iso</sub> per atom, relative shifts', 'ORCA, CASTEP')}
    ${R(0, 0, 'Transition state search', 'Locate a saddle point from a guess structure', 'TS geometry, imaginary mode, barrier', 'ORCA only &#183; needs 1 imaginary frequency check')}
    ${R(0, 1, 'Band structure / DOS', 'Electronic bands along a k-path and density of states', 'E(k), DOS, band gap', tag('Periodic systems only'))}
    ${R(0, 1, 'Phonons', 'Lattice dynamics at &#915; or on a q-grid', 'Phonon frequencies, DOS', tag('Periodic &#183; CASTEP only'))}
    </tbody></table>`;
  const step = (cls, t) => `<span class="pill ${cls}" style="height:30px;padding:0 14px"><span>${t}</span></span>`;
  const arrow = `<span style="color:#aaa;font:14px 'FA'">&#xf061;</span>`;
  const main = `<div style="padding:0 21px">
      <div class="sh" style="padding:0"><span class="car">&#xf04b;</span><span>Calculations to perform</span><span class="note">3 selected &#183; estimated cost ~4 min on 8 cores (ORCA, B3LYP-D3/def2-TZVP)</span></div>
      ${table}
    </div>
    <div style="padding:0 21px;margin-top:21px">
      <div class="sh" style="padding:0"><span class="car">&#xf04b;</span><span>Resulting workflow</span></div>
      <div style="display:flex;align-items:center;gap:12px;margin-top:6px;padding:11px 14px;border:1px solid var(--combo-border);background:var(--content)">
        ${step('blue', 'Structure (' + sub('C_6H_6') + ')')}${arrow}${step('green', '1 &#183; Geometry optimisation')}${arrow}${step('green', '2 &#183; Single point energy (at optimised geometry)')}${arrow}${step('green', '3 &#183; Vibrational frequencies')}
      </div>
      <div class="hint" style="margin-top:8px">Order is resolved automatically from dependencies; drag to override.</div>
    </div>`;
  const side = grp('Geometry optimisation', field('Convergence:', combo('Tight')) + field('Max. steps:', inp('100')) + field('Optimise:', combo('Positions only')) + field('Constraints:', combo('None (0 frozen)')) + `<div class="row"><div class="c" style="gap:10px">${chk(true)}<span>Keep trajectory</span></div></div>`, { icon: 'level-down-alt', note: 'selected' })
    + grp('Vibrational frequencies', field('Type:', combo('Analytical (if available)')) + field('Temperature:', inp('298.15', { unit: 'K' })) + field('Pressure:', inp('1.0', { unit: 'atm' })) + `<div class="row"><div class="c" style="gap:10px">${chk(false)}<span>Raman intensities</span></div></div>`, { icon: 'chart-bar', note: 'selected' })
    + grp('Single point energy', `<div class="row"><div class="c" style="gap:10px">${chk(true)}<span>Print orbitals</span></div></div>` + field('Geometry:', combo('Use optimised')), { icon: 'dot-circle', note: 'selected' })
    + grp('Excited states (TD-DFT)', '', { open: false, icon: 'atom', note: 'off' })
    + grp('Electronic properties', '', { open: false, icon: 'atom', note: 'off' });
  return page({ active: 3, main, side, statusItems: [statusItem.project, statusItem.sample, statusItem.calcs, statusItem.saved] });
}

/* =====================================================================
   04 Method
   ===================================================================== */
function methodPage() {
  const card = (name, st, ver, path, o = {}) => `<div style="flex:1;border:${o.sel ? '1px solid var(--accent)' : '1px solid var(--combo-border)'};border-radius:2px;background:${o.sel ? 'var(--row-hover)' : '#fff'};padding:12px 14px;${o.dis ? 'opacity:.9' : ''}">
      <div style="display:flex;align-items:center"><b style="font-size:15px">${name}</b><span class="pill ${st[0]}" style="margin-left:auto">${st[1]}</span></div>
      <div style="color:#666;margin-top:6px">${ver}</div><div class="mono" style="color:#999;font-size:12.5px;margin-top:3px">${path}</div></div>`;
  const log = `                         * O   R   C   A *
                  Program Version 6.0.1 - RELEASE
------------------------------------------------------------------------
| 1> ! B3LYP D3BJ def2-TZVP def2/J RIJCOSX TightSCF Opt Freq
| 2> %pal nprocs 8 end
| 3> * xyzfile 0 1 structure.xyz
------------------------------------------------------------------------
                       ****************************
                       * Geometry Optimization Run *
                       ****************************
Geometry convergence criteria ..... TIGHT

                 ***  Starting incremental Fock matrix formation  ***
ITER       Energy         Delta-E        Max-DP      RMS-DP      [F,P]     Damp
  0   -232.1894273031   0.000000000000 0.00342118  0.00008121  0.0251389 0.7000
  1   -232.2097105118  -0.020283208695 0.00185422  0.00005081  0.0119874 0.7000
  5   -232.2503771960  -0.000001244731 0.00000917  0.00000041  0.0000410 0.0000
               **** Energy Check signals convergence ****
FINAL SINGLE POINT ENERGY      -232.250377198640
                 -------------------------------------------
                 |     GEOMETRY OPTIMIZATION CYCLE   4     |
                 -------------------------------------------
         Energy change      -0.0000061240      0.0000010000      NO
         RMS gradient        0.0000098421      0.0000300000      YES
         MAX gradient        0.0000273110      0.0001000000      YES
         RMS step            0.0001102938      0.0006000000      YES
         MAX step            0.0003311421      0.0010000000      YES`;
  const main = `<div style="padding:0 21px">
      <div class="sh" style="padding:0"><span class="car">&#xf04b;</span><span>Engine</span>
        <span style="margin-left:auto;display:flex;gap:8px">${btn('sync-alt', 'Re-detect', 'sm')}${btn('cog', 'Configure paths...', 'sm')}</span></div>
      <div style="display:flex;gap:14px">
        ${card('ORCA', ['green', 'Found'], 'Version 6.0.1 &#183; MPI (OpenMPI 4.1)', '/opt/orca/6.0.1/orca', { sel: true })}
        ${card('PSI4', ['green', 'Found'], 'Version 1.9.1 &#183; conda env &#8220;psi4&#8221;', '~/miniconda3/envs/psi4/bin/psi4')}
        ${card('CASTEP', ['orange', 'Not found'], 'Not detected &#183; periodic systems only', 'castep.mpi &#8212; set path in Configure', { dis: true })}
      </div></div>
    <div style="padding:0 21px;margin-top:14px;flex:1;display:flex;flex-direction:column">
      <div class="sh" style="padding:0"><span class="car">&#xf04b;</span><span>Run</span>
        <span style="margin-left:auto;display:flex;gap:8px">${btn('eye', 'Preview input', 'sm')}${btn('download', 'Save inputs', 'sm')}</span></div>
      <div style="display:flex;align-items:center;gap:12px;margin-top:2px">
        <div class="seg"><span class="on">Run locally</span><span class="dis">Remote / cluster (later)</span></div>
        <span style="color:#888">Cores:</span><div style="width:110px">${inp('8')}</div>
        <span style="color:#888">Memory:</span><div style="width:140px">${inp('16', { unit: 'GB' })}</div>
        <span style="margin-left:auto;display:flex;gap:8px">${btn('play-circle', 'Run workflow', 'sm', 'ic-green')}${btn('stop', 'Stop', 'sm', 'ic-red')}</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin:12px 0">
        <span class="pill green">1 Optimisation</span>${`<span style="color:#aaa;font:13px 'FA'">&#xf061;</span>`}<span class="pill blue">2 Single point</span>${`<span style="color:#aaa;font:13px 'FA'">&#xf061;</span>`}<span class="pill grey">3 Frequencies</span>
        <div style="flex:1;height:4px;background:var(--app-border);border-radius:2px;margin-left:10px"><div style="width:48%;height:100%;background:var(--accent);border-radius:2px"></div></div>
        <span style="color:#777">48 % &#183; 1 min 52 s</span></div>
      <div class="log" style="flex:1;margin-bottom:21px">${log.replace(/&/g, '&amp;').replace(/</g, '&lt;')}<div style="position:absolute;top:8px;right:10px;display:flex;gap:6px;font-family:'PT Sans'"><span class="pill grey" style="background:var(--bg)">orca.out</span><span class="pill grey" style="background:var(--bg)">follow ${ic('check')}</span></div></div>
    </div>`;
  const side = grp('Level of theory', field('Method:', combo('DFT')) + field('Functional:', combo('B3LYP')) + field('Dispersion:', combo('D3(BJ)')) + field('Basis set:', combo('def2-TZVP')) + field('Auxiliary basis:', combo('def2/J (RIJCOSX)')), { icon: 'atom' })
    + grp('System', field('Charge:', inp('0', { ro: true })) + field('Multiplicity:', inp('1', { ro: true })) + field('Reference:', combo('RKS (closed shell)')) + field('Solvation:', combo('None')), { icon: 'sliders-h' })
    + grp('SCF', field('Convergence:', combo('Tight (1e-8 Eh)')) + field('Max. iterations:', inp('125')) + field('Integration grid:', combo('DefGrid2')) + `<div class="row"><div class="c" style="gap:10px">${chk(false)}<span>Stability check</span></div></div>`, { icon: 'cogs' })
    + grp('Engine-specific (ORCA)', '', { open: false, icon: 'file-code', note: 'extra controls' });
  return page({ active: 4, main, side, foot: false, statusItems: [statusItem.project, statusItem.engine, ['play-circle', 'Job', 'running &#8212; step 2/3'], ['microchip', 'PID', '48213 &#183; 8 threads &#183; 3.1 GB']] });
}

/* =====================================================================
   05 Summary
   ===================================================================== */
function summaryPage() {
  const tile = (l, v, sub2, accent) => `<div style="flex:1;border:1px solid var(--combo-border);background:var(--content);border-radius:2px;padding:10px 12px;min-width:0">
      <div style="color:#888;font-size:13px;white-space:nowrap">${l}</div>
      <div style="font:200 26px/1.25 'Encode Sans';color:${accent || '#333'};margin:2px 0;white-space:nowrap">${v}</div>
      <div style="color:#999;font-size:12.5px;line-height:1.25">${sub2}</div></div>`;
  const b = [['C1&#8211;C2', '1.3915', '1.3929', '+0.0014', 'C1&#8211;C2&#8211;C3', '120.00'], ['C2&#8211;C3', '1.3915', '1.3929', '+0.0014', 'C2&#8211;C3&#8211;C4', '120.00'], ['C1&#8211;H7', '1.0800', '1.0831', '+0.0031', 'H7&#8211;C1&#8211;C2', '120.00']]
    .map(r => `<tr>${r.map((c, i) => `<td class="${i === 0 || i === 4 ? '' : 'r'}" ${i === 5 ? 'style="text-align:right"' : ''}>${c}</td>`).join('')}</tr>`).join('');
  const main = `<div class="tabbar"><div class="t on">Results</div><div class="t">Report</div><div class="t">orca.out</div><div class="t">orca.xyz</div><div class="t">orca.hess</div></div>
    <div style="padding:14px 21px 0;display:flex;gap:10px">
      ${tile('Final energy (Eh)', '&#8722;232.250377', 'B3LYP-D3(BJ)/def2-TZVP')}
      ${tile('Optimisation', 'Converged', '12 steps &#183; &#916;E = &#8722;2.14 kcal/mol', '#55832a')}
      ${tile('Imaginary modes', '0', 'true minimum &#183; ZPE 61.9 kcal/mol')}
      ${tile('HOMO&#8211;LUMO gap (eV)', '6.72', 'HOMO &#8722;6.85 &#183; LUMO &#8722;0.13')}
      ${tile('Dipole moment (D)', '0.000', 'D6h symmetry preserved')}
      ${tile('Gibbs free energy (Eh)', '&#8722;232.187', '298.15 K, 1 atm')}
    </div>
    <div style="display:flex;gap:21px;padding:0 21px;margin-top:6px">
      <div style="width:470px;flex:none">
        <div class="sh" style="padding:0"><span class="car">&#xf04b;</span><span>Geometry optimisation</span><span class="note">initial &#8594; final</span></div>
        <table class="tbl"><thead><tr><th>Bond</th><th class="r">Initial (&#197;)</th><th class="r">Final (&#197;)</th><th class="r">&#916; (&#197;)</th><th>Angle</th><th class="r">Final (&#176;)</th></tr></thead><tbody>${b}</tbody></table>
        <div class="hint" style="margin-top:8px">&#8230; 15 more rows &#183; <span style="color:var(--accent)">show all</span> &#183; <span style="color:var(--accent)">open final structure in viewer</span></div>
        <div class="sh" style="padding:0;margin-top:14px"><span class="car">&#xf04b;</span><span>Convergence</span></div>
        <table class="tbl"><thead><tr><th>Criterion</th><th class="r">Value</th><th class="r">Tolerance</th><th class="c">Met</th></tr></thead><tbody>
          <tr><td>Energy change</td><td class="r">&#8722;6.12e-6</td><td class="r">1.0e-6</td><td class="c" style="color:var(--green)">&#10003;</td></tr>
          <tr><td>RMS gradient</td><td class="r">9.84e-6</td><td class="r">3.0e-5</td><td class="c" style="color:var(--green)">&#10003;</td></tr>
          <tr><td>MAX step</td><td class="r">3.31e-4</td><td class="r">1.0e-3</td><td class="c" style="color:var(--green)">&#10003;</td></tr></tbody></table>
      </div>
      <div style="flex:1;min-width:0">
        <div class="sh" style="padding:0"><span class="car">&#xf04b;</span><span>Vibrational frequencies</span>
          <span class="note"><div class="seg" style="color:#333"><span class="on">IR spectrum</span><span>Table (30 modes)</span></div></span></div>
        <div class="chartwrap">${irChart(450, 400)}</div>
        <div style="display:flex;align-items:center;gap:12px;margin-top:6px"><span class="hint" style="margin:0;flex:1">Hover a bar for mode number, symmetry and intensity.</span>${btn('play', 'Animate selected mode', 'sm')}</div>
      </div>
    </div>`;
  const side = grp('Results', ['Energies', 'Optimised geometry', 'Frequencies'].map(t => chkRow(t, true)).join('') + ['Orbitals', 'Charges'].map(t => chkRow(t, false)).join(''), { icon: 'check-circle' })
    + grp('Units', field('Energy:', combo('Hartree (Eh)')) + field('Length:', combo('&#197;')) + field('Frequency:', combo('cm&#8315;&#185;')), { icon: 'ruler' })
    + grp('Export', `${btn('file-export', 'Export report (HTML)', 'wide')}<div style="height:8px"></div>${btn('file-export', 'Export report (PDF)', 'wide')}<div style="height:8px"></div>${btn('download', 'Final structure (xyz / cif)', 'wide')}<div style="height:8px"></div>${btn('download', 'Results as JSON / CSV', 'wide')}`, { icon: 'download' })
    + grp('Job', `<div class="kv" style="grid-template-columns:168px 1fr;row-gap:6px"><span>Engine:</span><span>ORCA 6.0.1</span><span>Wall time:</span><span>3 min 41 s &#183; 8 cores</span><span>Finished:</span><span>2026-10-28 11:52</span><span>Folder:</span><span class="mono" style="font-size:12.5px">~/projects/benzene_b3lyp/run_001/</span></div>`, { icon: 'microchip' });
  return page({ active: 5, main, side, foot: false, statusItems: [statusItem.project, statusItem.engine, ['check-circle', 'Job', 'completed'], ['th-list', 'Results', '3 / 3 calculations parsed']] });
}

/* =====================================================================
   00 Workflow (overview in the same look)
   ===================================================================== */
function workflowPage() {
  const H = 770;
  const stepBox = (i, t, ico, bullets, prod) => `<div style="flex:1;border:1px solid var(--combo-border);background:var(--content);border-radius:2px;padding:14px 16px;display:flex;flex-direction:column;min-height:262px">
      <div style="display:flex;align-items:center;gap:10px;color:var(--accent);font-size:17px"><span style="font:20px 'FA'">${ic(ico)}</span><b>${i} &#183; ${t}</b></div>
      <ul style="margin:12px 0 0;padding-left:18px;line-height:1.5">${bullets.map(x => `<li>${x}</li>`).join('')}</ul>
      <div style="margin-top:auto;border-top:1px dashed #ccc;padding-top:9px;color:#777"><b style="color:var(--accent)">produces</b> ${prod}</div></div>`;
  const arrow = `<div style="align-self:center;color:#aaa;font:18px 'FA'">&#xf061;</div>`;
  const lay = (t, d) => `<div style="flex:1;border:1px solid var(--combo-border);border-radius:2px;padding:14px 16px"><div style="color:var(--accent);font-weight:bold;font-size:15px">${t}</div><div style="margin-top:6px;line-height:1.5;color:#555">${d}</div></div>`;
  const main = `<div style="padding:28px 31px 0"><div class="title-xl">EasyQuantum</div><div style="color:#666;margin-top:6px;font-size:15px">The standard EasyApp five-step workflow, with Experiment &#8594; Calculations and Analysis &#8594; Method.</div></div>
    <div style="display:flex;gap:10px;padding:28px 31px 0">
      ${stepBox(1, 'Project', 'archive', ['Create / open / skip', 'Name, description, folder', 'Recent projects'], 'project.json')}${arrow}
      ${stepBox(2, 'Sample', 'atom', ['Load xyz / cif / car / coord / pdb', '3D viewer', 'Atoms, bonds, cell tables (editable)'], 'Structure (atoms, cell, charge, multiplicity)')}${arrow}
      ${stepBox(3, 'Calculations', 'tasks', ['Tick tasks: SPE, Opt, Freq, TD-DFT &#8230;', 'Per-task options', 'Auto-ordered workflow'], 'Task list')}${arrow}
      ${stepBox(4, 'Method', 'calculator', ['Engine: ORCA / PSI4 / CASTEP', 'Theory level, basis, settings', 'Run locally, live log'], 'Input files, raw output')}${arrow}
      ${stepBox(5, 'Summary', 'clipboard-list', ['Headline results', 'Tables and spectra', 'Raw output viewer, report export'], 'results.json, report.html')}
    </div>
    <div style="display:flex;gap:14px;padding:21px 31px 0">
      ${lay('GUI layer (QML / EasyApp)', 'Page per step, right-hand sidebar with Basic / Extra control groups, shared 3D viewer component, editable table component.')}
      ${lay('Logic layer (Python)', 'Project, Structure, TaskList, Method, JobRunner and Results objects exposed to QML via QObject proxies. No engine-specific code here.')}
      ${lay('Engine adapters', 'One adapter per code: writes input, launches the executable, parses output into a common Results schema. ORCA, PSI4, CASTEP first; interface open for others.')}
    </div>`;
  const bodyH = H - 2 - 31 - 77 - 36;
  return `<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css"></head><body>
  <div class="win" style="height:${H}px">${titlebar}${appbar(0)}<div class="body" style="height:${bodyH}px"><div class="main">${main}</div></div>${status([statusItem.project, statusItem.sample, statusItem.engine])}</div></body></html>`;
}

/* ---------- render ---------- */
const pages = [
  ['00_workflow', workflowPage(), 770], ['01_project', projectPage(), 1000], ['02_sample', samplePage(), 1000],
  ['03_calculations', calcPage(), 1000], ['04_method', methodPage(), 1000], ['05_summary', summaryPage(), 1000],
];
const only = process.argv[2];
for (const [name, html, h] of pages) {
  if (only && !name.startsWith(only)) continue;
  const f = path.join(__dirname, name + '.html');
  fs.writeFileSync(f, html);
  execFileSync(EDGE, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--force-device-scale-factor=${SCALE}`,
    `--window-size=1602,${h + 2}`, '--virtual-time-budget=4000', `--screenshot=${path.join(OUT, name + '.png')}`, 'file:///' + f.replace(/\\/g, '/')], { stdio: 'ignore' });
  console.log('rendered', name);
}
