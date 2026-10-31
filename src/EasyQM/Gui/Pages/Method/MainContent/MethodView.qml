import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Engine card and the Run card: one engine (ORCA), run locally and serially, with the
// engine output followed live in the log view.
Rectangle {
    id: page

    readonly property int commonSpacing: EaStyle.Sizes.fontPixelSize * 1.5
    readonly property int contentWidth: width - 2 * commonSpacing
    readonly property bool canRun: Globals.BackendWrapper.methodEngineFound &&
                                   Globals.BackendWrapper.calculationsSelectedCount > 0 &&
                                   !Globals.BackendWrapper.jobRunning

    color: EaStyle.Colors.mainContentBackground

    component SectionTitle: EaElements.Label {
        font.family: EaStyle.Fonts.secondFontFamily
        font.pixelSize: EaStyle.Sizes.fontPixelSize * 1.5
        font.weight: Font.Light
        color: EaStyle.Colors.themeAccent
    }

    // A file:// URL for a local path, to hand to the system file browser or editor.
    function fileUrl(path) {
        const slashed = path.replace(/\\/g, '/')
        return slashed.startsWith('/') ? `file://${slashed}` : `file:///${slashed}`
    }

    Column {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: commonSpacing
        width: page.contentWidth
        spacing: commonSpacing

        // Engine

        Item {
            width: parent.width
            height: engineButtons.height

            SectionTitle {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr('Engine')
            }

            Row {
                id: engineButtons
                anchors.right: parent.right
                spacing: EaStyle.Sizes.fontPixelSize

                EaElements.SideBarButton {
                    fontIcon: 'sync'
                    text: qsTr('Re-detect')
                    onClicked: Globals.BackendWrapper.methodRedetect()
                }
                EaElements.SideBarButton {
                    fontIcon: 'cog'
                    text: qsTr('Configure paths...')
                    onClicked: engineFileDialog.open()
                }
            }
        }

        Components.EngineCard {
            name: Globals.BackendWrapper.methodEngineName
            found: Globals.BackendWrapper.methodEngineFound
            subtitle: Globals.BackendWrapper.methodEngineCardText
            path: Globals.BackendWrapper.methodEnginePath
        }

        // Run

        Item {
            width: parent.width
            height: runButtons.height

            SectionTitle {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr('Run')
            }

            Row {
                id: runButtons
                anchors.right: parent.right
                spacing: EaStyle.Sizes.fontPixelSize

                // Not in PoC1: ORCA echoes the input file at the top of its output.
                EaElements.SideBarButton {
                    fontIcon: 'eye'
                    text: qsTr('Preview input')
                    enabled: false
                }
                EaElements.SideBarButton {
                    fontIcon: 'download'
                    text: qsTr('Save inputs')
                    enabled: false
                }
            }
        }

        Row {
            spacing: EaStyle.Sizes.fontPixelSize

            Row {
                EaElements.SideBarButton {
                    width: EaStyle.Sizes.fontPixelSize * 10
                    checkable: true
                    checked: true
                    text: qsTr('Run locally')
                }
                EaElements.SideBarButton {
                    width: EaStyle.Sizes.fontPixelSize * 14
                    checkable: true
                    enabled: false
                    text: qsTr('Remote / cluster (later)')
                }
            }

            EaElements.Label {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr('Cores:')
            }
            EaElements.TextField {
                width: EaStyle.Sizes.fontPixelSize * 6
                // PoC1 runs serially.
                enabled: false
                validator: IntValidator { bottom: 1; top: 1024 }
                text: Globals.BackendWrapper.methodCores
                onEditingFinished: Globals.BackendWrapper.methodSetCores(parseInt(text))
                ToolTip.text: qsTr('Jobs run on one core in this version')
            }

            EaElements.Label {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr('Memory:')
            }
            EaElements.TextField {
                width: EaStyle.Sizes.fontPixelSize * 6
                enabled: !Globals.BackendWrapper.jobRunning
                validator: IntValidator { bottom: 1; top: 4096 }
                text: Globals.BackendWrapper.methodMemoryGb
                onEditingFinished: Globals.BackendWrapper.methodSetMemoryGb(parseInt(text))
            }
            EaElements.Label {
                anchors.verticalCenter: parent.verticalCenter
                color: EaStyle.Colors.themeForegroundMinor
                text: 'GB'
            }

            Item { width: EaStyle.Sizes.fontPixelSize * 2; height: 1 }

            EaElements.SideBarButton {
                width: EaStyle.Sizes.fontPixelSize * 11
                fontIcon: 'play-circle'
                text: qsTr('Run workflow')
                enabled: page.canRun
                onClicked: Globals.BackendWrapper.jobRun()
            }
            EaElements.SideBarButton {
                width: EaStyle.Sizes.fontPixelSize * 7
                fontIcon: 'stop'
                text: qsTr('Stop')
                enabled: Globals.BackendWrapper.jobRunning
                onClicked: Globals.BackendWrapper.jobStop()
            }
        }

        // Step strip: the workflow from the Calculations page. All steps run in one engine
        // process, so they share the job state.
        Row {
            spacing: EaStyle.Sizes.fontPixelSize

            Repeater {
                model: Globals.BackendWrapper.calculationsWorkflow

                Row {
                    spacing: EaStyle.Sizes.fontPixelSize

                    EaElements.Label {
                        visible: index > 0
                        anchors.verticalCenter: parent.verticalCenter
                        font.family: EaStyle.Fonts.iconsFamily
                        color: EaStyle.Colors.themeForegroundMinor
                        text: 'arrow-right'
                    }
                    Components.StatusPill {
                        status: Globals.BackendWrapper.jobState === 'idle' ? 'new' : Globals.BackendWrapper.jobState
                        text: `${modelData.step} · ${modelData.label}`
                    }
                }
            }

            EaElements.Label {
                visible: Globals.BackendWrapper.calculationsWorkflow.length === 0
                color: EaStyle.Colors.themeForegroundMinor
                text: qsTr('No calculations selected')
            }
        }

        // Job state, run folder and output file

        Item {
            id: jobLine

            width: parent.width
            height: outputButtons.height

            Row {
                anchors.left: parent.left
                anchors.right: outputButtons.left
                anchors.rightMargin: EaStyle.Sizes.fontPixelSize
                anchors.verticalCenter: parent.verticalCenter
                spacing: EaStyle.Sizes.fontPixelSize

                Components.StatusPill {
                    anchors.verticalCenter: parent.verticalCenter
                    status: Globals.BackendWrapper.jobState === 'idle' ? 'new' : Globals.BackendWrapper.jobState
                    text: Globals.BackendWrapper.jobStateLabel
                }
                EaElements.Label {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Globals.BackendWrapper.jobMessage
                }
                EaElements.Label {
                    anchors.verticalCenter: parent.verticalCenter
                    font.family: EaStyle.Fonts.monoFontFamily
                    color: EaStyle.Colors.themeForegroundMinor
                    // Long run folders are shortened in the middle, keeping the file name.
                    width: Math.min(implicitWidth, Math.max(0, parent.width - x))
                    elide: Text.ElideMiddle
                    text: Globals.BackendWrapper.jobOutputPath
                }
            }

            Row {
                id: outputButtons
                anchors.right: parent.right
                spacing: EaStyle.Sizes.fontPixelSize

                EaElements.SideBarButton {
                    width: EaStyle.Sizes.fontPixelSize * 10
                    fontIcon: 'file-alt'
                    text: qsTr('Open output')
                    enabled: Globals.BackendWrapper.jobOutputPath !== ''
                    onClicked: Qt.openUrlExternally(page.fileUrl(Globals.BackendWrapper.jobOutputPath))
                }
                EaElements.SideBarButton {
                    width: EaStyle.Sizes.fontPixelSize * 10
                    fontIcon: 'folder-open'
                    text: qsTr('Open folder')
                    enabled: Globals.BackendWrapper.jobFolder !== ''
                    onClicked: Qt.openUrlExternally(page.fileUrl(Globals.BackendWrapper.jobFolder))
                }
            }
        }

        // Live output: the engine's output file, followed while the job runs.
        Components.LogView {
            id: logView

            width: parent.width
            height: Math.max(EaStyle.Sizes.fontPixelSize * 10, page.height - 2 * page.commonSpacing - y)
            placeholderText: qsTr('No job has been run yet.')
            text: Globals.BackendWrapper.jobOutput

            Connections {
                target: Globals.BackendWrapper
                function onJobOutputAppended(text) { logView.append(text) }
            }
        }
    }

    FileDialog {
        id: engineFileDialog
        title: qsTr('Choose the %1 executable').arg(Globals.BackendWrapper.methodEngineName)
        nameFilters: [qsTr('ORCA executable (orca orca.exe)'), qsTr('All files (*)')]
        onAccepted: Globals.BackendWrapper.methodSetEnginePath(selectedFile)
    }
}
