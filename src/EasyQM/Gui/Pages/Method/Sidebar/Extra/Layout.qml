import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Engine-specific (%1)').arg(Globals.BackendWrapper.methodEngineName)
        icon: 'file-code'
        collapsed: false

        Loader { source: 'Groups/EngineSpecific.qml' }
    }

}
