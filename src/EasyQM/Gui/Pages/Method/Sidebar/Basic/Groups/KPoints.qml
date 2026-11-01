import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Monkhorst-Pack sampling of a crystal: a grid from the spacing, or set by hand. The
// spacing is CASTEP's kpoint_mp_spacing, without the 2π factor.
Column {
    spacing: EaStyle.Sizes.fontPixelSize

    readonly property bool periodic: Globals.BackendWrapper.methodPeriodic
    readonly property var grid: Globals.BackendWrapper.methodKpointGrid

    Components.LabelledField {
        text: qsTr('Spacing:')
        units: qsTr('Å⁻¹ (no 2π)')
        enabled: periodic
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: DoubleValidator { bottom: 0.001; top: 10; notation: DoubleValidator.StandardNotation }
            text: Globals.BackendWrapper.methodKpointSpacing
            onEditingFinished: Globals.BackendWrapper.methodSetKpointSpacing(parseFloat(text))
        }
    }

    Components.LabelledField {
        text: qsTr('Grid:')
        enabled: periodic

        Row {
            id: gridFields
            spacing: EaStyle.Sizes.fontPixelSize * 0.5

            Repeater {
                id: gridRepeater
                model: 3

                EaElements.TextField {
                    width: EaStyle.Sizes.fontPixelSize * 4
                    validator: IntValidator { bottom: 1; top: 100 }
                    text: grid.length === 3 ? grid[index] : ''
                    onEditingFinished: {
                        const counts = [0, 1, 2].map(i => parseInt(gridRepeater.itemAt(i).text))
                        if (counts.every(n => n > 0)) {
                            Globals.BackendWrapper.methodSetKpointGrid(counts[0], counts[1], counts[2])
                        }
                    }
                }
            }
        }
    }

    EaElements.Label {
        color: EaStyle.Colors.themeForegroundMinor
        text: periodic ? qsTr('Set from the spacing until edited; a new spacing resets it.') :
                         qsTr('For crystals; the sample is a molecule.')
    }
}
