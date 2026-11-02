import QtQuick
import QtQuick.Controls
import QtQuick3D

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Structure viewer on QtQuick3D, the same for molecules and crystals: it draws the scene the
// Sample part builds (logic/scene.py), atoms with their copies in other cells, bonds and cell
// edges, and does not know which kind of system it shows. Drag to rotate, right-drag to pan,
// wheel to zoom, click to select.
//
// The View3D set-up (orthographic camera on a turntable node, cell edges and axes as
// cylinders, rotation with Node.rotate) follows EasyDiffractionBeta's StructureViewTab.qml,
// BSD-3-Clause, © 2023 EasyDiffraction contributors.
Rectangle {
    id: view

    color: EaStyle.Colors.mainContentBackground

    // View state
    property string style: 'ballstick'  // 'ballstick' | 'wireframe' | 'spacefill'
    property bool showLabels: true
    property bool selectMode: true  // clicks pick atoms; off, they only rotate
    property real zoom: 1.0
    property real panX: 0.0  // Å
    property real panY: 0.0
    // Changed whenever the projection changes, so that the 2D labels follow the 3D scene.
    property int projection: 0

    readonly property var atoms: Globals.BackendWrapper.sampleSceneAtoms
    readonly property var bonds: Globals.BackendWrapper.sampleSceneBonds
    readonly property var edges: Globals.BackendWrapper.sampleCellEdges
    readonly property var centre: Globals.BackendWrapper.sampleSceneCentre
    readonly property real extent: Globals.BackendWrapper.sampleSceneExtent
    readonly property var selected: Globals.BackendWrapper.sampleSelectedSceneAtoms
    readonly property bool periodic: Globals.BackendWrapper.samplePeriodic

    // Scene units per Å: the built-in meshes are 100 units across.
    readonly property real unit: 100
    // Pixels per Å: at zoom 1 the scene, with a margin for the balls, fills 85 % of the shorter side.
    readonly property real scale: Math.min(width, height) * 0.5 * 0.85 / (Math.max(extent, 1.0) + 1.0) * zoom
    // A thickness that looks the same at any zoom, in scene units per pixel.
    readonly property real pixel: unit / scale

    // A loaded structure starts from the default view; an edited or optimised one keeps the
    // user's rotation, zoom and pan.
    Connections {
        target: Globals.BackendWrapper
        function onSampleStructureLoaded() { Qt.callLater(view.resetView) }
    }
    onScaleChanged: reproject()
    onPanXChanged: reproject()
    onPanYChanged: reproject()
    onAtomsChanged: {
        // Labels of hundreds of atoms are clutter; the button turns them back on.
        if (atoms.length > 100) {
            showLabels = false
        }
        reproject()
    }
    onCentreChanged: reproject()

    // Re-place the 2D labels once all bindings of a change have settled: right away they
    // would be mapped with the camera or the scene of before the change.
    function reproject() {
        Qt.callLater(nextProjection)
    }

    function nextProjection() {
        projection++
    }

    function resetView() {
        // A molecule as in its file, x right and y up; a crystal tilted so that the cell reads
        // as a box (the EasyDiffractionBeta default).
        turntable.eulerRotation = periodic ? Qt.vector3d(12, -34, -8) : Qt.vector3d(0, 0, 0)
        zoom = 1.0
        panX = 0.0
        panY = 0.0
        showLabels = atoms.length <= 100  // see onAtomsChanged
        reproject()
    }

    // Turn the structure so that `vector` points at the viewer.
    function lookAlong(vector) {
        turntable.rotation = rotationBetween(Qt.vector3d(vector[0], vector[1], vector[2]), Qt.vector3d(0, 0, 1))
        reproject()
    }

    // The rotation that turns direction u onto direction v.
    function rotationBetween(u, v) {
        u = u.normalized()
        v = v.normalized()
        const axis = u.crossProduct(v)
        const sin = axis.length()
        const cos = u.dotProduct(v)
        if (sin < 1e-9) {
            if (cos > 0) {
                return Qt.quaternion(1, 0, 0, 0)
            }
            // Opposite: half a turn about any axis across u.
            const across = (Math.abs(u.x) < 0.9 ? Qt.vector3d(1, 0, 0) : Qt.vector3d(0, 1, 0)).crossProduct(u).normalized()
            return Qt.quaternion(0, across.x, across.y, across.z)
        }
        const half = Math.atan2(sin, cos) / 2
        const k = Math.sin(half) / sin
        return Qt.quaternion(Math.cos(half), axis.x * k, axis.y * k, axis.z * k)
    }

    function ballRadius(element) {
        switch (style) {
        case 'wireframe': return 0.08
        case 'spacefill': return Components.AtomStyle.radius(element) * 2.6
        default: return Components.AtomStyle.radius(element)
        }
    }

    function scenePoint(x, y, z) {
        return Qt.vector3d(x * unit, y * unit, z * unit)
    }

    // A cylinder between two points: bonds, cell edges, axes.
    component Stick: Model {
        property vector3d from
        property vector3d to
        property real radius  // scene units
        property color color
        property bool shaded: true

        readonly property vector3d along: to.minus(from)

        source: '#Cylinder'
        position: from.plus(to).times(0.5)
        rotation: view.rotationBetween(Qt.vector3d(0, 1, 0), along)
        scale: Qt.vector3d(radius / 50, along.length() / 100, radius / 50)
        materials: PrincipledMaterial {
            baseColor: color
            roughness: 0.5
            lighting: shaded ? PrincipledMaterial.FragmentLighting : PrincipledMaterial.NoLighting
        }
    }

    // A ball: the atom, or a translucent shell around it for selected and fixed atoms.
    component Ball: Model {
        property real radius  // scene units
        property color color

        source: '#Sphere'
        scale: Qt.vector3d(radius / 50, radius / 50, radius / 50)
        materials: PrincipledMaterial {
            baseColor: color
            roughness: 0.35
            alphaMode: color.a < 1 ? PrincipledMaterial.Blend : PrincipledMaterial.Opaque
        }
    }

    View3D {
        id: view3d

        anchors.fill: parent
        camera: camera

        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: view.color
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        OrthographicCamera {
            id: camera
            z: 100000
            clipFar: 200000
            // Not 0 before the page has a size.
            horizontalMagnification: Math.max(1e-3, view.scale / view.unit)
            verticalMagnification: Math.max(1e-3, view.scale / view.unit)
        }

        // Key light from the upper left, fill from the lower right; both fixed to the camera.
        DirectionalLight {
            eulerRotation: Qt.vector3d(-35, -35, 0)
            brightness: 1.0
            ambientColor: Qt.rgba(0.35, 0.35, 0.35, 1.0)
        }
        DirectionalLight {
            eulerRotation: Qt.vector3d(25, 150, 0)
            brightness: 0.35
        }

        Node {
            position: Qt.vector3d(view.panX * view.unit, view.panY * view.unit, 0)

            Node {
                id: turntable

                Node {
                    id: structure

                    position: view.centre.length === 3 ? view.scenePoint(-view.centre[0], -view.centre[1], -view.centre[2]) :
                                                         Qt.vector3d(0, 0, 0)

                    Repeater3D {
                        model: view.atoms

                        Node {
                            readonly property var atom: modelData
                            readonly property real radius: view.ballRadius(atom.element) * view.unit

                            position: view.scenePoint(atom.x, atom.y, atom.z)

                            Ball {
                                property int sceneIndex: index  // for picking
                                pickable: true
                                radius: parent.radius
                                color: Components.AtomStyle.color(atom.element)
                            }
                            Ball {
                                visible: atom.fixed
                                radius: parent.radius + 0.12 * view.unit
                                color: Qt.alpha(EaStyle.Colors.orange, 0.45)
                            }
                            Ball {
                                visible: view.selected.includes(index)
                                radius: parent.radius + 0.25 * view.unit
                                color: Qt.alpha(EaStyle.Colors.themeAccent, 0.4)
                            }
                        }
                    }

                    Repeater3D {
                        model: view.style === 'spacefill' ? 0 : view.bonds.length

                        Stick {
                            // On a change the atoms and the bonds arrive one after the other, and
                            // delegates past the new end are evaluated once more before they go.
                            readonly property var pair: view.bonds[index] ?? []
                            readonly property var first: view.atoms[pair[0]]
                            readonly property var second: view.atoms[pair[1]]

                            visible: first !== undefined && second !== undefined
                            from: visible ? view.scenePoint(first.x, first.y, first.z) : Qt.vector3d(0, 0, 0)
                            to: visible ? view.scenePoint(second.x, second.y, second.z) : Qt.vector3d(0, 1, 0)
                            radius: (view.style === 'wireframe' ? 0.04 : 0.1) * view.unit
                            color: '#9aa3ad'
                        }
                    }

                    // Edges 0, 4 and 8 start at the origin and run along a, b and c.
                    Repeater3D {
                        model: Globals.ViewSettings.showCell ? view.edges.length : 0

                        Stick {
                            readonly property var edge: view.edges[index] ?? [[0, 0, 0], [0, 0, 0]]
                            readonly property var axisColors: ({ 0: EaStyle.Colors.red, 4: EaStyle.Colors.green, 8: EaStyle.Colors.blue })

                            from: view.scenePoint(edge[0][0], edge[0][1], edge[0][2])
                            to: view.scenePoint(edge[1][0], edge[1][1], edge[1][2])
                            radius: (index in axisColors ? 1.5 : 0.75) * view.pixel
                            color: axisColors[index] ?? EaStyle.Colors.themeForegroundMinor
                            shaded: false
                        }
                    }
                }
            }
        }
    }

    // Atom labels, drawn over the 3D view, nearest on top; not hidden by atoms in front.
    Item {
        anchors.fill: parent
        visible: view.showLabels && view.style !== 'wireframe'

        Repeater {
            model: parent.visible ? view.atoms : []

            Text {
                readonly property var atom: modelData
                readonly property vector3d point: {
                    view.projection
                    return view3d.mapFrom3DScene(structure.mapPositionToScene(view.scenePoint(atom.x, atom.y, atom.z)))
                }

                x: point.x - width / 2
                y: point.y - height / 2
                z: -point.z
                font.family: EaStyle.Fonts.fontFamily
                font.bold: true
                font.pixelSize: Math.max(9, Math.round(view.scale * 0.25))
                color: Components.AtomStyle.labelColor(atom.element)
                text: atom.label
            }
        }
    }

    // Rotate by dragging, pan with the right button, zoom with the wheel. In select mode a
    // click (no drag) picks an atom: alone it replaces the selection, with Ctrl or Shift it is
    // added or taken out; a click on the background clears the selection.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton

        property point last
        property point press

        onPressed: (mouse) => { last = press = Qt.point(mouse.x, mouse.y) }
        onPositionChanged: (mouse) => {
            const dx = mouse.x - last.x
            const dy = mouse.y - last.y
            last = Qt.point(mouse.x, mouse.y)
            if (pressedButtons & Qt.RightButton) {
                view.panX += dx / view.scale
                view.panY -= dy / view.scale
                return
            }
            turntable.rotate(dx * 0.4, Qt.vector3d(0, 1, 0), Node.SceneSpace)
            turntable.rotate(dy * 0.4, Qt.vector3d(1, 0, 0), Node.SceneSpace)
            view.reproject()
        }
        onReleased: (mouse) => {
            if (mouse.button !== Qt.LeftButton || !view.selectMode || Math.hypot(mouse.x - press.x, mouse.y - press.y) > 4) {
                return
            }
            const hit = view3d.pick(mouse.x, mouse.y).objectHit
            const extend = (mouse.modifiers & (Qt.ControlModifier | Qt.ShiftModifier)) !== 0
            if (hit && hit.sceneIndex !== undefined) {
                Globals.BackendWrapper.sampleSelectSceneAtom(hit.sceneIndex, extend ? 'toggle' : 'only')
            } else if (!extend) {
                Globals.BackendWrapper.sampleClearSelection()
            }
        }
        onWheel: (wheel) => {
            view.zoom = Math.min(10.0, Math.max(0.2, view.zoom * (wheel.angleDelta.y > 0 ? 1.1 : 1 / 1.1)))
        }
    }

    // Axes gizmo: x, y, z turning with the structure. The letters are 2D items next to the
    // View3D, not in it: items inside a View3D become part of its scene.
    Item {
        visible: Globals.ViewSettings.showAxes
        anchors.left: parent.left
        anchors.bottom: readout.top
        anchors.margins: EaStyle.Sizes.fontPixelSize
        width: EaStyle.Sizes.fontPixelSize * 6
        height: width

        View3D {
            id: gizmo

            anchors.fill: parent
            camera: gizmoCamera

            environment: SceneEnvironment {
                backgroundMode: SceneEnvironment.Transparent
                antialiasingMode: SceneEnvironment.MSAA
            }
            OrthographicCamera { id: gizmoCamera; z: 1000 }
            DirectionalLight { ambientColor: Qt.rgba(0.5, 0.5, 0.5, 1.0) }

            Node {
                id: gizmoAxes
                rotation: turntable.rotation

                Repeater3D {
                    model: [[EaStyle.Colors.red, 1, 0, 0], [EaStyle.Colors.green, 0, 1, 0], [EaStyle.Colors.blue, 0, 0, 1]]

                    Stick {
                        from: Qt.vector3d(0, 0, 0)
                        to: Qt.vector3d(modelData[1], modelData[2], modelData[3]).times(gizmo.width * 0.3)
                        radius: 1.5
                        color: modelData[0]
                    }
                }
            }
        }

        Repeater {
            model: ['x', 'y', 'z']

            Text {
                readonly property vector3d point: {
                    view.projection
                    const tip = Qt.vector3d(index === 0 ? 1 : 0, index === 1 ? 1 : 0, index === 2 ? 1 : 0).times(gizmo.width * 0.4)
                    return gizmo.mapFrom3DScene(gizmoAxes.mapPositionToScene(tip))
                }
                x: point.x - width / 2
                y: point.y - height / 2
                font.family: EaStyle.Fonts.fontFamily
                color: EaStyle.Colors.themeForegroundMinor
                text: modelData
            }
        }
    }

    // A tool button with a letter instead of an icon: Font Awesome 5 has no letters.
    component LetterButton: EaElements.ToolButton {
        property string letter
        EaElements.Label {
            anchors.centerIn: parent
            font.bold: true
            color: parent.enabled ? EaStyle.Colors.themeForeground : EaStyle.Colors.themeForegroundDisabled
            text: parent.letter
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
            visible: view.periodic

            Repeater {
                model: ['a', 'b', 'c']

                LetterButton {
                    letter: modelData
                    ToolTip.text: qsTr('View along %1').arg(modelData)
                    onClicked: view.lookAlong(Globals.BackendWrapper.sampleCell.vectors[index])
                }
            }
        }

        Row {
            EaElements.ToolButton {
                fontIcon: 'arrows-alt'
                checkable: true
                checked: view.selectMode
                ToolTip.text: qsTr('Select atoms')
                onClicked: view.selectMode = !view.selectMode
            }
            EaElements.ToolButton {
                fontIcon: 'expand'
                ToolTip.text: qsTr('Fit to view')
                onClicked: view.resetView()
            }
            EaElements.ToolButton {
                fontIcon: 'backspace'
                enabled: Globals.BackendWrapper.sampleSelectedAtoms.length > 0
                ToolTip.text: qsTr('Clear selection')
                onClicked: Globals.BackendWrapper.sampleClearSelection()
            }
        }
    }

    // Selection readout and hint line
    EaElements.Label {
        id: readout
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: EaStyle.Sizes.fontPixelSize * 1.5
        textFormat: Text.StyledText
        text: Globals.BackendWrapper.sampleSelectionMeasurement === '' ?
                  qsTr('Selected: <b>%1</b>').arg(Globals.BackendWrapper.sampleSelectionText) :
                  qsTr('Selected: <b>%1</b> – %2').arg(Globals.BackendWrapper.sampleSelectionText)
                                                  .arg(Globals.BackendWrapper.sampleSelectionMeasurement)
        opacity: Globals.BackendWrapper.sampleSelectedAtoms.length > 0 ? 1 : 0
    }

    EaElements.Label {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: EaStyle.Sizes.fontPixelSize * 1.5
        color: EaStyle.Colors.themeForegroundMinor
        text: view.selectMode ?
                  qsTr('Select: click · Add: Ctrl+click · Rotate: drag · Pan: right-drag · Zoom: wheel') :
                  qsTr('Rotate: drag · Pan: right-drag · Zoom: wheel')
    }
}
