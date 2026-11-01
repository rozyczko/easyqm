import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    // Charge and multiplicity belong to the sample; they are shown here, set on the Sample page.
    Components.LabelledField {
        text: qsTr('Charge:')
        EaElements.TextField {
            width: parent.width
            enabled: false
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.sampleCharge
        }
    }

    Components.LabelledField {
        text: qsTr('Multiplicity:')
        EaElements.TextField {
            width: parent.width
            enabled: false
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.sampleMultiplicity
        }
    }

    Components.LabelledField {
        text: qsTr('Reference:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodReferenceChoices
            value: Globals.BackendWrapper.methodReference
            onSelected: (value) => Globals.BackendWrapper.methodSetReference(value)
        }
    }

    // Insulators need fixed occupations for their phonons; metals need smearing.
    Components.LabelledField {
        visible: Globals.BackendWrapper.methodOccupationsChoices.length > 0
        text: qsTr('Occupations:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodOccupationsChoices
            value: Globals.BackendWrapper.methodOccupations
            onSelected: (value) => Globals.BackendWrapper.methodSetOccupations(value)
        }
    }

    Components.LabelledField {
        visible: Globals.BackendWrapper.methodSolvationChoices.length > 0
        text: qsTr('Solvation:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.methodSolvationChoices
            value: Globals.BackendWrapper.methodSolvation
            onSelected: (value) => Globals.BackendWrapper.methodSetSolvation(value)
        }
    }
}
