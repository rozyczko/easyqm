import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// The symmetry of the current geometry, updated with every edit. A crystal: the space group
// spglib finds for its atoms, with a warning while it differs from the one the file gives.
// A molecule: the point group.
Column {
    readonly property bool periodic: Globals.BackendWrapper.samplePeriodic
    readonly property string pointGroup: Globals.BackendWrapper.samplePointGroup
    readonly property var cell: Globals.BackendWrapper.sampleCell

    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: periodic ? qsTr('Space group:') : qsTr('Point group:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: (periodic ?
                       (cell.spaceGroup ? `${cell.spaceGroup} (${cell.spaceGroupNumber})` : '') :
                       pointGroup) || qsTr('unknown')
        }
    }

    Components.SpaceGroupWarning {}

    EaElements.Label {
        color: EaStyle.Colors.themeForegroundMinor
        text: periodic ?
                  qsTr('From the current atoms, within %1 Å.').arg(Globals.BackendWrapper.sampleSpaceGroupTolerance) :
                  Globals.BackendWrapper.sampleAtomCount > Globals.BackendWrapper.samplePointGroupAtomLimit ?
                      qsTr('Not determined above %1 atoms.').arg(Globals.BackendWrapper.samplePointGroupAtomLimit) :
                      qsTr('From the current geometry, within 4°.')
    }
}
