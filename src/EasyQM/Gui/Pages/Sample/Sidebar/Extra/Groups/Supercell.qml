import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Replaces a crystal's cell by a block of cells along a, b and c, atoms included: the
// structure itself changes, unlike Display's repeat, which only draws more cells. Disabled
// for a molecule, and while a job runs (the job was set up for the current cell).
Column {
    id: group

    spacing: EaStyle.Sizes.fontPixelSize
    enabled: periodic && !Globals.BackendWrapper.jobRunning

    readonly property bool periodic: Globals.BackendWrapper.samplePeriodic
    readonly property int atomLimit: Globals.BackendWrapper.sampleSceneAtomLimit
    // Cells along a, b, c, as set in the fields; back to one cell after a build or a load.
    property var counts: [1, 1, 1]
    readonly property int cellCount: counts[0] * counts[1] * counts[2]
    readonly property int atomCount: Globals.BackendWrapper.sampleAtomCount * cellCount
    readonly property bool tooLarge: atomCount > atomLimit

    Connections {
        target: Globals.BackendWrapper
        function onSampleStructureLoaded() { group.counts = [1, 1, 1] }
    }

    Components.LabelledField {
        text: qsTr('Cells:')

        Row {
            id: countsRow
            width: parent.width
            spacing: EaStyle.Sizes.fontPixelSize * 0.5

            Repeater {
                model: 3

                EaElements.SpinBox {
                    width: (countsRow.width - 2 * countsRow.spacing) / 3
                    from: 1
                    to: Globals.BackendWrapper.sampleSupercellMax
                    value: group.counts[index]
                    // EasyApp's +/- buttons call increase() and decrease(), which do not emit
                    // valueModified; a value that came from `counts` is skipped.
                    onValueChanged: {
                        if (value === group.counts[index]) {
                            return
                        }
                        const counts = Array.from(group.counts)
                        counts[index] = value
                        group.counts = counts
                    }
                }
            }
        }
    }

    Item {
        width: EaStyle.Sizes.sideBarContentWidth
        height: buildButton.height

        EaElements.SideBarButton {
            id: buildButton
            width: EaStyle.Sizes.fontPixelSize * 12
            fontIcon: 'th'
            text: qsTr('Build supercell')
            enabled: group.cellCount > 1 && !group.tooLarge
            onClicked: {
                Globals.BackendWrapper.sampleMakeSupercell(group.counts[0], group.counts[1], group.counts[2])
                group.counts = [1, 1, 1]
            }
        }

        EaElements.Label {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: group.periodic
            color: group.tooLarge ? EaStyle.Colors.red : EaStyle.Colors.themeForegroundMinor
            text: group.tooLarge ?
                      qsTr('%1 atoms: more than %2').arg(group.atomCount).arg(group.atomLimit) :
                      qsTr('%1 atoms').arg(group.atomCount)
        }
    }

    EaElements.Label {
        width: EaStyle.Sizes.sideBarContentWidth
        wrapMode: Text.WordWrap
        color: EaStyle.Colors.themeForegroundMinor
        text: group.periodic ?
                  qsTr('The cell and its atoms are replaced; the space group is found again from them.') :
                  qsTr('A molecule has no cell to repeat.')
    }
}
