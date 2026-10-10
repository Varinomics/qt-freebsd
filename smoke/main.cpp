#include <QGuiApplication>
#include <QImage>
#include <QObject>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QString>
#include <QTest>
#include <QUrl>
#include <QtCore/qtenvironmentvariables.h>
#include <rhi/qrhi.h>
#include <cstdio>

int main(int argc, char* argv[])
{
    QGuiApplication application(argc, argv);
    QQmlApplicationEngine engine;
    engine.loadData(R"(
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes

Window {
    visible: true
    width: 160
    height: 120
    color: "#17324d"
    ColumnLayout {
        anchors.fill: parent
        Label { text: "FreeBSD Qt SDK" }
        Shape {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ShapePath {
                strokeColor: "white"
                startX: 8
                startY: 8
                PathLine { x: 48; y: 32 }
            }
        }
    }
}
)", QUrl("sdk-smoke.qml"));
    if (engine.rootObjects().isEmpty()) {
        std::fprintf(stderr, "Qt SDK cannot instantiate its required QML modules.\n");
        return 1;
    }
    auto* window = qobject_cast<QQuickWindow*>(engine.rootObjects().first());
    if (!window || !QTest::qWaitForWindowExposed(window)) {
        std::fprintf(stderr, "Qt SDK cannot expose a Quick window.\n");
        return 1;
    }
    if (window->grabWindow().isNull()) {
        std::fprintf(stderr, "Qt SDK cannot render and capture a Quick frame.\n");
        return 1;
    }
    if (qEnvironmentVariable("QT_QPA_PLATFORM") == "xcb" &&
        window->rendererInterface()->graphicsApi() != QSGRendererInterface::OpenGL)
    {
        std::fprintf(stderr, "The XCB SDK check did not exercise OpenGL.\n");
        return 1;
    }
    return 0;
}
