import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
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
    Components.MessageDialog { id: projectErrorDialog }

    Connections {
        target: Globals.BackendWrapper
        function onProjectLoadError(message) { projectErrorDialog.show(qsTr('Project could not be opened'), message) }
        function onProjectSaveError(message) { projectErrorDialog.show(qsTr('Project could not be saved'), message) }
    }
}
