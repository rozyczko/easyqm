import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.ContentPage {
    mainView: EaComponents.MainContent {
        tabs: [
            EaElements.TabButton { text: qsTr('Results') },
            EaElements.TabButton { text: qsTr('Report') },
            EaElements.TabButton { text: qsTr('Output') }
        ]

        items: [
            Loader { source: 'MainContent/ResultsView.qml' },
            Loader { source: 'MainContent/ReportView.qml' },
            Loader { source: 'MainContent/OutputView.qml' }
        ]
    }

    sideBar: EaComponents.SideBar {
        tabs: [
            EaElements.TabButton { text: qsTr('Basic controls') },
            EaElements.TabButton { text: qsTr('Extra controls') }
        ]

        items: [
            Loader { source: 'Sidebar/Basic/Layout.qml' },
            Loader { source: 'Sidebar/Extra/Layout.qml' }
        ]

        continueButton.visible: false
    }

    Component.onCompleted: console.debug(`Summary page loaded ::: ${this}`)
    Component.onDestruction: console.debug(`Summary page destroyed ::: ${this}`)
}
