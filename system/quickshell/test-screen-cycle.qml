pragma ComponentBehavior: Bound
import QtQuick
import Quickshell

Scope {
    Variants {
        model: Quickshell.screens
        FloatingWindow {
            id: win
            required property ShellScreen modelData
            screen: modelData
            implicitWidth: 320
            implicitHeight: 200
            visible: true
            Rectangle {
                anchors.fill: parent
                color: "#183e41"
                Text {
                    anchors.centerIn: parent
                    text: win.modelData.name + " " + win.modelData.width
                }
            }
        }
    }
}
