import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// A crystal: the space group as read from the file; editing the atoms or the cell clears it.
// Detecting it, with a tolerance, needs a symmetry library (spglib), which is not used yet.
// A molecule: the point group, found from the current geometry and updated with every edit.
Column {
    readonly property bool periodic: Globals.BackendWrapper.samplePeriodic
    readonly property string pointGroup: Globals.BackendWrapper.samplePointGroup

    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: periodic ? qsTr('Space group:') : qsTr('Point group:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: (periodic ? Globals.BackendWrapper.sampleCell.spaceGroup : pointGroup) || qsTr('unknown')
        }
    }

    EaElements.Label {
        color: EaStyle.Colors.themeForegroundMinor
        text: periodic ?
                  qsTr('As read from the file; cleared by edits.') :
                  Globals.BackendWrapper.sampleAtomCount > Globals.BackendWrapper.samplePointGroupAtomLimit ?
                      qsTr('Not determined above %1 atoms.').arg(Globals.BackendWrapper.samplePointGroupAtomLimit) :
                      qsTr('From the current geometry, within 4°.')
    }
}
