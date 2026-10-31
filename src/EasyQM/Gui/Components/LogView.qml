import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// Read-only monospace view of an engine output file that grows while the job runs.
// `text` is the whole output (assigning it replaces the view); `append()` adds what the
// engine wrote since. The view follows the end unless the user has scrolled up.
Rectangle {
    id: view

    property string text: ''
    property alias placeholderText: area.placeholderText

    // Characters of `text` the view holds; the view may store line ends differently.
    property int shownLength: 0

    function append(chunk) {
        const following = flick.atYEnd || flick.contentHeight <= flick.height
        area.insert(area.length, chunk)
        shownLength += chunk.length
        if (following) {
            Qt.callLater(scrollToEnd)
        }
    }

    function scrollToEnd() {
        flick.contentY = Math.max(0, flick.contentHeight - flick.height)
    }

    // A complete output the view already holds through `append` leaves the view (and the
    // user's scroll position) alone.
    onTextChanged: {
        if (text.length !== shownLength || text.length === 0) {
            area.text = text
            shownLength = text.length
            Qt.callLater(scrollToEnd)
        }
    }

    radius: 4
    color: EaStyle.Colors.contentBackground
    border.width: 1
    border.color: EaStyle.Colors.appBorder
    clip: true

    Flickable {
        id: flick

        anchors.fill: parent
        anchors.margins: 1
        boundsBehavior: Flickable.StopAtBounds

        TextArea.flickable: EaElements.TextArea {
            id: area

            readOnly: true
            wrapMode: TextEdit.NoWrap
            textFormat: TextEdit.PlainText
            font.family: EaStyle.Fonts.monoFontFamily
            backgroundOpacity: 0
        }

        ScrollBar.vertical: EaElements.ScrollBar {}
        ScrollBar.horizontal: EaElements.ScrollBar {}
    }
}
