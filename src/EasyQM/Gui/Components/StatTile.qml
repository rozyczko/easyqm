import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// One headline number of the Summary page: title, value, one or two lines of detail.
// `tone` colours the value: '' plain, 'good', 'bad' or 'warning'.
Rectangle {
    id: tile

    property string title: ''
    property string value: ''
    property string detail: ''
    property string tone: ''

    readonly property int padding: EaStyle.Sizes.fontPixelSize

    height: EaStyle.Sizes.fontPixelSize * 7.5
    radius: 2
    color: EaStyle.Colors.contentBackground
    border.width: 1
    border.color: EaStyle.Colors.appBorder

    Column {
        anchors.fill: parent
        anchors.margins: tile.padding
        spacing: EaStyle.Sizes.fontPixelSize * 0.2

        EaElements.Label {
            width: parent.width
            elide: Text.ElideRight
            color: EaStyle.Colors.themeForegroundMinor
            text: tile.title
        }
        EaElements.Label {
            width: parent.width
            elide: Text.ElideRight
            font.family: EaStyle.Fonts.secondFontFamily
            font.pixelSize: EaStyle.Sizes.fontPixelSize * 1.9
            font.weight: Font.ExtraLight
            color: {
                switch (tile.tone) {
                case 'good': return EaStyle.Colors.green
                case 'bad': return EaStyle.Colors.red
                case 'warning': return EaStyle.Colors.orange
                default: return EaStyle.Colors.themeForeground
                }
            }
            text: tile.value
        }
        EaElements.Label {
            visible: tile.detail !== ''
            width: parent.width
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            font.pixelSize: EaStyle.Sizes.fontPixelSize * 0.9
            color: EaStyle.Colors.themeForegroundMinor
            text: tile.detail
        }
    }
}
