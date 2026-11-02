import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Cell parameters of a crystal: lengths and angles editable, volume and space group derived.
// Empty and disabled for a molecule, and disabled while a job runs (the job was set up for
// the current cell, and a variable-cell optimisation changes it when it converges).
Column {
    spacing: EaStyle.Sizes.fontPixelSize
    enabled: Globals.BackendWrapper.samplePeriodic

    readonly property var cell: Globals.BackendWrapper.sampleCell
    readonly property bool periodic: cell.a !== undefined

    // One cell parameter. The atoms keep their fractional coordinates.
    component ParameterField: EaElements.TextField {
        property string name
        property int decimals
        readonly property var cell: Globals.BackendWrapper.sampleCell
        readonly property string shown: cell[name] === undefined ? '' : cell[name].toFixed(decimals)

        horizontalAlignment: TextInput.AlignLeft
        enabled: !Globals.BackendWrapper.jobRunning
        text: shown

        // A refused or unchanged value shows the backend's value again.
        onEditingFinished: {
            if (text !== shown) {
                Globals.BackendWrapper.sampleSetCellParameter(name, text)
            }
            text = Qt.binding(() => shown)
        }
    }

    Components.LabelledField {
        text: qsTr('a, b, c:')
        units: 'Å'

        Row {
            id: lengthsRow
            width: parent.width
            spacing: EaStyle.Sizes.fontPixelSize * 0.5

            Repeater {
                model: ['a', 'b', 'c']
                ParameterField {
                    width: (lengthsRow.width - 2 * lengthsRow.spacing) / 3
                    name: modelData
                    decimals: 4
                }
            }
        }
    }

    Components.LabelledField {
        text: qsTr('α, β, γ:')
        units: '°'

        Row {
            id: anglesRow
            width: parent.width
            spacing: EaStyle.Sizes.fontPixelSize * 0.5

            Repeater {
                model: ['alpha', 'beta', 'gamma']
                ParameterField {
                    width: (anglesRow.width - 2 * anglesRow.spacing) / 3
                    name: modelData
                    decimals: 2
                }
            }
        }
    }

    Components.LabelledField {
        text: qsTr('Volume:')
        units: 'Å³'
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: periodic ? cell.volume.toFixed(2) : ''
        }
    }

    Components.LabelledField {
        text: qsTr('Space group:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            // An edited structure need not have the symmetry of its file.
            text: periodic ? cell.spaceGroup || qsTr('unknown') : ''
        }
    }
}
