import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// TD-DFT (CIS or TD-HF with the Hartree-Fock family) or EOM-CCSD, for molecules (ORCA).
// Only the controls of the chosen method are shown.
Column {
    readonly property bool tddft: Globals.BackendWrapper.calculationsExcMethod === 'tddft'

    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: qsTr('Method:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.calculationsExcMethodChoices
            value: Globals.BackendWrapper.calculationsExcMethod
            onSelected: (value) => Globals.BackendWrapper.calculationsSetExcMethod(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Number of states:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 1; top: 50 }
            text: Globals.BackendWrapper.calculationsExcStates
            onEditingFinished: Globals.BackendWrapper.calculationsSetExcStates(parseInt(text))
        }
    }

    Components.LabelledField {
        visible: tddft
        text: qsTr('Occupied orbitals:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 0; top: 1000 }
            text: Globals.BackendWrapper.calculationsExcOccupiedOrbitals
            onEditingFinished: Globals.BackendWrapper.calculationsSetExcOccupiedOrbitals(parseInt(text))
            ToolTip.text: qsTr('The highest occupied orbitals excitations start from; 0 leaves ORCA\'s choice, all but the core orbitals.')
            ToolTip.visible: hovered && EaGlobals.Vars.showToolTips
        }
    }

    Components.LabelledField {
        visible: tddft
        text: qsTr('Virtual orbitals:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 0; top: 1000 }
            text: Globals.BackendWrapper.calculationsExcVirtualOrbitals
            onEditingFinished: Globals.BackendWrapper.calculationsSetExcVirtualOrbitals(parseInt(text))
            ToolTip.text: qsTr('The lowest virtual orbitals excitations end in; 0 for all of them.')
            ToolTip.visible: hovered && EaGlobals.Vars.showToolTips
        }
    }

    EaElements.CheckBox {
        visible: tddft
        text: qsTr('Tamm-Dancoff approximation')
        checked: Globals.BackendWrapper.calculationsExcTda
        onToggled: Globals.BackendWrapper.calculationsSetExcTda(checked)
    }

    EaElements.CheckBox {
        visible: tddft
        text: qsTr('Triplet states (closed-shell singlets)')
        checked: Globals.BackendWrapper.calculationsExcTriplets
        onToggled: Globals.BackendWrapper.calculationsSetExcTriplets(checked)
    }

    EaElements.CheckBox {
        visible: !tddft
        text: qsTr('Frozen core')
        checked: Globals.BackendWrapper.calculationsExcFrozenCore
        onToggled: Globals.BackendWrapper.calculationsSetExcFrozenCore(checked)
    }
}
