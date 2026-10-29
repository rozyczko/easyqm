import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('K-point grid')
        icon: 'border-all'
        collapsed: false

        Loader { source: 'Groups/KPointGrid.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Symmetry')
        icon: 'shapes'

        Loader { source: 'Groups/Symmetry.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Supercell')
        icon: 'th'

        Loader { source: 'Groups/Supercell.qml' }
    }

}
