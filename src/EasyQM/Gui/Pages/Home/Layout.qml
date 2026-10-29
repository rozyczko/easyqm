import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Globals as Globals


Item {

    Column {
        anchors.centerIn: parent

        // Application name
        Row {
            id: appName

            property string fontFamily: EaStyle.Fonts.thirdFontFamily
            property string fontPixelSize: EaStyle.Sizes.fontPixelSize * 4

            anchors.horizontalCenter: parent.horizontalCenter

            EaElements.Label {
                font.family: parent.fontFamily
                font.pixelSize: parent.fontPixelSize
                font.weight: Font.Light
                text: Globals.ApplicationInfo.about.namePrefixForLogo
            }
            EaElements.Label {
                font.family: parent.fontFamily
                font.pixelSize: parent.fontPixelSize
                font.weight: Font.DemiBold
                text: Globals.ApplicationInfo.about.nameSuffixForLogo
            }
        }
        // Application name

        // Application version
        EaElements.Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr('Version') + ` ${Globals.ApplicationInfo.about.version}`
        }
        // Application version

        // Vertical spacer
        Item { width: 1; height: EaStyle.Sizes.fontPixelSize * 2.5 }

        // Start button
        EaElements.SideBarButton {
            anchors.horizontalCenter: parent.horizontalCenter

            fontIcon: 'rocket'
            text: qsTr('Start')
            onClicked: Globals.References.applicationWindow.appBarCentralTabs.setCurrentIndex(1)
        }
    }

    Component.onCompleted: console.debug(`Home page loaded ::: ${this}`)
    Component.onDestruction: console.debug(`Home page destroyed ::: ${this}`)

}
