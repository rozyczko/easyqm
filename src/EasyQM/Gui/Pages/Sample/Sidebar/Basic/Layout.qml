import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Structure')
        icon: 'atom'
        collapsed: false

        Loader { source: 'Groups/Structure.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Atoms')
        icon: 'th-list'

        Loader { source: 'Groups/Atoms.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Electronic state')
        icon: 'sliders-h'

        Loader { source: 'Groups/ElectronicState.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Unit cell')
        icon: 'cube'

        Loader { source: 'Groups/UnitCell.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Display')
        icon: 'eye'

        Loader { source: 'Groups/Display.qml' }
    }

}
