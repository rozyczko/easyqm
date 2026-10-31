import QtQuick

import EasyApplication.Gui.Style as EaStyle

import Gui.Components as Components
import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    readonly property bool dft: Globals.BackendWrapper.methodFamily === 'DFT'

    Components.LabelledField {
        text: qsTr('Method:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodFamilyChoices
            value: Globals.BackendWrapper.methodFamily
            onSelected: (value) => Globals.BackendWrapper.methodSetFamily(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Functional:')
        enabled: dft
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodFunctionalChoices
            value: Globals.BackendWrapper.methodFunctional
            onSelected: (value) => Globals.BackendWrapper.methodSetFunctional(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Dispersion:')
        enabled: dft
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodDispersionChoices
            value: Globals.BackendWrapper.methodDispersion
            onSelected: (value) => Globals.BackendWrapper.methodSetDispersion(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Basis set:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodBasisSetChoices
            value: Globals.BackendWrapper.methodBasisSet
            onSelected: (value) => Globals.BackendWrapper.methodSetBasisSet(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Auxiliary basis:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodAuxiliaryBasisChoices
            value: Globals.BackendWrapper.methodAuxiliaryBasis
            onSelected: (value) => Globals.BackendWrapper.methodSetAuxiliaryBasis(value)
        }
    }
}
