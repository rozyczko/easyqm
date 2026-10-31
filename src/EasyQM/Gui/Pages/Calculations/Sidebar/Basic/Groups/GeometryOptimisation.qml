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
            choices: Globals.BackendWrapper.calculationsOptConvergenceChoices
            value: Globals.BackendWrapper.calculationsOptConvergence
            onSelected: (value) => Globals.BackendWrapper.calculationsSetOptConvergence(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Max. steps:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 1; top: 10000 }
            text: Globals.BackendWrapper.calculationsOptMaxSteps
            onEditingFinished: Globals.BackendWrapper.calculationsSetOptMaxSteps(parseInt(text))
        }
    }

    Components.LabelledField {
        text: qsTr('Optimise:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.calculationsOptOptimiseChoices
            value: Globals.BackendWrapper.calculationsOptOptimise
            onSelected: (value) => Globals.BackendWrapper.calculationsSetOptOptimise(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Constraints:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            // Derived from the Fix column of the Atoms table on the Sample page.
            text: Globals.BackendWrapper.sampleFixedCount > 0 ?
                      qsTr('Fixed atoms (%1 frozen)').arg(Globals.BackendWrapper.sampleFixedCount) :
                      qsTr('None (0 frozen)')
        }
    }

    EaElements.CheckBox {
        text: qsTr('Keep trajectory')
        checked: Globals.BackendWrapper.calculationsOptKeepTrajectory
        onToggled: Globals.BackendWrapper.calculationsSetOptKeepTrajectory(checked)
    }
}
