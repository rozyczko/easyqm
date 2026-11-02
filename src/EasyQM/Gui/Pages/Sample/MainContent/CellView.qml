import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


// The unit cell of a crystal: lattice vectors and parameters, read-only (edited in the sidebar).
Rectangle {
    color: EaStyle.Colors.mainContentBackground

    readonly property var cell: Globals.BackendWrapper.sampleCell
    readonly property bool periodic: cell.a !== undefined

    component Table: Grid {
        property var cells: []
        columnSpacing: EaStyle.Sizes.fontPixelSize * 2
        rowSpacing: EaStyle.Sizes.fontPixelSize * 0.5

        // Grid skips items of zero width, which an empty label has: the corner gets a space.
        Repeater {
            model: parent.cells
            EaElements.Label {
                // The first row and column are headings.
                color: index < parent.columns || index % parent.columns === 0 ?
                           EaStyle.Colors.themeForegroundMinor : EaStyle.Colors.themeForeground
                horizontalAlignment: Text.AlignRight
                text: modelData
            }
        }
    }

    Column {
        visible: periodic
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: EaStyle.Sizes.fontPixelSize * 1.5
        spacing: EaStyle.Sizes.fontPixelSize * 1.5

        Table {
            columns: 4
            cells: periodic ? [' ', qsTr('x (Å)'), qsTr('y (Å)'), qsTr('z (Å)')].concat(
                       ...['a', 'b', 'c'].map((name, row) => [name].concat(cell.vectors[row].map(v => v.toFixed(4))))) : []
        }

        Table {
            columns: 4
            cells: periodic ? [
                ' ', 'a, α', 'b, β', 'c, γ',
                qsTr('Length (Å)'), cell.a.toFixed(4), cell.b.toFixed(4), cell.c.toFixed(4),
                qsTr('Angle (°)'), cell.alpha.toFixed(2), cell.beta.toFixed(2), cell.gamma.toFixed(2)
            ] : []
        }

        EaElements.Label {
            text: periodic ? qsTr('Volume %1 Å³ · space group %2 · %3 atoms in the cell')
                             .arg(cell.volume.toFixed(2))
                             .arg(cell.spaceGroup || qsTr('unknown'))
                             .arg(Globals.BackendWrapper.sampleAtomCount) : ''
        }
    }

    EaElements.Label {
        visible: !periodic
        anchors.centerIn: parent
        color: EaStyle.Colors.themeForegroundMinor
        text: qsTr('A molecule has no unit cell.')
    }
}
