import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui as Gui
import Gui.Components as Components
import Gui.Globals as Globals

EaComponents.ApplicationWindow {
    id: applicationWindow

    ///////////////////
    // APPLICATION BAR
    ///////////////////

    // Left group of application bar tool buttons
    appBarLeftButtons: [

        EaElements.ToolButton {
            highlighted: true
            fontIcon: 'save'
            enabled: Globals.BackendWrapper.projectCreated && Globals.BackendWrapper.projectHasUnsavedChanges
            ToolTip.text: qsTr('Save current state of the project')
            onClicked: Globals.BackendWrapper.projectSave()
        },

        // Not while a job runs: stop it on the Method page first.
        EaElements.ToolButton {
            fontIcon: 'undo'
            enabled: !Globals.BackendWrapper.jobRunning
            ToolTip.text: qsTr('Reset to initial state without project, sample and calculations')
            onClicked: Globals.BackendWrapper.edited ? resetDialog.open() : applicationWindow.resetApplication()
        }
    ]

    // Everything back to start-up, shown from the Home page.
    function resetApplication() {
        Globals.BackendWrapper.reset()
        EaGlobals.Vars.appBarCurrentIndex = 0
    }

    // Asked only when the reset would discard work (BackendWrapper.edited).
    EaElements.Dialog {
        id: resetDialog

        modal: true
        title: qsTr('Reset EasyQM?')
        standardButtons: Dialog.Ok | Dialog.Cancel
        closePolicy: Popup.CloseOnEscape

        onAccepted: applicationWindow.resetApplication()
        Component.onCompleted: standardButton(Dialog.Ok).text = qsTr('Reset')

        // Fixed implicit size, as in Components.MessageDialog: the wrapped label's implicit
        // width is that of its unwrapped text, and the dialog would take it.
        Item {
            implicitWidth: EaStyle.Sizes.sideBarContentWidth
            implicitHeight: resetMessage.implicitHeight

            EaElements.Label {
                id: resetMessage
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr('The project is closed. Changes that are not in a saved ' +
                           'project file are lost, including the sample and method settings.')
            }
        }
    }

    // Right group of application bar tool buttons
    appBarRightButtons: [

        // The assistant panel (Components.AssistantPanel below); checked while it is open.
        EaElements.ToolButton {
            fontIcon: 'robot'
            checked: assistantPanel.open
            ToolTip.text: assistantPanel.open ?
                              qsTr('Close the assistant (Ctrl+Shift+A)') :
                              qsTr('Open the assistant (Ctrl+Shift+A)')
            onClicked: assistantPanel.toggle()
        },

        // For now the only EasyQM preferences are the assistant's.
        EaElements.ToolButton {
            fontIcon: 'cog'
            ToolTip.text: qsTr('Assistant settings')
            onClicked: assistantSettingsDialog.open()
        },

        EaElements.ToolButton {
            fontIcon: 'question-circle'
            ToolTip.text: qsTr('Get online help')
        },

        EaElements.ToolButton {
            fontIcon: 'bug'
            ToolTip.text: qsTr('Report a bug or issue')
        }
    ]

    // Central group of application bar page buttons (workflow tabs)
    appBarCentralTabs.contentData: [

        // Home page
        EaElements.AppBarTabButton {
            fontIcon: 'home'
            text: qsTr('Home')
            ToolTip.text: qsTr('Home')
        },

        // Project page
        EaElements.AppBarTabButton {
            fontIcon: 'archive'
            text: qsTr('Project')
            ToolTip.text: qsTr('Project description page')
        },

        // Sample page
        EaElements.AppBarTabButton {
            fontIcon: 'atom'
            text: qsTr('Sample')
            ToolTip.text: qsTr('Molecule or crystal structure page')
        },

        // Calculations page
        EaElements.AppBarTabButton {
            fontIcon: 'tasks'
            text: qsTr('Calculations')
            ToolTip.text: qsTr('Calculation types to perform page')
        },

        // Method page
        EaElements.AppBarTabButton {
            fontIcon: 'calculator'
            text: qsTr('Method')
            ToolTip.text: qsTr('Engine, level of theory and run control page')
        },

        // Summary page
        EaElements.AppBarTabButton {
            fontIcon: 'clipboard-list'
            text: qsTr('Summary')
            ToolTip.text: qsTr('Summary of the results')
        }
    ]

    //////////////////////////////////
    // APP PAGES (MAIN AREA + SIDEBAR)
    //////////////////////////////////

    // Pages for the tab buttons described above
    contentArea: [
        Loader { source: 'Pages/Home/Layout.qml' },
        Loader { source: 'Pages/Project/Layout.qml' },
        Loader { source: 'Pages/Sample/Layout.qml' },
        Loader { source: 'Pages/Calculations/Layout.qml' },
        Loader { source: 'Pages/Method/Layout.qml' },
        Loader { source: 'Pages/Summary/Layout.qml' }
    ]

    /////////////
    // STATUS BAR
    /////////////

    statusBar: Gui.StatusBar {}

    //////////////////
    // ASSISTANT PANEL
    //////////////////

    // Slides in over the right of the current page, between the app bar and the status bar.
    // One conversation for the whole workflow, so it lives here and not in a page.
    Components.AssistantPanel {
        id: assistantPanel
        objectName: 'assistantPanel'

        anchors.top: parent.top
        anchors.topMargin: EaStyle.Sizes.appBarHeight
        anchors.bottom: parent.bottom
        anchors.bottomMargin: EaStyle.Sizes.statusBarHeight
        z: 10

        onSettingsRequested: assistantSettingsDialog.open()
    }

    Components.AssistantSettingsDialog {
        id: assistantSettingsDialog
        objectName: 'assistantSettingsDialog'
    }

    Shortcut {
        sequence: 'Ctrl+Shift+A'
        context: Qt.ApplicationShortcut
        onActivated: assistantPanel.toggle()
    }

    Component.onCompleted: {
        Globals.References.applicationWindow = applicationWindow
        console.debug(`Application window loaded ::: ${this}`)
    }
    Component.onDestruction: console.debug(`Application window destroyed ::: ${this}`)
}
