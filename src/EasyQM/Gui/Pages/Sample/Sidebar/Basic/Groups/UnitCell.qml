import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Read-only cell parameters; empty and disabled for a molecule.
Column {
    spacing: EaStyle.Sizes.fontPixelSize
    enabled: Globals.BackendWrapper.samplePeriodic

    readonly property var cell: Globals.BackendWrapper.sampleCell

    // '5.6402  5.6402  5.6402' for the given keys; '' for a molecule.
    function values(keys, decimals) {
        return cell.a === undefined ? '' : keys.map(key => cell[key].toFixed(decimals)).join('  ')
    }

    Components.LabelledField {
        text: qsTr('a, b, c:')
        units: 'Å'
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: values(['a', 'b', 'c'], 4)
        }
    }

    Components.LabelledField {
        text: qsTr('α, β, γ:')
        units: '°'
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: values(['alpha', 'beta', 'gamma'], 2)
        }
    }

    Components.LabelledField {
        text: qsTr('Volume:')
        units: 'Å³'
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: values(['volume'], 2)
        }
    }

    Components.LabelledField {
        text: qsTr('Space group:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: cell.a === undefined ? '' : cell.spaceGroup || qsTr('not given in the file')
        }
    }
}
