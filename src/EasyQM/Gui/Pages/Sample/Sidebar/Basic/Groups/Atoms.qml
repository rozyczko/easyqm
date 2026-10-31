import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Globals as Globals


Column {
    spacing: EaStyle.Sizes.fontPixelSize

    readonly property int coordinateWidth: EaStyle.Sizes.fontPixelSize * 4.5

    EaComponents.TableView {
        id: atomsTable

        defaultInfoText: qsTr('No structure loaded')
        // Row count only: the delegates read the current atom by index, so a change of one
        // atom does not rebuild the table.
        model: Globals.BackendWrapper.sampleAtoms.length

        header: EaComponents.TableViewHeader {
            EaComponents.TableViewLabel {
                width: EaStyle.Sizes.fontPixelSize * 2.5
                text: qsTr('No.')
            }
            EaComponents.TableViewLabel {
                flexibleWidth: true
                horizontalAlignment: Text.AlignLeft
                text: qsTr('Label')
            }
            EaComponents.TableViewLabel {
                width: EaStyle.Sizes.fontPixelSize * 2.5
                horizontalAlignment: Text.AlignLeft
                text: qsTr('El.')
            }
            EaComponents.TableViewLabel {
                width: coordinateWidth
                horizontalAlignment: Text.AlignRight
                text: qsTr('x (Å)')
            }
            EaComponents.TableViewLabel {
                width: coordinateWidth
                horizontalAlignment: Text.AlignRight
                text: qsTr('y (Å)')
            }
            EaComponents.TableViewLabel {
                width: coordinateWidth
                horizontalAlignment: Text.AlignRight
                text: qsTr('z (Å)')
            }
            EaComponents.TableViewLabel {
                width: EaStyle.Sizes.tableRowHeight
                text: qsTr('Fix')
                ToolTip.text: qsTr('Keep the atom in place during geometry optimisation')
            }
        }

        delegate: EaComponents.TableViewDelegate {
            readonly property var atom: Globals.BackendWrapper.sampleAtoms[index]

            EaComponents.TableViewLabel {
                width: EaStyle.Sizes.fontPixelSize * 2.5
                color: EaStyle.Colors.themeForegroundMinor
                text: index + 1
            }
            EaComponents.TableViewLabel {
                flexibleWidth: true
                horizontalAlignment: Text.AlignLeft
                text: atom.label
            }
            EaComponents.TableViewLabel {
                width: EaStyle.Sizes.fontPixelSize * 2.5
                horizontalAlignment: Text.AlignLeft
                text: atom.element
            }
            EaComponents.TableViewLabel {
                width: coordinateWidth
                horizontalAlignment: Text.AlignRight
                text: atom.x.toFixed(4)
            }
            EaComponents.TableViewLabel {
                width: coordinateWidth
                horizontalAlignment: Text.AlignRight
                text: atom.y.toFixed(4)
            }
            EaComponents.TableViewLabel {
                width: coordinateWidth
                horizontalAlignment: Text.AlignRight
                text: atom.z.toFixed(4)
            }
            EaComponents.TableViewCheckBox {
                width: EaStyle.Sizes.tableRowHeight
                checked: atom.fixed
                onToggled: Globals.BackendWrapper.sampleSetAtomFixed(index, checked)
            }
        }
    }

    Item {
        width: EaStyle.Sizes.sideBarContentWidth
        height: buttons.height

        Row {
            id: buttons
            spacing: EaStyle.Sizes.fontPixelSize

            // PoC1: the structure is not editable yet.
            EaElements.SideBarButton {
                width: EaStyle.Sizes.fontPixelSize * 9
                fontIcon: 'plus'
                text: qsTr('Add atom')
                enabled: false
            }
            EaElements.SideBarButton {
                width: EaStyle.Sizes.fontPixelSize * 8
                fontIcon: 'minus'
                text: qsTr('Remove')
                enabled: false
            }
        }

        EaElements.Label {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            color: EaStyle.Colors.themeForegroundMinor
            text: qsTr('%1 atoms · Cartesian · Å').arg(Globals.BackendWrapper.sampleAtomCount)
        }
    }
}
