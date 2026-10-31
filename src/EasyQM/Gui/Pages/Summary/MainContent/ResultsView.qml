import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements
import EasyApplication.Gui.Components as EaComponents

import Gui.Components as Components
import Gui.Globals as Globals


// Results of the last job: stat tiles, the geometry optimisation card and the vibrational
// frequencies card. The backend only offers what the output contains, so every part is
// shown when its data exists, whichever calculations are ticked now.
Rectangle {
    id: page

    readonly property int commonSpacing: EaStyle.Sizes.fontPixelSize * 1.5
    readonly property int geometryRowsCollapsed: 3

    property bool showAllGeometry: false
    property string frequencyView: 'ir'  // 'ir', 'raman' or 'table'
    // Mode number shared by the spectrum and the table; the future mode animation plays it.
    property var selectedMode: null

    color: EaStyle.Colors.mainContentBackground

    component SectionTitle: EaElements.Label {
        font.family: EaStyle.Fonts.secondFontFamily
        font.pixelSize: EaStyle.Sizes.fontPixelSize * 1.3
        font.weight: Font.Light
        color: EaStyle.Colors.themeAccent
    }

    component MinorLabel: EaElements.Label {
        color: EaStyle.Colors.themeForegroundMinor
    }

    // EasyApp sizes a table's flexible column when its header is created, before the main
    // area has its final width.
    component WideTable: EaComponents.TableView {
        // EasyApp delays presses by 10 ms, and the replayed press never reaches the rows'
        // TapHandler, so row clicks would be lost.
        pressDelay: 0
        onWidthChanged: {
            if (headerItem === null) {
                return
            }
            setWidthOfFlexibleColumnForHeader()
            setAllColumnsWidthAndAlignment()
        }
    }

    function spectrumPoints(view) {
        return Globals.BackendWrapper.resultsModes
            .filter(mode => !mode.imaginary)
            .map(mode => ({
                key: mode.number,
                x: mode.frequency,
                y: view === 'raman' ? mode.ramanActivity : mode.irIntensity,
                title: `ν ${mode.frequencyText} cm⁻¹`,
                detail: view === 'raman' ?
                            qsTr('Mode %1 · %2 Å⁴/amu').arg(mode.number).arg(mode.ramanText) :
                            qsTr('Mode %1 · %2 km/mol').arg(mode.number).arg(mode.irText)
            }))
    }

    Connections {
        target: Globals.BackendWrapper
        // A new job: start from the collapsed table and no selection.
        function onResultsAvailableChanged() {
            page.showAllGeometry = false
            page.selectedMode = null
            if (page.frequencyView === 'raman' && !Globals.BackendWrapper.resultsHasRaman) {
                page.frequencyView = 'ir'
            }
        }
    }

    MinorLabel {
        anchors.centerIn: parent
        visible: !Globals.BackendWrapper.resultsAvailable
        text: Globals.BackendWrapper.resultsPlaceholder
    }

    Flickable {
        anchors.fill: parent
        visible: Globals.BackendWrapper.resultsAvailable
        contentHeight: content.height + 2 * page.commonSpacing
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        ScrollBar.vertical: EaElements.ScrollBar {}

        Column {
            id: content

            x: page.commonSpacing
            y: page.commonSpacing
            width: page.width - 2 * page.commonSpacing
            spacing: page.commonSpacing

            // Stat tiles: one per headline number found in the output

            Row {
                id: tiles

                width: parent.width
                spacing: EaStyle.Sizes.fontPixelSize * 0.75

                Repeater {
                    id: tileRepeater

                    model: Globals.BackendWrapper.resultsTiles

                    Components.StatTile {
                        width: (tiles.width - tiles.spacing * (tileRepeater.count - 1)) / tileRepeater.count
                        title: modelData.title
                        value: modelData.value
                        detail: modelData.detail
                        tone: modelData.tone
                    }
                }
            }

            Row {
                width: parent.width
                spacing: page.commonSpacing

                // Geometry optimisation card

                Column {
                    id: geometryCard

                    visible: Globals.BackendWrapper.resultsHasOptimisation
                    width: Globals.BackendWrapper.resultsHasFrequencies ? parent.width * 0.42 : parent.width
                    spacing: EaStyle.Sizes.fontPixelSize

                    Item {
                        width: parent.width
                        height: geometryTitle.height

                        SectionTitle {
                            id: geometryTitle
                            text: qsTr('Geometry optimisation')
                        }
                        MinorLabel {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: qsTr('initial → final')
                        }
                    }

                    WideTable {
                        id: geometryTable

                        readonly property var rows: Globals.BackendWrapper.resultsGeometryRows

                        width: parent.width
                        model: page.showAllGeometry ? rows.length : Math.min(rows.length, page.geometryRowsCollapsed)
                        maxRowCountShow: Math.max(count, 1)
                        defaultInfoText: qsTr('No geometry found')

                        header: EaComponents.TableViewHeader {
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignLeft
                                text: qsTr('Bond')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('Initial (Å)')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('Final (Å)')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('Δ (Å)')
                            }
                            EaComponents.TableViewLabel {
                                flexibleWidth: true
                                leftPadding: EaStyle.Sizes.fontPixelSize
                                horizontalAlignment: Text.AlignLeft
                                text: qsTr('Angle')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('Final (°)')
                            }
                        }

                        delegate: EaComponents.TableViewDelegate {
                            readonly property var row: geometryTable.rows[index]

                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignLeft
                                text: row.bond
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: row.bondInitial
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: row.bondFinal
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: row.bondChange
                            }
                            EaComponents.TableViewLabel {
                                flexibleWidth: true
                                leftPadding: EaStyle.Sizes.fontPixelSize
                                horizontalAlignment: Text.AlignLeft
                                text: row.angle
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 5
                                horizontalAlignment: Text.AlignRight
                                text: row.angleFinal
                            }
                        }
                    }

                    Row {
                        visible: geometryTable.rows.length > page.geometryRowsCollapsed
                        spacing: EaStyle.Sizes.fontPixelSize * 0.5

                        MinorLabel {
                            visible: !page.showAllGeometry
                            text: qsTr('… %1 more rows ·').arg(geometryTable.rows.length - page.geometryRowsCollapsed)
                        }
                        EaElements.Label {
                            color: EaStyle.Colors.link
                            text: page.showAllGeometry ? qsTr('show fewer') : qsTr('show all')

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.showAllGeometry = !page.showAllGeometry
                            }
                        }
                    }

                    SectionTitle {
                        visible: Globals.BackendWrapper.resultsConvergenceRows.length > 0
                        topPadding: EaStyle.Sizes.fontPixelSize * 0.5
                        text: qsTr('Convergence')
                    }

                    WideTable {
                        id: convergenceTable

                        readonly property var rows: Globals.BackendWrapper.resultsConvergenceRows

                        visible: rows.length > 0
                        width: parent.width
                        model: rows.length
                        maxRowCountShow: Math.max(count, 1)

                        header: EaComponents.TableViewHeader {
                            EaComponents.TableViewLabel {
                                flexibleWidth: true
                                horizontalAlignment: Text.AlignLeft
                                text: qsTr('Criterion')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 7
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('Value')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 7
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('Tolerance')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 4
                                text: qsTr('Met')
                            }
                        }

                        delegate: EaComponents.TableViewDelegate {
                            readonly property var row: convergenceTable.rows[index]

                            EaComponents.TableViewLabel {
                                flexibleWidth: true
                                horizontalAlignment: Text.AlignLeft
                                text: row.criterion
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 7
                                horizontalAlignment: Text.AlignRight
                                text: row.value
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 7
                                horizontalAlignment: Text.AlignRight
                                text: row.tolerance
                            }
                            // Icon and colour, so the state is not told by colour alone.
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 4
                                font.family: EaStyle.Fonts.iconsFamily
                                color: row.met ? EaStyle.Colors.green : EaStyle.Colors.red
                                text: row.met ? 'check' : 'times'
                            }
                        }
                    }
                }

                // Vibrational frequencies card

                Column {
                    visible: Globals.BackendWrapper.resultsHasFrequencies
                    width: geometryCard.visible ? parent.width - geometryCard.width - parent.spacing : parent.width
                    spacing: EaStyle.Sizes.fontPixelSize

                    Item {
                        width: parent.width
                        height: viewButtons.height

                        SectionTitle {
                            anchors.verticalCenter: parent.verticalCenter
                            text: qsTr('Vibrational frequencies')
                        }

                        Row {
                            id: viewButtons
                            anchors.right: parent.right

                            EaElements.SideBarButton {
                                width: EaStyle.Sizes.fontPixelSize * 9
                                checkable: true
                                checked: page.frequencyView === 'ir'
                                text: qsTr('IR spectrum')
                                onClicked: page.frequencyView = 'ir'
                            }
                            EaElements.SideBarButton {
                                visible: Globals.BackendWrapper.resultsHasRaman
                                width: EaStyle.Sizes.fontPixelSize * 10
                                checkable: true
                                checked: page.frequencyView === 'raman'
                                text: qsTr('Raman spectrum')
                                onClicked: page.frequencyView = 'raman'
                            }
                            EaElements.SideBarButton {
                                width: EaStyle.Sizes.fontPixelSize * 10
                                checkable: true
                                checked: page.frequencyView === 'table'
                                text: Globals.BackendWrapper.resultsModes.length === 1 ?
                                          qsTr('Table (1 mode)') :
                                          qsTr('Table (%1 modes)').arg(Globals.BackendWrapper.resultsModes.length)
                                onClicked: page.frequencyView = 'table'
                            }
                        }
                    }

                    Components.StickSpectrum {
                        visible: page.frequencyView !== 'table'
                        width: parent.width
                        height: EaStyle.Sizes.fontPixelSize * 26
                        points: page.spectrumPoints(page.frequencyView)
                        xTitle: qsTr('Wavenumber (cm⁻¹)')
                        yTitle: page.frequencyView === 'raman' ?
                                    qsTr('Raman activity (rel. %)') :
                                    qsTr('IR intensity (rel. %)')
                        selectedKey: page.selectedMode
                        onPicked: (key) => page.selectedMode = key
                    }

                    WideTable {
                        id: modesTable

                        readonly property var rows: Globals.BackendWrapper.resultsModes
                        readonly property int ramanWidth: Globals.BackendWrapper.resultsHasRaman ? EaStyle.Sizes.fontPixelSize * 9 : 0

                        visible: page.frequencyView === 'table'
                        width: parent.width
                        model: rows.length
                        maxRowCountShow: 14
                        defaultInfoText: qsTr('No vibrational modes')

                        header: EaComponents.TableViewHeader {
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 4
                                horizontalAlignment: Text.AlignHCenter
                                text: qsTr('Mode')
                            }
                            EaComponents.TableViewLabel {
                                flexibleWidth: true
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('ν (cm⁻¹)')
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 9
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('IR (km/mol)')
                            }
                            EaComponents.TableViewLabel {
                                width: modesTable.ramanWidth
                                visible: Globals.BackendWrapper.resultsHasRaman
                                horizontalAlignment: Text.AlignRight
                                text: qsTr('Raman (Å⁴/amu)')
                            }
                        }

                        delegate: EaComponents.TableViewDelegate {
                            readonly property var row: modesTable.rows[index]

                            color: row.number === page.selectedMode ?
                                       EaStyle.Colors.themeRowHighlightHovered :
                                       index % 2 ? EaStyle.Colors.themeBackgroundHovered2 : EaStyle.Colors.themeBackgroundHovered1

                            TapHandler {
                                onTapped: page.selectedMode = row.number
                            }

                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 4
                                horizontalAlignment: Text.AlignHCenter
                                text: row.number
                            }
                            EaComponents.TableViewLabel {
                                flexibleWidth: true
                                horizontalAlignment: Text.AlignRight
                                color: row.imaginary ? EaStyle.Colors.orange : EaStyle.Colors.themeForeground
                                text: row.imaginary ? qsTr('%1 (imaginary)').arg(row.frequencyText) : row.frequencyText
                            }
                            EaComponents.TableViewLabel {
                                width: EaStyle.Sizes.fontPixelSize * 9
                                horizontalAlignment: Text.AlignRight
                                text: row.irText
                            }
                            EaComponents.TableViewLabel {
                                width: modesTable.ramanWidth
                                visible: Globals.BackendWrapper.resultsHasRaman
                                horizontalAlignment: Text.AlignRight
                                text: row.ramanText
                            }
                        }
                    }

                    Item {
                        width: parent.width
                        height: animateButton.height

                        MinorLabel {
                            anchors.left: parent.left
                            anchors.right: animateButton.left
                            anchors.rightMargin: EaStyle.Sizes.fontPixelSize
                            anchors.verticalCenter: parent.verticalCenter
                            wrapMode: Text.WordWrap
                            text: page.frequencyView === 'table' ?
                                      qsTr('Click a row to select its mode.') :
                                      qsTr('Hover a stick for mode number, frequency and intensity; click it to select the mode.')
                        }

                        // Not implemented yet: would play the selected mode in the Sample viewer.
                        EaElements.SideBarButton {
                            id: animateButton
                            anchors.right: parent.right
                            width: EaStyle.Sizes.fontPixelSize * 13
                            fontIcon: 'play'
                            text: qsTr('Animate selected mode')
                            enabled: false
                            ToolTip.text: qsTr('Planned: plays the selected mode in the Sample viewer')
                        }
                    }
                }
            }
        }
    }
}
