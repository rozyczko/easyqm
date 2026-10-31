import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    EaElements.CheckBox {
        text: qsTr('Print orbitals')
        checked: Globals.BackendWrapper.calculationsSinglePointPrintOrbitals
        onToggled: Globals.BackendWrapper.calculationsSetSinglePointPrintOrbitals(checked)
    }

    Components.LabelledField {
        text: qsTr('Geometry:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: Globals.BackendWrapper.calculationsSinglePointGeometryChoices
            value: Globals.BackendWrapper.calculationsSinglePointGeometry
            onSelected: (value) => Globals.BackendWrapper.calculationsSetSinglePointGeometry(value)
        }
    }
}
