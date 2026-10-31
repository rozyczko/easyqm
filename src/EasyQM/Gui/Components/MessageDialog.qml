import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// A dialog with a title, a wrapped message and an OK button, for errors reported by the backend.
EaElements.Dialog {
    id: dialog

    property string message: ''

    function show(title, message) {
        dialog.title = title
        dialog.message = message
        open()
    }

    standardButtons: Dialog.Ok
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    // Fixed implicit size, so the wrapped label's size does not feed back into the dialog's.
    Item {
        implicitWidth: EaStyle.Sizes.sideBarContentWidth
        implicitHeight: messageLabel.implicitHeight

        EaElements.Label {
            id: messageLabel
            width: parent.width
            wrapMode: Text.WordWrap
            text: dialog.message
        }
    }
}
