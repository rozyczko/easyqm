import QtQuick
import QtQuick.Controls

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements

import Gui.Components as Components
import Gui.Globals as Globals


// Assistant settings: the Anthropic API key, the model, when actions ask first, and what is
// shared. The key is written to the backend and never read back.
EaElements.Dialog {
    id: dialog

    property string verifyMessage: ''

    title: qsTr('Assistant settings')
    modal: true
    standardButtons: Dialog.Close
    closePolicy: Popup.CloseOnEscape

    onOpened: {
        keyField.text = ''
        verifyMessage = ''
    }

    Connections {
        target: Globals.BackendWrapper
        function onAssistantSettingsVerified(message) { dialog.verifyMessage = message }
    }

    Column {
        width: EaStyle.Sizes.sideBarContentWidth
        spacing: EaStyle.Sizes.fontPixelSize * 0.75

        // Key

        EaElements.Label {
            font.bold: true
            text: qsTr('Anthropic API key')
        }

        Components.LabelledField {
            text: qsTr('New key:')
            EaElements.TextField {
                id: keyField
                width: parent.width
                horizontalAlignment: TextInput.AlignLeft
                echoMode: TextInput.Password
                placeholderText: Globals.BackendWrapper.assistantSettingsHasKey ? qsTr('a key is set') : 'sk-ant-…'
            }
        }

        EaElements.CheckBox {
            id: rememberBox
            checked: true
            text: Globals.BackendWrapper.assistantSettingsSecureStoreAvailable ?
                      qsTr('Remember it in the system credential store') :
                      qsTr('Remember it in the settings file, as plain text')
        }

        Row {
            spacing: EaStyle.Sizes.fontPixelSize * 0.5
            EaElements.Button {
                text: qsTr('Use key')
                enabled: keyField.text.trim() !== ''
                onClicked: {
                    Globals.BackendWrapper.assistantSettingsSetKey(keyField.text, rememberBox.checked)
                    keyField.text = ''
                }
            }
            EaElements.Button {
                text: qsTr('Clear key')
                enabled: Globals.BackendWrapper.assistantSettingsHasKey
                onClicked: Globals.BackendWrapper.assistantSettingsClearKey()
            }
            EaElements.Button {
                text: qsTr('Verify')
                enabled: Globals.BackendWrapper.assistantSettingsSdkAvailable
                onClicked: {
                    dialog.verifyMessage = qsTr('Checking…')
                    Globals.BackendWrapper.assistantSettingsVerify()
                }
            }
        }

        EaElements.Label {
            width: parent.width
            wrapMode: Text.WordWrap
            color: EaStyle.Colors.themeForegroundMinor
            text: {
                if (!Globals.BackendWrapper.assistantSettingsSdkAvailable)
                    return qsTr('The anthropic package is not installed (pip install EasyQM[llm]); the offline assistant answers.')
                const source = Globals.BackendWrapper.assistantSettingsKeySource
                if (source === '')
                    return qsTr('No credential found: enter a key, set ANTHROPIC_API_KEY or run "ant auth login".')
                const storage = {
                    session: qsTr('for this session only'),
                    keyring: qsTr('remembered in the credential store'),
                    settings: qsTr('remembered in the settings file')
                }[Globals.BackendWrapper.assistantSettingsKeyStorage] ?? ''
                return qsTr('Credential in use: from the %1').arg(source) + (storage ? `, ${storage}.` : '.')
            }
        }

        EaElements.Label {
            visible: dialog.verifyMessage !== ''
            width: parent.width
            wrapMode: Text.WordWrap
            text: dialog.verifyMessage
        }

        // Model

        EaElements.Label {
            topPadding: EaStyle.Sizes.fontPixelSize * 0.5
            font.bold: true
            text: qsTr('Model')
        }

        Components.LabelledField {
            text: qsTr('Model:')
            Components.ChoiceComboBox {
                width: parent.width
                choices: Array.from(Globals.BackendWrapper.assistantSettingsModelChoices, m => ({ value: m, label: m }))
                value: Globals.BackendWrapper.assistantSettingsModel
                onSelected: (value) => Globals.BackendWrapper.assistantSettingsSetModel(value)
            }
        }

        Components.LabelledField {
            text: qsTr('Other model:')
            EaElements.TextField {
                width: parent.width
                horizontalAlignment: TextInput.AlignLeft
                placeholderText: qsTr('model ID, e.g. for a newer model')
                text: Globals.BackendWrapper.assistantSettingsModelChoices.includes(Globals.BackendWrapper.assistantSettingsModel) ?
                          '' : Globals.BackendWrapper.assistantSettingsModel
                onEditingFinished: if (text.trim() !== '') Globals.BackendWrapper.assistantSettingsSetModel(text)
            }
        }

        Components.LabelledField {
            text: qsTr('Effort:')
            Components.ChoiceComboBox {
                width: parent.width
                choices: Array.from(Globals.BackendWrapper.assistantSettingsEffortChoices, e => ({ value: e, label: e }))
                value: Globals.BackendWrapper.assistantSettingsEffort
                onSelected: (value) => Globals.BackendWrapper.assistantSettingsSetEffort(value)
            }
        }

        // Actions and sharing

        EaElements.Label {
            topPadding: EaStyle.Sizes.fontPixelSize * 0.5
            font.bold: true
            text: qsTr('Actions and sharing')
        }

        Components.LabelledField {
            text: qsTr('Confirm:')
            Components.ChoiceComboBox {
                width: parent.width
                choices: Globals.BackendWrapper.assistantSettingsApprovalModeChoices
                value: Globals.BackendWrapper.assistantSettingsApprovalMode
                onSelected: (value) => Globals.BackendWrapper.assistantSettingsSetApprovalMode(value)
            }
        }

        EaElements.CheckBox {
            text: qsTr('Share engine output and messages')
            checked: Globals.BackendWrapper.assistantSettingsSendOutput
            onToggled: Globals.BackendWrapper.assistantSettingsSetSendOutput(checked)
        }

        EaElements.CheckBox {
            text: qsTr('Share results')
            checked: Globals.BackendWrapper.assistantSettingsSendResults
            onToggled: Globals.BackendWrapper.assistantSettingsSetSendResults(checked)
        }

        EaElements.CheckBox {
            text: qsTr('Offline: never contact the model')
            checked: Globals.BackendWrapper.assistantSettingsOffline
            onToggled: Globals.BackendWrapper.assistantSettingsSetOffline(checked)
        }

        EaElements.Label {
            width: parent.width
            wrapMode: Text.WordWrap
            color: EaStyle.Colors.themeForegroundMinor
            text: qsTr('Usage: %1.').arg(Globals.BackendWrapper.assistantUsageText)
        }
    }
}
