import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


// Under a space group field: the file gives another space group than spglib finds for the
// atoms. Hidden while they agree, for a molecule, and once the structure has been edited.
EaElements.Label {
    readonly property string warning: Globals.BackendWrapper.sampleSpaceGroupWarning

    visible: Globals.BackendWrapper.samplePeriodic && warning !== ''
    width: EaStyle.Sizes.sideBarContentWidth
    wrapMode: Text.WordWrap
    color: EaStyle.Colors.orange
    text: warning
}
