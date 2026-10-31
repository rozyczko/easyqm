import QtQuick

import EasyApplication.Gui.Elements as EaElements


// Combo box over a backend choice list `[{value, label}]`, showing the backend `value`.
// The selection is reported through `selected`; the backend setter updates `value`.
//
// The model is the list of labels, not the list of objects with a textRole: the
// EasyApplication delegate reads `model[textRole]` unless `Array.isArray(control.model)`,
// and a list that went through the `model` property never passes that check, so the popup
// items came out empty. Plain strings take the `modelData` path.
EaElements.ComboBox {
    id: control

    property var choices: []
    property string value: ''
    signal selected(string value)

    model: Array.from(choices ?? [], choice => choice.label)

    onActivated: (index) => selected(choices[index].value)
    onValueChanged: syncIndex()
    onChoicesChanged: syncIndex()
    Component.onCompleted: syncIndex()

    function syncIndex() {
        currentIndex = Array.from(choices ?? []).findIndex(choice => choice.value === value)
    }
}
