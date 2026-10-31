import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// Engine card of the Method page: name, Found / Not found pill, version line and executable path.
Rectangle {
    id: card

    property string name: ''
    property bool found: false
    property string subtitle: ''
    property string path: ''

    width: EaStyle.Sizes.fontPixelSize * 28
    height: column.height + EaStyle.Sizes.fontPixelSize * 2
    radius: 4
    color: found ? Qt.alpha(EaStyle.Colors.blue, 0.06) : EaStyle.Colors.contentBackground
    border.width: 1
    border.color: found ? EaStyle.Colors.blue : EaStyle.Colors.appBorder

    Column {
        id: column

        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: EaStyle.Sizes.fontPixelSize
        width: parent.width - 2 * anchors.margins
        spacing: EaStyle.Sizes.fontPixelSize * 0.5

        Item {
            width: parent.width
            height: nameLabel.height

            EaElements.Label {
                id: nameLabel
                font.bold: true
                font.pixelSize: EaStyle.Sizes.fontPixelSize * 1.2
                text: card.name
            }

            StatusPill {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                status: card.found ? 'completed' : 'engine_not_found'
                text: card.found ? qsTr('Found') : qsTr('Not found')
            }
        }

        EaElements.Label {
            width: parent.width
            elide: Text.ElideRight
            text: card.subtitle
        }

        EaElements.Label {
            width: parent.width
            elide: Text.ElideMiddle
            font.family: EaStyle.Fonts.monoFontFamily
            color: EaStyle.Colors.themeForegroundMinor
            text: card.path !== '' ? card.path : qsTr('orca — not on PATH')
        }
    }
}
