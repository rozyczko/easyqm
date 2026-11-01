import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// The space group as read from the file. Detecting it, with a tolerance, needs a symmetry
// library (spglib), which is not used yet.
Column {
    spacing: EaStyle.Sizes.fontPixelSize
    enabled: Globals.BackendWrapper.samplePeriodic

    Components.LabelledField {
        text: qsTr('Space group:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.samplePeriodic ?
                      Globals.BackendWrapper.sampleCell.spaceGroup || qsTr('not given in the file') : ''
        }
    }

    EaElements.Label {
        color: EaStyle.Colors.themeForegroundMinor
        text: Globals.BackendWrapper.samplePeriodic ? qsTr('As read from the file.') : qsTr('A molecule has no space group.')
    }
}
