import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents


EaComponents.SideBarColumn {

    EaElements.GroupBox {
        title: qsTr('Single point energy')
        collapsed: false

        Loader { source: 'Groups/SinglePointEnergy.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Geometry optimisation')

        Loader { source: 'Groups/GeometryOptimisation.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Vibrational frequencies')

        Loader { source: 'Groups/VibrationalFrequencies.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Excited states (TD-DFT)')

        Loader { source: 'Groups/ExcitedStates.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Electronic properties')

        Loader { source: 'Groups/ElectronicProperties.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('NMR shielding')

        Loader { source: 'Groups/NmrShielding.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Transition-state search')

        Loader { source: 'Groups/TransitionStateSearch.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Band structure / DOS')

        Loader { source: 'Groups/BandStructure.qml' }
    }

    EaElements.GroupBox {
        title: qsTr('Phonons')

        Loader { source: 'Groups/Phonons.qml' }
    }

}
