import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Bands along the high-symmetry path of the sample's lattice, for crystals (Quantum ESPRESSO).
Column {
    readonly property bool periodic: Globals.BackendWrapper.samplePeriodic

    spacing: EaStyle.Sizes.fontPixelSize

    EaElements.Label {
        visible: !periodic
        color: EaStyle.Colors.themeForegroundMinor
        text: qsTr('For periodic systems only.')
    }

    Components.LabelledField {
        visible: periodic
        text: qsTr('Lattice:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.calculationsBandsLattice
        }
    }

    Components.LabelledField {
        visible: periodic
        text: qsTr('Path:')
        EaElements.TextField {
            width: parent.width
            readOnly: true
            horizontalAlignment: TextInput.AlignLeft
            text: Globals.BackendWrapper.calculationsBandsPath
            ToolTip.text: qsTr('High-symmetry points after Setyawan and Curtarolo; | is a jump between two points.')
            ToolTip.visible: hovered && EaGlobals.Vars.showToolTips
        }
    }

    Components.LabelledField {
        text: qsTr('Path points:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 10; top: 1000 }
            text: Globals.BackendWrapper.calculationsBandsPoints
            onEditingFinished: Globals.BackendWrapper.calculationsSetBandsPoints(parseInt(text))
            ToolTip.text: qsTr('About this many in all, spread over the lines of the path by their length.')
            ToolTip.visible: hovered && EaGlobals.Vars.showToolTips
        }
    }

    Components.LabelledField {
        text: qsTr('Empty bands:')
        EaElements.TextField {
            width: parent.width
            horizontalAlignment: TextInput.AlignLeft
            validator: IntValidator { bottom: 0; top: 200 }
            text: Globals.BackendWrapper.calculationsBandsEmptyBands
            onEditingFinished: Globals.BackendWrapper.calculationsSetBandsEmptyBands(parseInt(text))
            ToolTip.text: qsTr('Conduction bands computed above the filled ones.')
            ToolTip.visible: hovered && EaGlobals.Vars.showToolTips
        }
    }

    EaElements.Label {
        visible: periodic && Globals.BackendWrapper.calculationsBandsFoldedReason !== ''
        width: parent.width
        wrapMode: Text.WordWrap
        color: EaStyle.Colors.orange
        text: Globals.BackendWrapper.calculationsBandsFoldedReason
    }
}
