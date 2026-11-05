import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Animations as EaAnimations
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


// The assistant chat: one conversation for the whole workflow, in a panel that slides in
// from the right edge between the app bar and the status bar. Non-modal: the page behind
// it stays live. Toggled from the app bar button and Ctrl+Shift+A.
Rectangle {
    id: panel

    property bool open: false

    // The gear in the header; the window opens the settings dialog.
    signal settingsRequested()

    // Page names for the backend context, in app bar tab order.
    readonly property var pageNames: ['home', 'project', 'sample', 'calculations', 'method', 'summary']
    readonly property bool busy: Globals.BackendWrapper.assistantBusy
    readonly property var approval: Globals.BackendWrapper.assistantApproval
    readonly property bool approvalPending: approval.id !== undefined

    function toggle() {
        open = !open
        if (open) {
            input.forceActiveFocus()
        }
    }

    function send(text) {
        if (busy || text.trim() === '') {
            return
        }
        Globals.BackendWrapper.assistantSend(text)
        input.clear()
        input.forceActiveFocus()
    }

    function showPage(page) {
        const index = pageNames.indexOf(page)
        if (index >= 0) {
            EaGlobals.Vars.appBarCurrentIndex = index
        }
    }

    // Model text is shown as Markdown without images, so the view loads no local or remote resource.
    function markdown(text) {
        return text.replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    }

    width: Math.round(EaStyle.Sizes.sideBarWidth * 0.85)
    x: open ? parent.width - width : parent.width
    Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    visible: x < parent.width

    color: EaStyle.Colors.contentBackground
    Behavior on color { EaAnimations.ThemeChange {} }

    // Panel border
    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: EaStyle.Sizes.borderThickness
        color: EaStyle.Colors.appBorder
    }

    // The backend answers against the page the user looks at.
    readonly property int currentPage: EaGlobals.Vars.appBarCurrentIndex
    onCurrentPageChanged: Globals.BackendWrapper.assistantSetPage(pageNames[currentPage] ?? 'home')
    Component.onCompleted: Globals.BackendWrapper.assistantSetPage(pageNames[currentPage] ?? 'home')

    Connections {
        target: Globals.BackendWrapper
        // New messages are shown at the end; a growing answer only while the view follows it.
        function onAssistantMessageCountChanged() { Qt.callLater(messages.positionViewAtEnd) }
        function onAssistantReplied() { Qt.callLater(messages.positionViewAtEnd) }
        function onAssistantStreamingTextChanged() {
            if (messages.atYEnd || messages.contentHeight <= messages.height) {
                Qt.callLater(messages.positionViewAtEnd)
            }
        }
        // The show_page tool.
        function onAssistantNavigateRequested(page) { panel.showPage(page) }
    }

    /////////
    // Header
    /////////

    Item {
        id: header

        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: EaStyle.Sizes.tableRowHeight + EaStyle.Sizes.fontPixelSize

        Row {
            anchors.left: parent.left
            anchors.leftMargin: EaStyle.Sizes.fontPixelSize * 1.25
            anchors.right: buttons.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: EaStyle.Sizes.fontPixelSize * 0.6

            EaElements.Label {
                anchors.verticalCenter: parent.verticalCenter
                font.family: EaStyle.Fonts.iconsFamily
                font.pixelSize: EaStyle.Sizes.fontPixelSize * 1.2
                color: EaStyle.Colors.themeAccent
                text: 'robot'
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - EaStyle.Sizes.fontPixelSize * 2
                EaElements.Label {
                    text: qsTr('Assistant')
                    font.bold: true
                }
                EaElements.Label {
                    width: parent.width
                    elide: Text.ElideRight
                    text: Globals.BackendWrapper.assistantConfigured ?
                              Globals.BackendWrapper.assistantModelName :
                              Globals.BackendWrapper.assistantModelName + ' · ' + qsTr('add an API key in the settings')
                    font.pixelSize: EaStyle.Sizes.fontPixelSize * 0.85
                    color: EaStyle.Colors.themeForegroundMinor
                }
            }
        }

        Row {
            id: buttons

            anchors.right: parent.right
            anchors.rightMargin: EaStyle.Sizes.fontPixelSize * 0.5
            anchors.verticalCenter: parent.verticalCenter

            EaElements.ToolButton {
                fontIcon: 'cog'
                ToolTip.text: qsTr('Assistant settings')
                onClicked: panel.settingsRequested()
            }
            EaElements.ToolButton {
                fontIcon: 'trash-alt'
                enabled: Globals.BackendWrapper.assistantMessageCount > 0 && !panel.busy
                ToolTip.text: qsTr('Clear the conversation')
                onClicked: Globals.BackendWrapper.assistantClear()
            }
            EaElements.ToolButton {
                fontIcon: 'times'
                ToolTip.text: qsTr('Close the assistant (Ctrl+Shift+A)')
                onClicked: panel.open = false
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: EaStyle.Sizes.borderThickness
            color: EaStyle.Colors.appBorder
        }
    }

    ///////////
    // Messages
    ///////////

    ListView {
        id: messages

        anchors.top: header.bottom
        anchors.bottom: approvalCard.visible ? approvalCard.top : suggestions.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: EaStyle.Sizes.fontPixelSize
        anchors.bottomMargin: EaStyle.Sizes.fontPixelSize * 0.5

        clip: true
        spacing: EaStyle.Sizes.fontPixelSize * 0.75
        boundsBehavior: Flickable.StopAtBounds

        model: Globals.BackendWrapper.assistantMessages
        delegate: Loader {
            width: messages.width
            sourceComponent: modelData.role === 'action' ? actionRow :
                             modelData.role === 'notice' || modelData.role === 'error' ? noticeRow :
                             bubble
            property var entry: modelData
        }

        // The answer being written, and what the assistant is doing.
        footer: Column {
            width: messages.width
            topPadding: visible ? messages.spacing : 0
            spacing: messages.spacing
            visible: panel.busy || Globals.BackendWrapper.assistantStreamingText !== ''

            Loader {
                width: parent.width
                active: Globals.BackendWrapper.assistantStreamingText !== ''
                visible: active
                sourceComponent: bubble
                property var entry: ({ role: 'assistant', text: Globals.BackendWrapper.assistantStreamingText })
            }

            Row {
                visible: panel.busy
                spacing: EaStyle.Sizes.fontPixelSize * 0.5

                EaElements.Label {
                    font.family: EaStyle.Fonts.iconsFamily
                    color: EaStyle.Colors.themeForegroundMinor
                    text: 'robot'
                }
                EaElements.Label {
                    id: statusLabel
                    property int dots: 1
                    color: EaStyle.Colors.themeForegroundMinor
                    text: (Globals.BackendWrapper.assistantStatus || qsTr('Thinking')) + '.'.repeat(dots)
                    Timer {
                        running: panel.busy
                        interval: 350
                        repeat: true
                        onTriggered: statusLabel.dots = statusLabel.dots % 3 + 1
                    }
                }
            }
        }

        ScrollBar.vertical: EaElements.ScrollBar {}

        // Empty state
        Column {
            anchors.centerIn: parent
            width: parent.width * 0.8
            spacing: EaStyle.Sizes.fontPixelSize * 0.5
            visible: Globals.BackendWrapper.assistantMessageCount === 0 && !panel.busy

            EaElements.Label {
                anchors.horizontalCenter: parent.horizontalCenter
                font.family: EaStyle.Fonts.iconsFamily
                font.pixelSize: EaStyle.Sizes.fontPixelSize * 2.5
                color: EaStyle.Colors.themeForegroundDisabled
                text: 'comment-dots'
            }
            EaElements.Label {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: EaStyle.Colors.themeForegroundMinor
                text: qsTr('Ask about the loaded structure, the method, a running job or the results, ' +
                           'or ask for changes: "load toluene.xyz and optimise it with def2-SVP".')
            }
        }
    }

    ////////////////
    // Approval card
    ////////////////

    Rectangle {
        id: approvalCard

        visible: panel.approvalPending
        anchors.bottom: suggestions.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: EaStyle.Sizes.fontPixelSize
        anchors.bottomMargin: EaStyle.Sizes.fontPixelSize * 0.5
        height: visible ? cardColumn.height + EaStyle.Sizes.fontPixelSize * 1.5 : 0

        radius: 4
        color: EaStyle.Colors.mainContentBackground
        border.width: 1
        border.color: EaStyle.Colors.themeAccent

        Keys.onEscapePressed: Globals.BackendWrapper.assistantAnswerApproval(panel.approval.id, false)

        Column {
            id: cardColumn

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.margins: EaStyle.Sizes.fontPixelSize * 0.75
            spacing: EaStyle.Sizes.fontPixelSize * 0.4

            EaElements.Label {
                width: parent.width
                wrapMode: Text.WordWrap
                font.bold: true
                text: panel.approval.title ?? ''
            }
            Repeater {
                model: panel.approval.detail ?? []
                EaElements.Label {
                    width: cardColumn.width
                    wrapMode: Text.WrapAnywhere
                    color: EaStyle.Colors.themeForegroundMinor
                    text: modelData
                }
            }
            Row {
                anchors.right: parent.right
                spacing: EaStyle.Sizes.fontPixelSize * 0.5
                EaElements.Button {
                    text: qsTr('Cancel')
                    onClicked: Globals.BackendWrapper.assistantAnswerApproval(panel.approval.id, false)
                }
                EaElements.Button {
                    text: panel.approval.confirm ?? qsTr('Allow')
                    onClicked: Globals.BackendWrapper.assistantAnswerApproval(panel.approval.id, true)
                }
            }
        }
    }

    //////////////
    // Suggestions
    //////////////

    Flow {
        id: suggestions

        anchors.bottom: inputBox.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: EaStyle.Sizes.fontPixelSize
        anchors.bottomMargin: EaStyle.Sizes.fontPixelSize * 0.5
        spacing: EaStyle.Sizes.fontPixelSize * 0.4
        visible: !panel.busy
        height: visible ? implicitHeight : 0

        Repeater {
            model: Globals.BackendWrapper.assistantSuggestions
            delegate: SuggestionChip {
                text: modelData
                onClicked: panel.send(text)
            }
        }
    }

    ////////
    // Input
    ////////

    Rectangle {
        id: inputBox

        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: EaStyle.Sizes.fontPixelSize
        height: Math.min(input.implicitHeight, EaStyle.Sizes.fontPixelSize * 8) + 2

        radius: 4
        color: EaStyle.Colors.textViewBackground
        border.width: 1
        border.color: input.activeFocus ? EaStyle.Colors.themeAccent : EaStyle.Colors.appBorder
        Behavior on border.color { EaAnimations.ThemeChange {} }

        Flickable {
            anchors.fill: parent
            anchors.margins: 1
            anchors.rightMargin: sendButton.width + EaStyle.Sizes.fontPixelSize * 0.5
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            TextArea.flickable: EaElements.TextArea {
                id: input

                enabled: !panel.approvalPending
                placeholderText: qsTr('Ask the assistant… (Enter to send, Shift+Enter for a new line)')
                wrapMode: TextEdit.Wrap
                padding: EaStyle.Sizes.fontPixelSize * 0.75
                backgroundOpacity: 0

                Keys.onReturnPressed: (event) => {
                    if (event.modifiers & Qt.ShiftModifier) {
                        event.accepted = false  // a new line
                    } else {
                        panel.send(text)
                    }
                }
                Keys.onEnterPressed: (event) => Keys.returnPressed(event)
            }

            ScrollBar.vertical: EaElements.ScrollBar {}
        }

        // Send, or stop the answer being written; a running engine job is not stopped.
        EaElements.ToolButton {
            id: sendButton

            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: EaStyle.Sizes.fontPixelSize * 0.25
            fontIcon: panel.busy ? 'stop' : 'paper-plane'
            highlighted: enabled
            enabled: panel.busy ? Globals.BackendWrapper.assistantStatus !== 'Cancelling' : input.text.trim() !== ''
            ToolTip.text: panel.busy ? qsTr('Stop the answer') : qsTr('Send')
            onClicked: panel.busy ? Globals.BackendWrapper.assistantCancel() : panel.send(input.text)
        }
    }

    /////////////
    // Components
    /////////////

    // The user's message in an accent bubble on the right, the assistant's as Markdown on the
    // left under a robot icon. `entry` comes from the Loader.
    Component {
        id: bubble

        Item {
            id: bubbleItem

            readonly property var entry: parent ? parent.entry : ({ role: '', text: '' })
            readonly property bool fromUser: entry.role === 'user'
            readonly property int maxWidth: Math.round(width * 0.85)

            width: parent ? parent.width : 0
            height: box.height

            // Unwrapped width of the text, to size a user bubble to short messages.
            Text {
                id: measure
                visible: false
                text: bubbleItem.entry.text
                font.family: EaStyle.Fonts.fontFamily
                font.pixelSize: EaStyle.Sizes.fontPixelSize
            }

            EaElements.Label {
                id: icon
                visible: !bubbleItem.fromUser
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.topMargin: EaStyle.Sizes.fontPixelSize * 0.6
                font.family: EaStyle.Fonts.iconsFamily
                color: EaStyle.Colors.themeAccent
                text: 'robot'
            }

            Rectangle {
                id: box

                anchors.right: bubbleItem.fromUser ? parent.right : undefined
                anchors.left: bubbleItem.fromUser ? undefined : icon.right
                anchors.leftMargin: EaStyle.Sizes.fontPixelSize * 0.6
                width: bubbleItem.fromUser ?
                           Math.min(measure.implicitWidth + 2 * label.padding, bubbleItem.maxWidth) :
                           bubbleItem.width - icon.width - anchors.leftMargin
                height: label.implicitHeight

                radius: EaStyle.Sizes.fontPixelSize * 0.75
                color: bubbleItem.fromUser ? EaStyle.Colors.themeRowHighlight : 'transparent'
                Behavior on color { EaAnimations.ThemeChange {} }

                EaElements.Label {
                    id: label
                    width: parent.width
                    padding: bubbleItem.fromUser ? EaStyle.Sizes.fontPixelSize * 0.6 : EaStyle.Sizes.fontPixelSize * 0.3
                    wrapMode: Text.WordWrap
                    textFormat: bubbleItem.fromUser ? Text.PlainText : Text.MarkdownText
                    text: bubbleItem.fromUser ? bubbleItem.entry.text : panel.markdown(bubbleItem.entry.text)
                }
            }
        }
    }

    // What a tool did: green tick or orange cross, the result, and a link to the page it changed.
    Component {
        id: actionRow

        Row {
            id: actionItem

            readonly property var entry: parent ? parent.entry : ({ ok: true, text: '', page: '' })

            width: parent ? parent.width : 0
            spacing: EaStyle.Sizes.fontPixelSize * 0.5
            leftPadding: EaStyle.Sizes.fontPixelSize * 1.6

            EaElements.Label {
                id: actionIcon
                font.family: EaStyle.Fonts.iconsFamily
                font.pixelSize: EaStyle.Sizes.fontPixelSize * 0.9
                color: actionItem.entry.ok ? EaStyle.Colors.green : EaStyle.Colors.orange
                text: actionItem.entry.ok ? 'check-circle' : 'exclamation-circle'
            }
            EaElements.Label {
                width: parent.width - parent.leftPadding - actionIcon.width - showLink.width - 2 * parent.spacing
                wrapMode: Text.WordWrap
                font.pixelSize: EaStyle.Sizes.fontPixelSize * 0.9
                color: EaStyle.Colors.themeForegroundMinor
                text: actionItem.entry.text
            }
            EaElements.Label {
                id: showLink
                visible: actionItem.entry.page !== ''
                width: visible ? implicitWidth : 0
                font.pixelSize: EaStyle.Sizes.fontPixelSize * 0.9
                color: EaStyle.Colors.link
                text: qsTr('Show')
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    onTapped: {
                        panel.showPage(actionItem.entry.page)
                        panel.open = false
                    }
                }
            }
        }
    }

    // A note from the application: disclosure, limits, cancellation, errors.
    Component {
        id: noticeRow

        EaElements.Label {
            id: noticeItem

            readonly property var entry: parent ? parent.entry : ({ role: '', text: '' })

            width: parent ? parent.width : 0
            leftPadding: EaStyle.Sizes.fontPixelSize * 1.6
            wrapMode: Text.WordWrap
            font.pixelSize: EaStyle.Sizes.fontPixelSize * 0.9
            font.italic: noticeItem.entry.role === 'notice'
            color: noticeItem.entry.role === 'error' ? EaStyle.Colors.red : EaStyle.Colors.themeForegroundMinor
            text: noticeItem.entry.text
        }
    }

    // A suggested question; clicking it sends it.
    component SuggestionChip: Rectangle {
        id: chip

        property alias text: chipLabel.text
        signal clicked()

        width: chipLabel.implicitWidth + EaStyle.Sizes.fontPixelSize * 1.2
        height: EaStyle.Sizes.fontPixelSize * 1.9
        radius: height / 2
        color: chipHover.hovered ? EaStyle.Colors.themeRowHovered : 'transparent'
        border.width: 1
        border.color: chipHover.hovered ? EaStyle.Colors.themeAccent : EaStyle.Colors.appBorder
        Behavior on color { EaAnimations.ThemeChange {} }

        EaElements.Label {
            id: chipLabel
            anchors.centerIn: parent
            font.pixelSize: EaStyle.Sizes.fontPixelSize * 0.9
            color: chipHover.hovered ? EaStyle.Colors.themeAccent : EaStyle.Colors.themeForeground
        }

        HoverHandler {
            id: chipHover
            cursorShape: Qt.PointingHandCursor
        }
        TapHandler {
            onTapped: chip.clicked()
        }
    }
}
