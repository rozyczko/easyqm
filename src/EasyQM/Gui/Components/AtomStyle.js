.pragma library

// Display colour (CPK-like) and ball radius in Å per element, shared by the structure viewers.

const STYLES = {
    H: { color: '#e8e8e8', radius: 0.30 },
    C: { color: '#5a5a5a', radius: 0.45 },
    N: { color: '#3050f8', radius: 0.42 },
    O: { color: '#ff0d0d', radius: 0.40 },
    F: { color: '#90e050', radius: 0.38 },
    Si: { color: '#f0c8a0', radius: 0.55 },
    P: { color: '#ff8000', radius: 0.52 },
    S: { color: '#ffff30', radius: 0.50 },
    Cl: { color: '#1ff01f', radius: 0.50 }
}

// Jmol colours of the other elements, H to Rn, drawn with the default radius.
const COLORS = {
    He: '#d9ffff', Li: '#cc80ff', Be: '#c2ff00', B: '#ffb5b5', Ne: '#b3e3f5', Na: '#ab5cf2',
    Mg: '#8aff00', Al: '#bfa6a6', Ar: '#80d1e3', K: '#8f40d4', Ca: '#3dff00', Sc: '#e6e6e6',
    Ti: '#bfc2c7', V: '#a6a6ab', Cr: '#8a99c7', Mn: '#9c7ac7', Fe: '#e06633', Co: '#f090a0',
    Ni: '#50d050', Cu: '#c88033', Zn: '#7d80b0', Ga: '#c28f8f', Ge: '#668f8f', As: '#bd80e3',
    Se: '#ffa100', Br: '#a62929', Kr: '#5cb8d1', Rb: '#702eb0', Sr: '#00ff00', Y: '#94ffff',
    Zr: '#94e0e0', Nb: '#73c2c9', Mo: '#54b5b5', Tc: '#3b9e9e', Ru: '#248f8f', Rh: '#0a7d8c',
    Pd: '#006985', Ag: '#c0c0c0', Cd: '#ffd98f', In: '#a67573', Sn: '#668080', Sb: '#9e63b5',
    Te: '#d47a00', I: '#940094', Xe: '#429eb0', Cs: '#57178f', Ba: '#00c900', La: '#70d4ff',
    Ce: '#ffffc7', Pr: '#d9ffc7', Nd: '#c7ffc7', Pm: '#a3ffc7', Sm: '#8fffc7', Eu: '#61ffc7',
    Gd: '#45ffc7', Tb: '#30ffc7', Dy: '#1fffc7', Ho: '#00ff9c', Er: '#00e675', Tm: '#00d452',
    Yb: '#00bf38', Lu: '#00ab24', Hf: '#4dc2ff', Ta: '#4da6ff', W: '#2194d6', Re: '#267dab',
    Os: '#266696', Ir: '#175487', Pt: '#d0d0e0', Au: '#ffd123', Hg: '#b8b8d0', Tl: '#a6544d',
    Pb: '#575961', Bi: '#9e4fb5', Po: '#ab5c00', At: '#754f45', Rn: '#428296'
}

const DEFAULT = { color: '#ff1493', radius: 0.45 }

function color(element) {
    return (STYLES[element] || {}).color || COLORS[element] || DEFAULT.color
}

function radius(element) {
    return (STYLES[element] || DEFAULT).radius
}

// Text colour that reads on the element's colour.
function labelColor(element) {
    const hex = color(element).substring(1)
    const r = parseInt(hex.substring(0, 2), 16)
    const g = parseInt(hex.substring(2, 4), 16)
    const b = parseInt(hex.substring(4, 6), 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#333333' : '#ffffff'
}
