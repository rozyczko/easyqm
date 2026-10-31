import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


EaComponents.ContentPage {
    mainView: EaComponents.MainContent {
        tabs: [
            EaElements.TabButton { text: qsTr('Viewer') },
            // PoC1: the tables behind these tabs are not implemented yet.
            EaElements.TabButton { text: qsTr('Atoms'); enabled: false },
            EaElements.TabButton { text: qsTr('Bonds'); enabled: false },
            EaElements.TabButton { text: qsTr('Cell'); enabled: false }
        ]

        items: [
            Loader { source: 'MainContent/StructureView.qml' },
            Loader { source: 'MainContent/AtomsView.qml' },
            Loader { source: 'MainContent/BondsView.qml' },
            Loader { source: 'MainContent/CellView.qml' }
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

        continueButton.text: qsTr('Continue')
        continueButton.onClicked: Globals.References.applicationWindow.appBarCentralTabs.setCurrentIndex(3)
    }

    Component.onCompleted: console.debug(`Sample page loaded ::: ${this}`)
    Component.onDestruction: console.debug(`Sample page destroyed ::: ${this}`)
}
