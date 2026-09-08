#include <QCoreApplication>
#include <QGuiApplication>
#include <QTimer>
#include <QDebug>
#include <qpa/qplatformscreen.h>
#include <qpa/qwindowsysteminterface.h>
#include <dlfcn.h>

// Test-only process injection: synthetic outputs in Qt's offscreen backend.
// Never loaded into the user's desktop process.
class TestScreen final : public QPlatformScreen {
public:
    QRect geometry() const override { return {800, 0, 640, 480}; }
    int depth() const override { return 32; }
    QImage::Format format() const override { return QImage::Format_ARGB32_Premultiplied; }
    QString name() const override { return QStringLiteral("TEST-HOTPLUG"); }
};

int QCoreApplication::exec() {
    using Exec = int (*)();
    auto realExec = reinterpret_cast<Exec>(dlsym(RTLD_NEXT, "_ZN16QCoreApplication4execEv"));
    if (!realExec || qEnvironmentVariable("QT_QPA_PLATFORM") != "offscreen")
        qFatal("Screen-cycle test requires isolated offscreen backend");
    auto *timer = new QTimer(QCoreApplication::instance());
    timer->setInterval(50);
    QObject::connect(timer, &QTimer::timeout, timer, [timer, screen = static_cast<TestScreen*>(nullptr), cycles = 0]() mutable {
        if (!screen) {
            screen = new TestScreen();
            QWindowSystemInterface::handleScreenAdded(screen);
        } else {
            QWindowSystemInterface::handleScreenRemoved(screen);
            // Qt owns deletion of both QScreen and QPlatformScreen here.
            screen = nullptr;
            if (++cycles == 100) {
                timer->stop();
                qInfo("SCREEN-CYCLE: 100 add/remove cycles completed");
                QTimer::singleShot(250, QCoreApplication::instance(), [] { QCoreApplication::quit(); });
            }
        }
    });
    timer->start();
    return realExec();
}
