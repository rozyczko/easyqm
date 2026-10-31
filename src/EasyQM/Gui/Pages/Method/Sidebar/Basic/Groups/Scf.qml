import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: qsTr('Convergence:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodScfConvergenceChoices
            value: Globals.BackendWrapper.methodScfConvergence
            onSelected: (value) => Globals.BackendWrapper.methodSetScfConvergence(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Max. iterations:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 1; top: 10000 }
            text: Globals.BackendWrapper.methodScfMaxIterations
            onEditingFinished: Globals.BackendWrapper.methodSetScfMaxIterations(parseInt(text))
        }
    }

    Components.LabelledField {
        text: qsTr('Integration grid:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodIntegrationGridChoices
            value: Globals.BackendWrapper.methodIntegrationGrid
            onSelected: (value) => Globals.BackendWrapper.methodSetIntegrationGrid(value)
        }
    }

    EaElements.CheckBox {
        text: qsTr('Stability check')
        checked: Globals.BackendWrapper.methodStabilityCheck
        onToggled: Globals.BackendWrapper.methodSetStabilityCheck(checked)
    }
}
