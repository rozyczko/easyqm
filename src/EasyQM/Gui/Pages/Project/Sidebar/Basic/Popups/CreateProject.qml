import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


EaComponents.ProjectDescriptionDialog {

    visible: EaGlobals.Vars.showProjectDescriptionDialog
    defaultProjectParentDirectory: Globals.BackendWrapper.projectParentDirectory

    onClosed: EaGlobals.Vars.showProjectDescriptionDialog = false

    // Runs after the base dialog has stored the composed location in `projectLocation`.
    onAccepted: {
        Globals.BackendWrapper.projectSetName(projectName)
        Globals.BackendWrapper.projectSetDescription(projectDescription)
        Globals.BackendWrapper.projectSetLocation(projectLocation)
        Globals.BackendWrapper.projectCreate()
    }

    Component.onCompleted: {
        projectName = Globals.BackendWrapper.projectName
        projectDescription = Globals.BackendWrapper.projectDescription
    }

}
