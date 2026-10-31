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

const DEFAULT = { color: '#ff1493', radius: 0.45 }

function color(element) {
    return (STYLES[element] || DEFAULT).color
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
