import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// PoC1: charge and multiplicity are shown from the sample, not editable yet.
Column {
    spacing: EaStyle.Sizes.fontPixelSize

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
            text: multiplicityLabel(Globals.BackendWrapper.sampleMultiplicity)
        }
    }

    function multiplicityLabel(value) {
        const names = ['', 'singlet', 'doublet', 'triplet', 'quartet', 'quintet']
        return value < names.length ? `${value} (${names[value]})` : `${value}`
    }
}
