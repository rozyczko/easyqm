import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


// The atoms as a table of the coordinates chosen under Display: Cartesian, fractional (a
// crystal) or the Z-matrix (a molecule).
Column {
    spacing: EaStyle.Sizes.fontPixelSize

    readonly property string coordinates: Globals.BackendWrapper.sampleCoordinates
    readonly property string zmatrixError: Globals.BackendWrapper.sampleZmatrixError

    Loader {
        visible: zmatrixError === ''
        source: coordinates === 'zmatrix' ? 'ZMatrixTable.qml' : 'CoordinatesTable.qml'
    }

    // A linear molecule of four atoms or more has no Z-matrix.
    EaElements.Label {
        visible: zmatrixError !== ''
        width: EaStyle.Sizes.sideBarContentWidth
        wrapMode: Text.WordWrap
        color: EaStyle.Colors.themeForegroundMinor
        text: zmatrixError || ' '
    }

    Item {
        width: EaStyle.Sizes.sideBarContentWidth
        height: buttons.height

        Row {
            id: buttons
            spacing: EaStyle.Sizes.fontPixelSize

            // Not while a job runs, as for the coordinate edits. At least one atom stays.
            EaElements.SideBarButton {
                width: EaStyle.Sizes.fontPixelSize * 9
                fontIcon: 'plus'
                text: qsTr('Add atom')
                enabled: !Globals.BackendWrapper.jobRunning
                onClicked: Globals.BackendWrapper.sampleAddAtom()
            }
            EaElements.SideBarButton {
                readonly property int selectedCount: Globals.BackendWrapper.sampleSelectedAtoms.length

                width: EaStyle.Sizes.fontPixelSize * 8
                fontIcon: 'minus'
                text: qsTr('Remove')
                ToolTip.text: qsTr('Remove selected atom(s)')
                enabled: !Globals.BackendWrapper.jobRunning &&
                         selectedCount > 0 && selectedCount < Globals.BackendWrapper.sampleAtomCount
                onClicked: Globals.BackendWrapper.sampleRemoveSelectedAtoms()
            }
        }

        EaElements.Label {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            color: EaStyle.Colors.themeForegroundMinor
            text: {
                const count = Globals.BackendWrapper.sampleAtomCount
                if (coordinates === 'fractional') {
                    return qsTr('%1 atoms · Fractional').arg(count)
                }
                if (coordinates === 'zmatrix') {
                    return qsTr('%1 atoms · Z-matrix · Å, °').arg(count)
                }
                return qsTr('%1 atoms · Cartesian · Å').arg(count)
            }
        }
    }
}
