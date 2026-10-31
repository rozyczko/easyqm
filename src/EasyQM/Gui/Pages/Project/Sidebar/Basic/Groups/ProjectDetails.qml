import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: qsTr('Name:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.projectName
            onEditingFinished: Globals.BackendWrapper.projectSetName(text)
        }
    }

    Components.LabelledField {
        text: qsTr('Description:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.projectDescription
            onEditingFinished: Globals.BackendWrapper.projectSetDescription(text)
        }
    }

    Components.LabelledField {
        text: qsTr('Location:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            // Chosen in the create dialog; an existing project folder is not moved from here.
            readOnly: true
            text: Globals.BackendWrapper.projectLocation
        }
    }

    EaElements.CheckBox {
        text: qsTr('Auto-save')
        checked: Globals.BackendWrapper.projectAutoSave
        onToggled: Globals.BackendWrapper.projectSetAutoSave(checked)
        ToolTip.text: qsTr('Write the project file after every change')
    }
}
