import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Levels on a denser k-point grid, with tetrahedra, for crystals (Quantum ESPRESSO). The
// broadening the curve is drawn with is set on the Summary page, without a new job.
Column {
    readonly property var grid: Globals.BackendWrapper.methodKpointGrid
    readonly property int factor: Globals.BackendWrapper.calculationsDosGridFactor

    spacing: EaStyle.Sizes.fontPixelSize

    Components.LabelledField {
        text: qsTr('Grid factor:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 1; top: 8 }
            text: factor
            onEditingFinished: Globals.BackendWrapper.calculationsSetDosGridFactor(parseInt(text))
            ToolTip.text: qsTr('The SCF k-point grid of the Method page, times this along each axis.')
            ToolTip.visible: hovered && EaGlobals.Vars.showToolTips
        }
    }

    Components.LabelledField {
        text: qsTr('Empty bands:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 0; top: 200 }
            text: Globals.BackendWrapper.calculationsDosEmptyBands
            onEditingFinished: Globals.BackendWrapper.calculationsSetDosEmptyBands(parseInt(text))
            ToolTip.text: qsTr('Conduction bands computed above the filled ones.')
            ToolTip.visible: hovered && EaGlobals.Vars.showToolTips
        }
    }

    EaElements.Label {
        visible: grid.length === 3
        color: EaStyle.Colors.themeForegroundMinor
        text: grid.length === 3 ?
                  qsTr('DOS grid: %1 × %2 × %3 k-points').arg(grid[0] * factor).arg(grid[1] * factor).arg(grid[2] * factor) : ''
    }
}
