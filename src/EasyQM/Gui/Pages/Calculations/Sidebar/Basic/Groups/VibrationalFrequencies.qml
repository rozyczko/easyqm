import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: qsTr('Type:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.calculationsFreqTypeChoices
            value: Globals.BackendWrapper.calculationsFreqType
            onSelected: (value) => Globals.BackendWrapper.calculationsSetFreqType(value)
        }
    }

    Components.LabelledField {
        text: qsTr('Temperature:')
        units: 'K'
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: DoubleValidator { bottom: 0.0 }
            text: Globals.BackendWrapper.calculationsFreqTemperature
            onEditingFinished: Globals.BackendWrapper.calculationsSetFreqTemperature(parseFloat(text))
        }
    }

    Components.LabelledField {
        text: qsTr('Pressure:')
        units: 'atm'
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: DoubleValidator { bottom: 0.0 }
            text: Globals.BackendWrapper.calculationsFreqPressure
            onEditingFinished: Globals.BackendWrapper.calculationsSetFreqPressure(parseFloat(text))
        }
    }

    EaElements.CheckBox {
        text: qsTr('Raman intensities')
        checked: Globals.BackendWrapper.calculationsFreqRaman
        onToggled: Globals.BackendWrapper.calculationsSetFreqRaman(checked)
    }
}
