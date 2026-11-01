pragma Singleton

import QtQuick


// Display choices only the structure viewer reads, set in the Sample page's Display group.
// Choices that change what is drawn (repeat, boundary atoms) are in the backend instead.

QtObject {
    property bool showCell: true
    property bool showAxes: true
}
