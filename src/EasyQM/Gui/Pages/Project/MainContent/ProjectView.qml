import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// The "Current project" card: name, description, folder, dates and the one-line summary of
// sample, calculations, engine and job status.
Rectangle {

    readonly property int commonSpacing: EaStyle.Sizes.fontPixelSize * 1.5

    color: EaStyle.Colors.mainContentBackground

    // An empty Label is hidden and the Grid would skip its cell, so empty values show a dash.
    function orDash(value) {
        return value !== '' ? value : '–'
    }

    function formatDateTime(iso) {
        return iso ? Qt.formatDateTime(new Date(iso), 'yyyy-MM-dd hh:mm') : '–'
    }

    Column {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.topMargin: commonSpacing
        anchors.leftMargin: commonSpacing * 1.5

        spacing: commonSpacing

        // Project title
        EaElements.TextInput {
            font.family: EaStyle.Fonts.secondFontFamily
            font.pixelSize: EaStyle.Sizes.fontPixelSize * 3
            font.weight: Font.ExtraLight
            text: Globals.BackendWrapper.projectName
            onEditingFinished: Globals.BackendWrapper.projectSetName(text)
        }
        // Project title

        // Project info
        Grid {
            columns: 2
            rowSpacing: 0
            columnSpacing: commonSpacing
            verticalItemAlignment: Grid.AlignVCenter

            EaElements.Label {
                font.bold: true
                text: qsTr('Description:')
            }
            EaElements.TextInput {
                text: Globals.BackendWrapper.projectDescription
                placeholderText: qsTr('Enter project description here')
                onEditingFinished: Globals.BackendWrapper.projectSetDescription(text)
            }

            EaElements.Label {
                font.bold: true
                text: qsTr('Location:')
            }
            EaElements.Label {
                font.family: EaStyle.Fonts.monoFontFamily
                text: Globals.BackendWrapper.projectLocation
            }

            EaElements.Label {
                font.bold: true
                text: qsTr('Created:')
            }
            EaElements.Label {
                text: formatDateTime(Globals.BackendWrapper.projectCreatedAt)
            }

            EaElements.Label {
                font.bold: true
                text: qsTr('Last modified:')
            }
            EaElements.Label {
                text: formatDateTime(Globals.BackendWrapper.projectModifiedAt)
            }

            EaElements.Label {
                font.bold: true
                text: qsTr('Sample:')
            }
            EaElements.Label {
                text: orDash(Globals.BackendWrapper.projectSampleName)
            }

            EaElements.Label {
                font.bold: true
                text: qsTr('Calculations:')
            }
            EaElements.Label {
                text: orDash(Globals.BackendWrapper.projectCalculations.join(' · '))
            }

            EaElements.Label {
                font.bold: true
                text: qsTr('Engine:')
            }
            EaElements.Label {
                text: orDash(Globals.BackendWrapper.projectEngine)
            }

            EaElements.Label {
                font.bold: true
                text: qsTr('Status:')
            }
            Components.StatusPill {
                status: Globals.BackendWrapper.projectStatus
                text: Globals.BackendWrapper.projectStatusLabel
            }
        }
        // Project info

    }

}
