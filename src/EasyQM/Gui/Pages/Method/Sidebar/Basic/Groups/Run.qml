import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


// Run and Stop, at the foot of the sidebar above Continue, as EasyDiffractionBeta places
// its Start fitting button.
Row {
    spacing: EaStyle.Sizes.fontPixelSize

    readonly property int buttonWidth: (EaStyle.Sizes.sideBarContentWidth - spacing) / 2

    EaElements.SideBarButton {
        width: buttonWidth
        fontIcon: 'play-circle'
        text: qsTr('Run workflow')
        enabled: Globals.BackendWrapper.methodEngineFound &&
                 Globals.BackendWrapper.methodCanRun &&
                 Globals.BackendWrapper.calculationsSelectedCount > 0 &&
                 !Globals.BackendWrapper.jobRunning
        onClicked: Globals.BackendWrapper.jobRun()
    }
    EaElements.SideBarButton {
        width: buttonWidth
        fontIcon: 'stop'
        text: qsTr('Stop')
        enabled: Globals.BackendWrapper.jobRunning
        onClicked: Globals.BackendWrapper.jobStop()
    }
}
