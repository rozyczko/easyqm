import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// Coloured status badge, e.g. "● Completed". `status` is a backend ProjectStatus value.
Rectangle {
    id: pill

    property string status: 'new'
    property string text: ''

    readonly property color statusColor: {
        switch (status) {
        case 'completed': return EaStyle.Colors.green
        case 'running': return EaStyle.Colors.blue
        case 'failed': return EaStyle.Colors.red
        case 'stopped':
        case 'engine_not_found': return EaStyle.Colors.orange
        default: return EaStyle.Colors.themeForegroundMinor
        }
    }

    width: row.width + EaStyle.Sizes.fontPixelSize * 1.5
    height: EaStyle.Sizes.fontPixelSize * 1.6
    radius: height / 2
    color: Qt.alpha(statusColor, 0.15)

    Row {
        id: row

        anchors.centerIn: parent
        spacing: EaStyle.Sizes.fontPixelSize * 0.4

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: EaStyle.Sizes.fontPixelSize * 0.5
            height: width
            radius: width / 2
            color: pill.statusColor
        }

        EaElements.Label {
            anchors.verticalCenter: parent.verticalCenter
            text: pill.text
            color: pill.statusColor
        }
    }
}
