import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Charge and multiplicity. The multiplicity list holds only what the electron count allows;
// a charge that changes the parity moves the multiplicity to the lowest allowed one.
Column {
    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: qsTr('Charge:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: -99; top: 99 }
            text: Globals.BackendWrapper.sampleCharge
            onEditingFinished: {
                Globals.BackendWrapper.sampleSetCharge(parseInt(text))
                text = Qt.binding(() => Globals.BackendWrapper.sampleCharge)  // a refused charge shows the old one
            }
        }
    }

    Components.LabelledField {
        text: qsTr('Multiplicity:')
        Components.ChoiceComboBox {
            width: parent.width
            // ChoiceComboBox compares string values
            choices: Array.from(Globals.BackendWrapper.sampleMultiplicityChoices,
                                choice => ({ value: String(choice.value), label: choice.label }))
            value: String(Globals.BackendWrapper.sampleMultiplicity)
            onSelected: (value) => Globals.BackendWrapper.sampleSetMultiplicity(parseInt(value))
        }
    }
}
