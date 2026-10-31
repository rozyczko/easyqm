import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    EaElements.SideBarButton {
        wide: true
        fontIcon: 'upload'
        text: qsTr('Load structure from file...')
        // PoC1 ships with benzene only; file loading comes with the structure reader.
        enabled: false
    }

    Components.LabelledField {
        text: qsTr('Source:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.sampleSummary
        }
    }

    Row {
        spacing: EaStyle.Sizes.fontPixelSize

        EaElements.CheckBox {
            text: qsTr('Periodic')
            enabled: false
            checked: Globals.BackendWrapper.samplePeriodic
        }
        EaElements.Label {
            anchors.verticalCenter: parent.verticalCenter
            color: EaStyle.Colors.themeForegroundMinor
            text: Globals.BackendWrapper.samplePeriodic ? qsTr('crystal') : qsTr('molecule')
        }
    }
}
