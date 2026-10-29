import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


EaComponents.ContentPage {
    mainView: Loader {
        anchors.fill: parent
        source: 'MainContent/CalculationsView.qml'
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

        continueButton.text: qsTr('Continue')
        continueButton.onClicked: Globals.References.applicationWindow.appBarCentralTabs.setCurrentIndex(4)
    }

    Component.onCompleted: console.debug(`Calculations page loaded ::: ${this}`)
    Component.onDestruction: console.debug(`Calculations page destroyed ::: ${this}`)
}
