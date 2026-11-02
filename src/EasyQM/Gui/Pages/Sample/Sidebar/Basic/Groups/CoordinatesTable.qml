import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


// The atoms with Cartesian or, for a crystal, fractional coordinates, editable.
EaComponents.TableView {
    id: atomsTable

    readonly property int coordinateWidth: EaStyle.Sizes.fontPixelSize * 4.5
    readonly property bool fractional: Globals.BackendWrapper.sampleCoordinates === 'fractional'

    // An atom's x, y or z, editable in the coordinates shown. Not while a job runs: the job
    // was set up for the current structure, and an optimisation moves it when it converges.
    component CoordinateInput: EaComponents.TableViewTextInput {
        property int atomIndex
        property int axis
        property real value
        readonly property string shown: value.toFixed(4)

        horizontalAlignment: Text.AlignRight
        enabled: !Globals.BackendWrapper.jobRunning
        text: shown

        // Editing an atom selects it, unless it is part of the selection already.
        onActiveFocusChanged: {
            if (activeFocus && !Globals.BackendWrapper.sampleSelectedAtoms.includes(atomIndex)) {
                Globals.BackendWrapper.sampleSelectAtom(atomIndex, 'only')
            }
        }
        // A refused or unchanged value shows the backend's value again.
        onEditingFinished: {
            if (text !== shown) {
                Globals.BackendWrapper.sampleSetAtomCoordinate(atomIndex, axis, text)
            }
            text = Qt.binding(() => shown)
        }
    }

    defaultInfoText: qsTr('No structure loaded')
    // EasyApp delays presses by 10 ms, and the replayed press never reaches the rows'
    // TapHandler, so row clicks would be lost.
    pressDelay: 0
    // Row count only: the delegates read the current atom by index, so a change of one
    // atom does not rebuild the table.
    model: Globals.BackendWrapper.sampleAtoms.length

    // Bring an atom picked in the viewer into view.
    Connections {
        target: Globals.BackendWrapper
        function onSampleSelectedAtomsChanged() {
            const selected = Globals.BackendWrapper.sampleSelectedAtoms
            if (selected.length > 0) {
                atomsTable.positionViewAtIndex(selected[selected.length - 1], ListView.Contain)
            }
        }
    }

    header: EaComponents.TableViewHeader {
        EaComponents.TableViewLabel {
            width: EaStyle.Sizes.fontPixelSize * 2.5
            text: qsTr('No.')
        }
        EaComponents.TableViewLabel {
            flexibleWidth: true
            horizontalAlignment: Text.AlignLeft
            text: qsTr('Label')
        }
        EaComponents.TableViewLabel {
            width: EaStyle.Sizes.fontPixelSize * 2.5
            horizontalAlignment: Text.AlignLeft
            text: qsTr('El.')
        }
        EaComponents.TableViewLabel {
            width: coordinateWidth
            horizontalAlignment: Text.AlignRight
            text: fractional ? qsTr('x') : qsTr('x (Å)')
        }
        EaComponents.TableViewLabel {
            width: coordinateWidth
            horizontalAlignment: Text.AlignRight
            text: fractional ? qsTr('y') : qsTr('y (Å)')
        }
        EaComponents.TableViewLabel {
            width: coordinateWidth
            horizontalAlignment: Text.AlignRight
            text: fractional ? qsTr('z') : qsTr('z (Å)')
        }
        EaComponents.TableViewLabel {
            width: EaStyle.Sizes.tableRowHeight
            text: qsTr('Fix')
            ToolTip.text: qsTr('Keep the atom in place during geometry optimisation')
        }
    }

    delegate: EaComponents.TableViewDelegate {
        readonly property var atom: Globals.BackendWrapper.sampleAtoms[index]
        readonly property bool selected: Globals.BackendWrapper.sampleSelectedAtoms.includes(index)

        color: selected ?
                   EaStyle.Colors.themeRowHighlightHovered :
                   index % 2 ? EaStyle.Colors.themeBackgroundHovered2 : EaStyle.Colors.themeBackgroundHovered1

        // Click selects the atom, Ctrl-click adds it or takes it out, Shift-click selects
        // the rows from the last clicked one to this one.
        TapHandler {
            id: rowTap
            onTapped: {
                const modifiers = rowTap.point.modifiers
                const mode = modifiers & Qt.ShiftModifier ? 'range' :
                             modifiers & Qt.ControlModifier ? 'toggle' : 'only'
                Globals.BackendWrapper.sampleSelectAtom(index, mode)
            }
        }

        EaComponents.TableViewLabel {
            width: EaStyle.Sizes.fontPixelSize * 2.5
            color: EaStyle.Colors.themeForegroundMinor
            text: index + 1
        }
        EaComponents.TableViewLabel {
            flexibleWidth: true
            horizontalAlignment: Text.AlignLeft
            text: atom.label
        }
        EaComponents.TableViewLabel {
            width: EaStyle.Sizes.fontPixelSize * 2.5
            horizontalAlignment: Text.AlignLeft
            text: atom.element
        }
        CoordinateInput {
            width: coordinateWidth
            atomIndex: index
            axis: 0
            value: fractional ? atom.fx : atom.x
        }
        CoordinateInput {
            width: coordinateWidth
            atomIndex: index
            axis: 1
            value: fractional ? atom.fy : atom.y
        }
        CoordinateInput {
            width: coordinateWidth
            atomIndex: index
            axis: 2
            value: fractional ? atom.fz : atom.z
        }
        EaComponents.TableViewCheckBox {
            width: EaStyle.Sizes.tableRowHeight
            checked: atom.fixed
            onToggled: Globals.BackendWrapper.sampleSetAtomFixed(index, checked)
        }
    }
}
