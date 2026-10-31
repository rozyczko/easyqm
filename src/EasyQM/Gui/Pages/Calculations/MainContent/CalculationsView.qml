import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Components as Components
import Gui.Globals as Globals


// "Calculations to perform" check-list and the resulting workflow strip.
Rectangle {
    id: page

    readonly property int commonSpacing: EaStyle.Sizes.fontPixelSize * 1.5
    readonly property int contentWidth: width - 2 * commonSpacing

    color: EaStyle.Colors.mainContentBackground

    Column {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: commonSpacing
        width: page.contentWidth
        spacing: commonSpacing

        // Calculations to perform

        Item {
            width: parent.width
            height: calculationsTitle.height

            EaElements.Label {
                id: calculationsTitle
                font.family: EaStyle.Fonts.secondFontFamily
                font.pixelSize: EaStyle.Sizes.fontPixelSize * 1.5
                font.weight: Font.Light
                color: EaStyle.Colors.themeAccent
                text: qsTr('Calculations to perform')
            }
            EaElements.Label {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                color: EaStyle.Colors.themeForegroundMinor
                text: qsTr('%1 selected').arg(Globals.BackendWrapper.calculationsSelectedCount)
            }
        }

        EaComponents.TableView {
            id: table

            width: page.contentWidth
            // The framework sizes the flexible column once, when the header is created; the
            // main area gets its final width later than that.
            onWidthChanged: {
                if (headerItem === null) {
                    return
                }
                setWidthOfFlexibleColumnForHeader()
                setAllColumnsWidthAndAlignment()
            }
            tallRows: true
            defaultInfoText: qsTr('No calculations available')
            model: Globals.BackendWrapper.calculationsRows.length

            header: EaComponents.TableViewHeader {
                EaComponents.TableViewLabel {
                    width: EaStyle.Sizes.tableRowHeight
                }
                EaComponents.TableViewLabel {
                    width: EaStyle.Sizes.fontPixelSize * 14
                    horizontalAlignment: Text.AlignLeft
                    text: qsTr('Calculation')
                }
                EaComponents.TableViewLabel {
                    flexibleWidth: true
                    horizontalAlignment: Text.AlignLeft
                    text: qsTr('Description')
                }
                EaComponents.TableViewLabel {
                    width: EaStyle.Sizes.fontPixelSize * 22
                    horizontalAlignment: Text.AlignLeft
                    text: qsTr('Main results')
                }
                EaComponents.TableViewLabel {
                    width: EaStyle.Sizes.fontPixelSize * 14
                    horizontalAlignment: Text.AlignLeft
                    text: qsTr('Requires / notes')
                }
            }

            delegate: EaComponents.TableViewDelegate {
                readonly property var row: Globals.BackendWrapper.calculationsRows[index]

                EaComponents.TableViewCheckBox {
                    width: EaStyle.Sizes.tableRowHeight
                    checked: row.selected
                    onToggled: Globals.BackendWrapper.calculationsSetSelected(row.type, checked)
                }
                EaComponents.TableViewLabel {
                    width: EaStyle.Sizes.fontPixelSize * 14
                    horizontalAlignment: Text.AlignLeft
                    font.bold: true
                    text: row.name
                }
                EaComponents.TableViewLabel {
                    flexibleWidth: true
                    horizontalAlignment: Text.AlignLeft
                    elide: Text.ElideRight
                    color: EaStyle.Colors.themeForegroundMinor
                    text: row.description
                    ToolTip.text: row.description
                }
                EaComponents.TableViewLabel {
                    width: EaStyle.Sizes.fontPixelSize * 22
                    horizontalAlignment: Text.AlignLeft
                    elide: Text.ElideRight
                    text: row.results
                    ToolTip.text: row.results
                }
                EaComponents.TableViewLabel {
                    width: EaStyle.Sizes.fontPixelSize * 14
                    horizontalAlignment: Text.AlignLeft
                    elide: Text.ElideRight
                    text: row.notes !== '' ? row.notes : '–'
                }
            }
        }

        // Resulting workflow

        EaElements.Label {
            font.family: EaStyle.Fonts.secondFontFamily
            font.pixelSize: EaStyle.Sizes.fontPixelSize * 1.5
            font.weight: Font.Light
            color: EaStyle.Colors.themeAccent
            text: qsTr('Resulting workflow')
        }

        Rectangle {
            width: parent.width
            height: strip.height + 2 * EaStyle.Sizes.fontPixelSize
            radius: 4
            color: EaStyle.Colors.contentBackground
            border.width: 1
            border.color: EaStyle.Colors.appBorder

            Row {
                id: strip

                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: EaStyle.Sizes.fontPixelSize
                spacing: EaStyle.Sizes.fontPixelSize

                Components.StatusPill {
                    status: 'running'
                    text: qsTr('Structure (%1)').arg(Globals.BackendWrapper.sampleFormula)
                }

                Repeater {
                    model: Globals.BackendWrapper.calculationsWorkflow

                    Row {
                        spacing: strip.spacing

                        EaElements.Label {
                            anchors.verticalCenter: parent.verticalCenter
                            font.family: EaStyle.Fonts.iconsFamily
                            color: EaStyle.Colors.themeForegroundMinor
                            text: 'arrow-right'
                        }
                        Components.StatusPill {
                            status: 'completed'
                            text: `${modelData.step} · ${modelData.label}`
                        }
                    }
                }

                EaElements.Label {
                    visible: Globals.BackendWrapper.calculationsWorkflow.length === 0
                    anchors.verticalCenter: parent.verticalCenter
                    color: EaStyle.Colors.themeForegroundMinor
                    text: qsTr('Tick at least one calculation')
                }
            }
        }

        EaElements.Label {
            color: EaStyle.Colors.themeForegroundMinor
            text: qsTr('Order is resolved automatically from dependencies.')
        }
    }
}
