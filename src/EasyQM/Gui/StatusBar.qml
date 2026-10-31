import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Globals as EaGlobals
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


EaElements.StatusBar {

    visible: EaGlobals.Vars.appBarCurrentIndex !== 0

    EaElements.StatusBarItem {
        keyIcon: 'archive'
        keyText: qsTr('Project')
        valueText: Globals.BackendWrapper.projectCreated ? Globals.BackendWrapper.projectName : ''
        ToolTip.text: qsTr('Current project')
    }

    EaElements.StatusBarItem {
        keyIcon: 'atom'
        keyText: qsTr('Sample')
        valueText: Globals.BackendWrapper.projectSampleName
        ToolTip.text: qsTr('Sample formula')
    }

    EaElements.StatusBarItem {
        keyIcon: 'tasks'
        keyText: qsTr('Calculations')
        valueText: Globals.BackendWrapper.calculationsSelectedCount > 0 ?
                       qsTr('%1 selected').arg(Globals.BackendWrapper.calculationsSelectedCount) :
                       ''
        ToolTip.text: qsTr('Calculations to perform')
    }

    EaElements.StatusBarItem {
        keyIcon: 'calculator'
        keyText: qsTr('Engine')
        valueText: Globals.BackendWrapper.methodEngineFound ?
                       `${Globals.BackendWrapper.methodEngineName} ${Globals.BackendWrapper.methodEngineVersion}`.trim() :
                       Globals.BackendWrapper.projectEngine
        ToolTip.text: qsTr('Current calculation engine')
    }

    EaElements.StatusBarItem {
        keyIcon: 'play-circle'
        keyText: qsTr('Job')
        valueText: Globals.BackendWrapper.projectStatus === 'new' ? '' : Globals.BackendWrapper.projectStatusLabel
        ToolTip.text: qsTr('Job state')
    }

    EaElements.StatusBarItem {
        keyIcon: 'save'
        keyText: qsTr('Saved')
        // The backend reports an ISO-8601 stamp so that the time is rendered in the user's
        // locale, at minute resolution.
        valueText: {
            const iso = Globals.BackendWrapper.projectLastSaved
            if (iso === '') {
                return ''
            }
            const format = Qt.locale().timeFormat(Locale.ShortFormat).replace(/[:.]?s+/g, '')
            return Qt.formatTime(new Date(iso), format)
        }
        ToolTip.text: qsTr('Time of the last successful save')
    }
}
