import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Engine-specific (ORCA)')
        icon: 'file-code'
        collapsed: false

        Loader { source: 'Groups/EngineSpecific.qml' }
    }

}
