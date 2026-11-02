import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// What the viewer and the Atoms table show. Cell, boundary atoms, repeat and fractional
// coordinates apply to crystals only, the Z-matrix to molecules only.
Column {
    spacing: EaStyle.Sizes.fontPixelSize

    readonly property bool periodic: Globals.BackendWrapper.samplePeriodic
    readonly property var repeat: Globals.BackendWrapper.sampleViewRepeat

    Row {
        spacing: EaStyle.Sizes.fontPixelSize * 2

        EaElements.CheckBox {
            text: qsTr('Unit cell')
            enabled: periodic
            checked: Globals.ViewSettings.showCell
            onToggled: Globals.ViewSettings.showCell = checked
        }
        EaElements.CheckBox {
            text: qsTr('Boundary atoms')
            enabled: periodic
            checked: Globals.BackendWrapper.sampleViewBoundaryAtoms
            onToggled: Globals.BackendWrapper.sampleSetViewBoundaryAtoms(checked)
            ToolTip.text: qsTr('Also draw atoms on a face, edge or corner of the cells on the opposite side')
        }
        EaElements.CheckBox {
            text: qsTr('Axes')
            checked: Globals.ViewSettings.showAxes
            onToggled: Globals.ViewSettings.showAxes = checked
        }
    }

    Components.LabelledField {
        text: qsTr('Repeat:')
        enabled: periodic

        Row {
            id: repeatRow
            width: parent.width
            spacing: EaStyle.Sizes.fontPixelSize * 0.5

            Repeater {
                model: 3

                EaElements.SpinBox {
                    width: (repeatRow.width - 2 * repeatRow.spacing) / 3
                    from: 1
                    to: 4
                    // A refused repeat (too many atoms) re-reads the backend value.
                    value: repeat[index]
                    // EasyApp's +/- buttons call increase() and decrease(), which do not emit
                    // valueModified; a change that came from the backend is skipped.
                    onValueChanged: {
                        if (value === repeat[index]) {
                            return
                        }
                        const counts = Array.from(repeat)
                        counts[index] = value
                        Globals.BackendWrapper.sampleSetViewRepeat(counts[0], counts[1], counts[2])
                    }
                }
            }
        }
    }

    EaElements.Label {
        visible: periodic
        color: EaStyle.Colors.themeForegroundMinor
        text: qsTr('Cells along a × b × c; at most %1 atoms are drawn.').arg(Globals.BackendWrapper.sampleSceneAtomLimit)
    }

    // What the Atoms table shows: a molecule's Z-matrix or a crystal's fractional coordinates.
    Components.LabelledField {
        text: qsTr('Coordinates:')
        Components.ChoiceComboBox {
            width: parent.width
            choices: [
                { value: 'cartesian', label: qsTr('Cartesian (Å)') },
                periodic ? { value: 'fractional', label: qsTr('Fractional') } : { value: 'zmatrix', label: qsTr('Z-matrix (Å, °)') }
            ]
            value: Globals.BackendWrapper.sampleCoordinates
            onSelected: (value) => Globals.BackendWrapper.sampleSetCoordinates(value)
        }
    }
}
