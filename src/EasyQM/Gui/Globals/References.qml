pragma Singleton

import QtQuick


// Objects that need to be reached from any other qml file. Filled in when the object is created.

QtObject {
    property var applicationWindow: null
}
