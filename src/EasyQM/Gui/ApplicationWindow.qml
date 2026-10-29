import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui as Gui
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
            ToolTip.text: qsTr('Save current state of the project')
        },

        EaElements.ToolButton {
            fontIcon: 'undo'
            ToolTip.text: qsTr('Reset to initial state without project, sample and calculations')
        }
    ]

    // Right group of application bar tool buttons
    appBarRightButtons: [

        EaElements.ToolButton {
            fontIcon: 'cog'
            ToolTip.text: qsTr('Application preferences')
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

    Component.onCompleted: {
        Globals.References.applicationWindow = applicationWindow
        console.debug(`Application window loaded ::: ${this}`)
    }
    Component.onDestruction: console.debug(`Application window destroyed ::: ${this}`)
}
