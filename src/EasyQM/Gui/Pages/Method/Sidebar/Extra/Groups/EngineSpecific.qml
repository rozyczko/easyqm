import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// The options only the active engine has, as its adapter lists them; none for most engines.
Column {
    spacing: EaStyle.Sizes.fontPixelSize

    Repeater {
        model: Globals.BackendWrapper.methodEngineOptions

        Components.LabelledField {
            text: modelData.label + ':'
            enabled: !Globals.BackendWrapper.jobRunning
            ToolTip.visible: modelData.tooltip !== '' && hovered.hovered
            ToolTip.text: modelData.tooltip

            HoverHandler { id: hovered }

            Components.ChoiceComboBox {
                width: parent.width
                choices: modelData.choices
                value: modelData.value
                onSelected: (value) => Globals.BackendWrapper.methodSetEngineOption(modelData.name, value)
            }
        }
    }

    EaElements.Label {
        visible: Globals.BackendWrapper.methodEngineOptions.length === 0
        color: EaStyle.Colors.themeForegroundMinor
        text: qsTr('No engine-specific options')
    }

    Components.MessageDialog { id: warningDialog }

    Connections {
        target: Globals.BackendWrapper
        function onMethodWarning(message) {
            warningDialog.show(qsTr('%1 option').arg(Globals.BackendWrapper.methodEngineName), message)
        }
    }
}
