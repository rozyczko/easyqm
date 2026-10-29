import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Results')
        icon: 'check-square'
        collapsed: false

        Loader { source: 'Groups/Results.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Units')
        icon: 'ruler'

        Loader { source: 'Groups/Units.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Export')
        icon: 'download'

        Loader { source: 'Groups/Export.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Job')
        icon: 'info-circle'

        Loader { source: 'Groups/Job.qml' }
    }

}
