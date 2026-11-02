import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


// The Z-matrix of a molecule, one row per atom in construction order: the bond length to
// an earlier atom, the angle with a second one and the dihedral with a third. The values
// are editable; the atom moves, and with it the atoms placed from it. The first rows lack
// some values ('—'): chemcoord measures those to the origin and the axes, which keeps the
// molecule in place.
//
// Fix is shown but not editable here. It fixes an atom's Cartesian position in the
// optimiser, not the bond, angle or dihedral of its row, which a checkbox in this table
// would suggest; it is set in the Cartesian table.
EaComponents.TableView {
    id: zmatrixTable

    readonly property var rows: Globals.BackendWrapper.sampleZmatrix
    readonly property int valueCellWidth: EaStyle.Sizes.fontPixelSize * 7

    // One internal coordinate: the atom it is measured to (muted, left) and its value
    // (editable, right). A value measured to the origin or an axis is a dash, not editable.
    // Values are not edited while a job runs: the job was set up for the current structure.
    // EasyApp's table sets the cell width from the header; this Item has no alignment for it
    // to set, so the label and the input keep their own.
    component ValueCell: Item {
        id: cell

        property int atomIndex
        property string field
        property string reference
        property real value
        property int decimals
        readonly property string shown: reference ? value.toFixed(decimals) : '—'

        height: parent ? parent.height : 0

        EaElements.Label {
            anchors.left: parent.left
            anchors.leftMargin: EaStyle.Sizes.fontPixelSize * 0.25
            anchors.verticalCenter: parent.verticalCenter
            color: EaStyle.Colors.themeForegroundMinor
            text: cell.reference
        }

        EaComponents.TableViewTextInput {
            anchors.right: parent.right
            width: parent.width * 0.65
            height: parent.height
            horizontalAlignment: Text.AlignRight
            readOnly: !cell.reference
            enabled: !Globals.BackendWrapper.jobRunning
            text: cell.shown

            // Editing an atom selects it, unless it is part of the selection already.
            onActiveFocusChanged: {
                if (activeFocus && !Globals.BackendWrapper.sampleSelectedAtoms.includes(cell.atomIndex)) {
                    Globals.BackendWrapper.sampleSelectAtom(cell.atomIndex, 'only')
                }
            }
            // A refused or unchanged value shows the backend's value again.
            onEditingFinished: {
                if (cell.reference && text !== cell.shown) {
                    Globals.BackendWrapper.sampleSetZmatrixValue(cell.atomIndex, cell.field, text)
                }
                text = Qt.binding(() => cell.shown)
            }
        }
    }

    defaultInfoText: qsTr('No structure loaded')
    // See CoordinatesTable.qml: row clicks would be lost with EasyApp's press delay.
    pressDelay: 0
    // Row count only: the delegates read their row by index, so edits do not rebuild the
    // table (the rows keep their order while the atoms move).
    model: rows.length

    // Bring an atom picked in the viewer into view.
    Connections {
        target: Globals.BackendWrapper
        function onSampleSelectedAtomsChanged() {
            const selected = Globals.BackendWrapper.sampleSelectedAtoms
            if (selected.length > 0) {
                const row = zmatrixTable.rows.findIndex(entry => entry.atom === selected[selected.length - 1])
                if (row >= 0) {
                    zmatrixTable.positionViewAtIndex(row, ListView.Contain)
                }
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
            text: qsTr('Atom')
        }
        EaComponents.TableViewLabel {
            width: valueCellWidth
            horizontalAlignment: Text.AlignRight
            text: qsTr('Bond (Å)')
            ToolTip.text: qsTr('Bond length to the atom on the left')
        }
        EaComponents.TableViewLabel {
            width: valueCellWidth
            horizontalAlignment: Text.AlignRight
            text: qsTr('Angle (°)')
            ToolTip.text: qsTr('Bond angle at the bonded atom, towards the atom on the left')
        }
        EaComponents.TableViewLabel {
            width: valueCellWidth
            horizontalAlignment: Text.AlignRight
            text: qsTr('Dihedral (°)')
            ToolTip.text: qsTr('Dihedral angle with the atom on the left, positive clockwise (IUPAC)')
        }
        EaComponents.TableViewLabel {
            width: EaStyle.Sizes.tableRowHeight
            text: qsTr('Fix')
            ToolTip.text: qsTr('Atoms kept in place during geometry optimisation. This fixes the position, not the ' +
                               'values in the row: set it in the Cartesian view.')
        }
    }

    delegate: EaComponents.TableViewDelegate {
        readonly property var row: zmatrixTable.rows[index] ?? {}
        readonly property var atom: Globals.BackendWrapper.sampleAtoms[row.atom] ?? {}
        readonly property bool selected: Globals.BackendWrapper.sampleSelectedAtoms.includes(row.atom)

        color: selected ?
                   EaStyle.Colors.themeRowHighlightHovered :
                   index % 2 ? EaStyle.Colors.themeBackgroundHovered2 : EaStyle.Colors.themeBackgroundHovered1

        // Click, Ctrl-click and Shift-click as in the coordinates table; a range runs over
        // the rows as shown.
        TapHandler {
            id: rowTap
            onTapped: {
                const modifiers = rowTap.point.modifiers
                const mode = modifiers & Qt.ShiftModifier ? 'range' :
                             modifiers & Qt.ControlModifier ? 'toggle' : 'only'
                Globals.BackendWrapper.sampleSelectAtom(row.atom, mode)
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
            text: row.label ?? ''
        }
        ValueCell {
            width: valueCellWidth
            atomIndex: row.atom ?? -1
            field: 'bond'
            reference: row.bondTo ?? ''
            value: row.bond ?? 0
            decimals: 4
        }
        ValueCell {
            width: valueCellWidth
            atomIndex: row.atom ?? -1
            field: 'angle'
            reference: row.angleTo ?? ''
            value: row.angle ?? 0
            decimals: 2
        }
        ValueCell {
            width: valueCellWidth
            atomIndex: row.atom ?? -1
            field: 'dihedral'
            reference: row.dihedralTo ?? ''
            value: row.dihedral ?? 0
            decimals: 2
        }
        // Read-only: see the note at the top.
        EaComponents.TableViewCheckBox {
            width: EaStyle.Sizes.tableRowHeight
            enabled: false
            checked: atom.fixed ?? false
        }
    }
}
