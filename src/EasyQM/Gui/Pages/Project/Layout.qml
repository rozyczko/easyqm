import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


EaComponents.ContentPage {
    mainView: Loader {
        anchors.fill: parent
        source: 'MainContent/ProjectView.qml'
    }

    sideBar: EaComponents.SideBar {
        tabs: [
            EaElements.TabButton { text: qsTr('Basic controls') }
        ]

        items: [
            Loader { source: 'Sidebar/Basic/Layout.qml' }
        ]

        continueButton.text: qsTr('Continue')
        continueButton.onClicked: Globals.References.applicationWindow.appBarCentralTabs.setCurrentIndex(2)
    }

    Component.onCompleted: console.debug(`Project page loaded ::: ${this}`)
    Component.onDestruction: console.debug(`Project page destroyed ::: ${this}`)
}
