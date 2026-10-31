import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components

import Gui.Globals as Globals


// TEMPORARY 2D structure viewer (PoC1).
// Draws the sample on a Canvas: orthographic projection, drag to rotate, wheel to zoom, atoms
// painted back to front. To be replaced by a QtQuick3D viewer reading the same
// `sampleAtoms` / `sampleBonds` properties; nothing outside this file depends on the Canvas.
Rectangle {
    id: view

    color: EaStyle.Colors.mainContentBackground

    // View state
    property real yaw: 0.0
    property real pitch: 0.0
    property real zoom: 1.0
    property string style: 'ballstick'  // 'ballstick' | 'wireframe' | 'spacefill'
    property bool showLabels: true

    readonly property var atoms: Globals.BackendWrapper.sampleAtoms
    readonly property var bonds: Globals.BackendWrapper.sampleBonds

    onAtomsChanged: canvas.requestPaint()
    onBondsChanged: canvas.requestPaint()
    onYawChanged: canvas.requestPaint()
    onPitchChanged: canvas.requestPaint()
    onZoomChanged: canvas.requestPaint()
    onStyleChanged: canvas.requestPaint()
    onShowLabelsChanged: canvas.requestPaint()

    function resetView() {
        yaw = 0.0
        pitch = 0.0
        zoom = 1.0
    }

    // Rotate about y (yaw) then x (pitch); returns [x, y, depth] in Å about the molecule centre.
    function rotate(x, y, z) {
        const cy = Math.cos(yaw), sy = Math.sin(yaw)
        const cp = Math.cos(pitch), sp = Math.sin(pitch)
        const x1 = x * cy + z * sy
        const z1 = -x * sy + z * cy
        const y2 = y * cp - z1 * sp
        const z2 = y * sp + z1 * cp
        return [x1, y2, z2]
    }

    Canvas {
        id: canvas

        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            const ctx = getContext('2d')
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            if (!view.atoms || view.atoms.length === 0) {
                return
            }

            // Centre and extent of the molecule
            let cx = 0, cy = 0, cz = 0
            for (const atom of view.atoms) {
                cx += atom.x; cy += atom.y; cz += atom.z
            }
            cx /= view.atoms.length; cy /= view.atoms.length; cz /= view.atoms.length
            let extent = 1.0
            for (const atom of view.atoms) {
                extent = Math.max(extent, Math.hypot(atom.x - cx, atom.y - cy, atom.z - cz))
            }
            const scale = Math.min(width, height) * 0.5 / (extent + 1.0) * 0.85 * view.zoom

            // Project
            const projected = []
            for (let i = 0; i < view.atoms.length; i++) {
                const atom = view.atoms[i]
                const r = view.rotate(atom.x - cx, atom.y - cy, atom.z - cz)
                projected.push({
                    index: i,
                    sx: width / 2 + r[0] * scale,
                    sy: height / 2 - r[1] * scale,
                    depth: r[2],
                    radius: ballRadius(atom.element) * scale,
                    atom: atom
                })
            }

            // Bonds under the atoms
            if (view.style !== 'spacefill') {
                ctx.lineWidth = view.style === 'wireframe' ? 3 : Math.max(2, 0.12 * scale)
                ctx.lineCap = 'round'
                ctx.strokeStyle = '#9aa3ad'
                for (const bond of view.bonds) {
                    const a = projected[bond[0]], b = projected[bond[1]]
                    ctx.beginPath()
                    ctx.moveTo(a.sx, a.sy)
                    ctx.lineTo(b.sx, b.sy)
                    ctx.stroke()
                }
            }

            // Atoms, far to near
            projected.sort((a, b) => a.depth - b.depth)
            ctx.font = `bold ${Math.max(9, Math.round(scale * 0.25))}px sans-serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            for (const p of projected) {
                ctx.beginPath()
                ctx.arc(p.sx, p.sy, p.radius, 0, 2 * Math.PI)
                ctx.fillStyle = Components.AtomStyle.color(p.atom.element)
                ctx.fill()
                ctx.lineWidth = p.atom.fixed ? 3 : 1.5
                ctx.strokeStyle = p.atom.fixed ? EaStyle.Colors.orange : '#7a7a7a'
                ctx.stroke()
                if (view.showLabels && view.style !== 'wireframe') {
                    ctx.fillStyle = Components.AtomStyle.labelColor(p.atom.element)
                    ctx.fillText(p.atom.label, p.sx, p.sy)
                }
            }
        }

        function ballRadius(element) {
            switch (view.style) {
            case 'wireframe': return 0.08
            case 'spacefill': return Components.AtomStyle.radius(element) * 2.6
            default: return Components.AtomStyle.radius(element)
            }
        }
    }

    // Rotate by dragging, zoom with the wheel
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton

        property real lastX: 0
        property real lastY: 0

        onPressed: (mouse) => { lastX = mouse.x; lastY = mouse.y }
        onPositionChanged: (mouse) => {
            if (!pressed) {
                return
            }
            view.yaw += (mouse.x - lastX) * 0.01
            view.pitch += (mouse.y - lastY) * 0.01
            lastX = mouse.x
            lastY = mouse.y
        }
        onWheel: (wheel) => {
            view.zoom = Math.min(5.0, Math.max(0.2, view.zoom * (wheel.angleDelta.y > 0 ? 1.1 : 1 / 1.1)))
        }
    }

    // Toolbar
    Row {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: EaStyle.Sizes.fontPixelSize * 2
        spacing: EaStyle.Sizes.fontPixelSize * 1.5

        Row {
            EaElements.ToolButton {
                fontIcon: 'project-diagram'
                checkable: true
                checked: view.style === 'ballstick'
                ToolTip.text: qsTr('Ball and stick')
                onClicked: view.style = 'ballstick'
            }
            EaElements.ToolButton {
                fontIcon: 'vector-square'
                checkable: true
                checked: view.style === 'wireframe'
                ToolTip.text: qsTr('Wireframe')
                onClicked: view.style = 'wireframe'
            }
            EaElements.ToolButton {
                fontIcon: 'circle'
                checkable: true
                checked: view.style === 'spacefill'
                ToolTip.text: qsTr('Space filling')
                onClicked: view.style = 'spacefill'
            }
        }

        Row {
            EaElements.ToolButton {
                fontIcon: 'tag'
                checkable: true
                checked: view.showLabels
                ToolTip.text: qsTr('Show atom labels')
                onClicked: view.showLabels = !view.showLabels
            }
            EaElements.ToolButton {
                fontIcon: 'ruler'
                enabled: false
                ToolTip.text: qsTr('Measure distances and angles (not available yet)')
            }
        }

        Row {
            EaElements.ToolButton {
                fontIcon: 'arrows-alt'
                enabled: false
                ToolTip.text: qsTr('Select atoms (not available yet)')
            }
            EaElements.ToolButton {
                fontIcon: 'expand'
                ToolTip.text: qsTr('Fit to view')
                onClicked: view.resetView()
            }
            EaElements.ToolButton {
                fontIcon: 'backspace'
                enabled: false
                ToolTip.text: qsTr('Clear selection (not available yet)')
            }
        }
    }

    // Hint line
    EaElements.Label {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: EaStyle.Sizes.fontPixelSize * 1.5
        color: EaStyle.Colors.themeForegroundMinor
        text: qsTr('Rotate: drag · Zoom: wheel')
    }
}
