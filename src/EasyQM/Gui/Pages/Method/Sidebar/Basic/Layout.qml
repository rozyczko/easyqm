import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Level of theory')
        icon: 'atom'
        collapsed: false

        Loader { source: 'Groups/LevelOfTheory.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('System')
        icon: 'sliders-h'

        Loader { source: 'Groups/System.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('SCF')
        icon: 'cogs'

        Loader { source: 'Groups/Scf.qml' }
    }

}
