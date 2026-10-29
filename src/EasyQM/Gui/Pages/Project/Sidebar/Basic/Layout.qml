import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Get started')
        icon: 'rocket'
        collapsed: false

        Loader { source: 'Groups/GetStarted.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Project details')
        icon: 'info-circle'

        Loader { source: 'Groups/ProjectDetails.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Examples')
        icon: 'folder-open'

        Loader { source: 'Groups/Examples.qml' }
    }

}
