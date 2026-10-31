import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    Grid {
        columns: 2
        spacing: EaStyle.Sizes.fontPixelSize

        EaElements.SideBarButton {
            fontIcon: 'plus-circle'
            text: qsTr('Create a new project')
            onClicked: EaGlobals.Vars.showProjectDescriptionDialog = true

            Loader { source: '../Popups/CreateProject.qml' }
        }

        EaElements.SideBarButton {
            fontIcon: 'upload'
            text: qsTr('Open an existing project')
            onClicked: openProjectDialog.open()
        }
    }

    EaElements.Label {
        width: EaStyle.Sizes.sideBarContentWidth
        wrapMode: Text.WordWrap
        color: EaStyle.Colors.themeForegroundMinor
        text: qsTr('Without a project, results are kept in a temporary folder and can be saved later (Continue).')
    }

    FolderDialog {
        id: openProjectDialog
        title: qsTr('Open a project folder')
        onAccepted: Globals.BackendWrapper.projectLoad(selectedFolder)
    }

    // Load and save failures reported by the backend
    EaElements.Dialog {
        id: projectErrorDialog
        standardButtons: Dialog.Ok
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        property string message: ''

        // Fixed implicit size, so the wrapped label's size does not feed back into the dialog's.
        Item {
            implicitWidth: EaStyle.Sizes.sideBarContentWidth
            implicitHeight: messageLabel.implicitHeight

            EaElements.Label {
                id: messageLabel
                width: parent.width
                wrapMode: Text.WordWrap
                text: projectErrorDialog.message
            }
        }
    }

    Connections {
        target: Globals.BackendWrapper
        function onProjectLoadError(message) { showError(qsTr('Project could not be opened'), message) }
        function onProjectSaveError(message) { showError(qsTr('Project could not be saved'), message) }
    }

    function showError(title, message) {
        projectErrorDialog.title = title
        projectErrorDialog.message = message
        projectErrorDialog.open()
    }
}
