import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// Sidebar row "Label:  [control]  unit". The control is the child item; give it `width: parent.width`.
Row {
    id: root

    property alias text: label.text
    property string units: ''
    default property alias control: slot.data

    readonly property int labelWidth: EaStyle.Sizes.fontPixelSize * 7
    readonly property int fieldWidth: EaStyle.Sizes.sideBarContentWidth - labelWidth - spacing

    spacing: EaStyle.Sizes.fontPixelSize

    EaElements.Label {
        id: label
        width: root.labelWidth
        anchors.verticalCenter: parent.verticalCenter
    }

    Item {
        id: slot
        width: root.fieldWidth - (unitsLabel.visible ? unitsLabel.width + root.spacing : 0)
        height: childrenRect.height
    }

    EaElements.Label {
        id: unitsLabel
        visible: root.units !== ''
        anchors.verticalCenter: parent.verticalCenter
        color: EaStyle.Colors.themeForegroundMinor
        text: root.units
    }
}
