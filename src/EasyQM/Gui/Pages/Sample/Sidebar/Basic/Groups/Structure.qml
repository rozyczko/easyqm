import QtQuick
import QtQuick.Dialogs

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
        // A running job was set up for the current structure.
        enabled: !Globals.BackendWrapper.jobRunning
        onClicked: structureFileDialog.open()
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

    FileDialog {
        id: structureFileDialog
        title: qsTr('Load a structure')
        nameFilters: [qsTr('Structure files (*.cif *.xyz)'), qsTr('CIF files (*.cif)'), qsTr('XYZ files (*.xyz)'),
                      qsTr('All files (*)')]
        onAccepted: Globals.BackendWrapper.sampleLoadStructure(selectedFile)
    }

    Components.MessageDialog { id: loadErrorDialog }

    Connections {
        target: Globals.BackendWrapper
        function onSampleLoadError(message) { loadErrorDialog.show(qsTr('Structure could not be loaded'), message) }
    }
}
