// Event API only: no trampolines, function patching, or private-member access.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>
#include <aquamarine/backend/Session.hpp>
#include <hyprland/src/debug/HyprCtl.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <hyprland/src/state/MonitorState.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/protocols/IdleNotify.hpp>
#include <algorithm>
#include <csignal>
#include <cstdlib>
#include <fstream>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static HANDLE handle;
static std::string target;
static bool correcting = false;
static CHyprSignalListener motion, lockListener, sessionListener;
static SP<SHyprCtlCommand> command;

static void pauseSeat() {
    const char* runtime = getenv("XDG_RUNTIME_DIR");
    if (!runtime) return;
    std::string root = std::string(runtime) + "/caelestia-multiseat/";
    // Releasing keyboard grabs must not wait for a shell process or IPC round trip.
    std::ifstream pidFile(root + "input.pid");
    int pid = 0;
    if (pidFile >> pid && pid > 1) {
        char exe[512] = {};
        auto proc = "/proc/" + std::to_string(pid) + "/exe";
        auto size = readlink(proc.c_str(),exe,sizeof(exe)-1);
        if (size > 0 && std::string_view(exe,size) == "/usr/local/libexec/caelestia-multiseat-input") kill(pid, SIGTERM);
    }
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    sockaddr_un address = {.sun_family = AF_UNIX};
    auto path = root + "control.sock";
    if (path.size() < sizeof(address.sun_path)) {
        std::copy(path.begin(), path.end(), address.sun_path);
        sendto(fd, "pause", 5, MSG_DONTWAIT, reinterpret_cast<sockaddr*>(&address), sizeof(address));
    }
    close(fd);
    target.clear();
}
APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle = h;
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Multiseat guard ABI mismatch; leaving normal input intact");
    motion = Event::bus()->m_events.input.mouse.move.listen([](const Vector2D& pos, Event::SCallbackInfo& info) {
        if (target.empty() || correcting || g_pSessionLockManager->isSessionLocked()) return;
        PHLMONITOR mon;
        for (const auto& m : State::monitorState()->monitors()) if (m->m_name == target && !m->m_mirrorOf) {mon=m;break;}
        if (!mon) {pauseSeat();return;}
        Vector2D clipped = {std::clamp(pos.x, mon->m_position.x, mon->m_position.x + mon->m_size.x - 1),
                            std::clamp(pos.y, mon->m_position.y, mon->m_position.y + mon->m_size.y - 1)};
        if (pos == clipped) return;
        info.cancelled = true;
        correcting = true;
        Pointer::mgr()->warpTo(clipped);
        g_pInputManager->simulateMouseMovement();
        correcting = false;
    });
    lockListener = g_pSessionLockManager->m_events.lock.listen([] {pauseSeat();});
    if (g_pCompositor->m_aqBackend->session)
        sessionListener = g_pCompositor->m_aqBackend->session->events.changeActive.listen([] {
            if (!g_pCompositor->m_aqBackend->session->active) pauseSeat();
        });
    command = HyprlandAPI::registerHyprCtlCommand(handle, SHyprCtlCommand{
        .name="caelestiamultiseat", .exact=false,
        .fn=[](eHyprCtlOutputFormat, std::string args) {
            auto start=args.find(' ');
            auto output = start == std::string::npos ? std::string() : args.substr(start+1);
            if (output == "activity") {PROTO::idle->onActivity();return std::string("ok");}
            if (output == "off") {target.clear();return std::string("ok");}
            for (const auto& m : State::monitorState()->monitors()) if (m->m_name == output && !m->m_mirrorOf) {
                target=output;return std::string("ok");
            }
            return std::string("error: joined output unavailable");
        }});
    return {"caelestia-multiseat-guard", "Constrain the main pointer while a second seat is active", "Caelestia", "1.0"};
}
APICALL EXPORT void PLUGIN_EXIT() {
    pauseSeat();motion.reset();lockListener.reset();sessionListener.reset();command.reset();
}
