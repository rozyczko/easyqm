import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


// One group per calculation, in the order the workflow runs them.
EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Geometry optimisation')
        icon: 'level-down-alt'
        collapsed: false

        Loader { source: 'Groups/GeometryOptimisation.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Vibrational frequencies')
        icon: 'chart-bar'

        Loader { source: 'Groups/VibrationalFrequencies.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Single point energy')
        icon: 'dot-circle'

        Loader { source: 'Groups/SinglePointEnergy.qml' }
    }

    // PoC1 placeholders: no controls behind these yet.
    EaElements.GroupBox {
        title: qsTr('Excited states (TD-DFT)')
        icon: 'cog'

        Loader { source: 'Groups/ExcitedStates.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Electronic properties')
        icon: 'cog'

        Loader { source: 'Groups/ElectronicProperties.qml' }
    }

}
