#define _GNU_SOURCE
/* libinput -> a PRIVATE wlroots seat. No uinput, input logging, or compositor hooks. */
#include <errno.h>
#include <fcntl.h>
#include <libinput.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include "virtual-keyboard-unstable-v1-client-protocol.h"
#include "wlr-virtual-pointer-unstable-v1-client-protocol.h"

static volatile sig_atomic_t running = 1;
static struct wl_seat *seat;
static struct zwp_virtual_keyboard_manager_v1 *km;
static struct zwlr_virtual_pointer_manager_v1 *pm;
static struct zwp_virtual_keyboard_v1 *keyboard;
static struct zwlr_virtual_pointer_v1 *pointer;
static struct xkb_state *xstate;
static const char *escape_socket;
static bool super_down, swallowed_m;
static int opened[16], opened_count;

static void stop(int sig) { (void)sig; running = 0; }
static int open_restricted(const char *path, int flags, void *data) {
    (void)data;
    int fd = open(path, flags | O_CLOEXEC);
    if (fd < 0) {fprintf(stderr,"Cannot open assigned input %s: %s (flags %x)\n",path,strerror(errno),flags);return -errno;}
    /* A toggle is pressed on the device being handed over. Wait for its
       release so neither desktop inherits a stuck Super/Ctrl key. */
    unsigned char keys[(KEY_MAX+8)/8];
    for (int tries=0; tries<250; ++tries) {
        memset(keys, 0, sizeof(keys));
        if (ioctl(fd, EVIOCGKEY(sizeof(keys)), keys) < 0) break;
        bool held=false;
        for (unsigned i=0; i<sizeof(keys); ++i) if (keys[i]) held=true;
        if (!held) break;
        if (tries==249) {close(fd);return -EBUSY;}
        usleep(20000);
    }
    if (opened_count >= 16 || ioctl(fd, EVIOCGRAB, 1) < 0) {
        int error = errno ? errno : E2BIG;
        close(fd);
        return -error;
    }
    opened[opened_count++] = fd;
    return fd;
}
static void close_restricted(int fd, void *data) {
    (void)data;
    ioctl(fd, EVIOCGRAB, 0);
    for (int i=0; i<opened_count; ++i) if (opened[i] == fd) opened[i] = -1;
    close(fd);
}
static const struct libinput_interface li_interface = {open_restricted, close_restricted};

static void global(void *data, struct wl_registry *reg, uint32_t id, const char *iface, uint32_t version) {
    (void)data;
    if (!strcmp(iface, wl_seat_interface.name) && !seat)
        seat = wl_registry_bind(reg, id, &wl_seat_interface, 1);
    else if (!strcmp(iface, zwp_virtual_keyboard_manager_v1_interface.name))
        km = wl_registry_bind(reg, id, &zwp_virtual_keyboard_manager_v1_interface, 1);
    else if (!strcmp(iface, zwlr_virtual_pointer_manager_v1_interface.name))
        pm = wl_registry_bind(reg, id, &zwlr_virtual_pointer_manager_v1_interface, version < 2 ? version : 2);
}
static void global_remove(void *data, struct wl_registry *reg, uint32_t id) {(void)data;(void)reg;(void)id;}
static const struct wl_registry_listener registry_listener = {global, global_remove};

static void send_control(const char *message) {
    if (!escape_socket) return;
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    snprintf(address.sun_path, sizeof(address.sun_path), "%s", escape_socket);
    sendto(fd, message, strlen(message), MSG_DONTWAIT, (struct sockaddr*)&address, sizeof(address));
    close(fd);
}
static uint32_t milliseconds(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint32_t)((uint64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000);
}
static void key_event(uint32_t time, uint32_t key, uint32_t state) {
    if (key == KEY_LEFTMETA || key == KEY_RIGHTMETA) super_down = state;
    if (key == KEY_M && super_down && state) {
        swallowed_m = true;
        send_control("pause");running = 0;
        return;
    }
    if (key == KEY_M && swallowed_m) { swallowed_m = false; return; }
    zwp_virtual_keyboard_v1_key(keyboard, time, key, state);
    xkb_state_update_key(xstate, key + 8, state ? XKB_KEY_DOWN : XKB_KEY_UP);
    zwp_virtual_keyboard_v1_modifiers(keyboard,
        xkb_state_serialize_mods(xstate, XKB_STATE_MODS_DEPRESSED),
        xkb_state_serialize_mods(xstate, XKB_STATE_MODS_LATCHED),
        xkb_state_serialize_mods(xstate, XKB_STATE_MODS_LOCKED),
        xkb_state_serialize_layout(xstate, XKB_STATE_LAYOUT_EFFECTIVE));
}
static void process(struct libinput_event *ev) {
    enum libinput_event_type type = libinput_event_get_type(ev);
    uint32_t now = milliseconds();
    static uint32_t last_activity;
    if (type >= LIBINPUT_EVENT_KEYBOARD_KEY && now-last_activity >= 1000) {
        send_control("activity");last_activity=now;
    }
    if (type == LIBINPUT_EVENT_DEVICE_ADDED) {
        struct libinput_device *dev = libinput_event_get_device(ev);
        libinput_device_config_tap_set_enabled(dev, LIBINPUT_CONFIG_TAP_ENABLED);
        libinput_device_config_scroll_set_natural_scroll_enabled(dev, 1);
        libinput_device_config_dwt_set_enabled(dev, LIBINPUT_CONFIG_DWT_ENABLED);
    } else if (type == LIBINPUT_EVENT_DEVICE_REMOVED) {
        /* Release all grabs if either built-in device disappears. */
        running = 0;
    } else if (type == LIBINPUT_EVENT_KEYBOARD_KEY) {
        struct libinput_event_keyboard *e = libinput_event_get_keyboard_event(ev);
        key_event(now, libinput_event_keyboard_get_key(e), libinput_event_keyboard_get_key_state(e));
    } else if (type == LIBINPUT_EVENT_POINTER_MOTION) {
        struct libinput_event_pointer *e = libinput_event_get_pointer_event(ev);
        zwlr_virtual_pointer_v1_motion(pointer, now, wl_fixed_from_double(libinput_event_pointer_get_dx(e)), wl_fixed_from_double(libinput_event_pointer_get_dy(e)));
        zwlr_virtual_pointer_v1_frame(pointer);
    } else if (type == LIBINPUT_EVENT_POINTER_BUTTON) {
        struct libinput_event_pointer *e = libinput_event_get_pointer_event(ev);
        zwlr_virtual_pointer_v1_button(pointer, now, libinput_event_pointer_get_button(e), libinput_event_pointer_get_button_state(e));
        zwlr_virtual_pointer_v1_frame(pointer);
    } else if (type == LIBINPUT_EVENT_POINTER_SCROLL_FINGER || type == LIBINPUT_EVENT_POINTER_SCROLL_WHEEL || type == LIBINPUT_EVENT_POINTER_SCROLL_CONTINUOUS) {
        struct libinput_event_pointer *e = libinput_event_get_pointer_event(ev);
        uint32_t source = type == LIBINPUT_EVENT_POINTER_SCROLL_FINGER ? WL_POINTER_AXIS_SOURCE_FINGER : type == LIBINPUT_EVENT_POINTER_SCROLL_WHEEL ? WL_POINTER_AXIS_SOURCE_WHEEL : WL_POINTER_AXIS_SOURCE_CONTINUOUS;
        zwlr_virtual_pointer_v1_axis_source(pointer, source);
        for (int axis=0; axis<2; ++axis) if (libinput_event_pointer_has_axis(e, axis)) {
            double value = libinput_event_pointer_get_scroll_value(e, axis);
            if (value == 0) zwlr_virtual_pointer_v1_axis_stop(pointer, now, axis);
            else zwlr_virtual_pointer_v1_axis(pointer, now, axis, wl_fixed_from_double(value));
        }
        zwlr_virtual_pointer_v1_frame(pointer);
    }
}
int main(int argc, char **argv) {
    if (argc < 4) {fprintf(stderr,"usage: input-bridge PRIVATE_WAYLAND_SOCKET CONTROL_SOCKET DEVICE...\n");return 2;}
    escape_socket = argv[2];
    signal(SIGTERM, stop);signal(SIGINT, stop);signal(SIGHUP, stop);
    /* Connect and validate the target BEFORE taking any input device. */
    struct wl_display *display = wl_display_connect(argv[1]);
    if (!display) {perror("private Wayland connection");return 1;}
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !seat || !km || !pm) {
        fprintf(stderr,"Private compositor does not provide virtual input\n");return 1;
    }
    pointer = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(pm, seat);
    keyboard = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(km, seat);
    struct xkb_context *xcontext = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
    struct xkb_rule_names names = {.layout="us"};
    struct xkb_keymap *keymap = xkb_keymap_new_from_names(xcontext, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
    if (!keymap) return 1;
    xstate = xkb_state_new(keymap);
    char *text = xkb_keymap_get_as_string(keymap, XKB_KEYMAP_FORMAT_TEXT_V1);
    size_t size = strlen(text) + 1;
    int fd = memfd_create("multiseat-keymap", MFD_CLOEXEC);
    if (fd < 0 || write(fd, text, size) != (ssize_t)size) return 1;
    zwp_virtual_keyboard_v1_keymap(keyboard, WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1, fd, size);
    close(fd);free(text);
    if (wl_display_roundtrip(display) < 0) return 1;
    struct libinput *li = libinput_path_create_context(&li_interface, NULL);
    if (!li) return 1;
    for (int i=3; i<argc; ++i) if (!libinput_path_add_device(li, argv[i])) {
        fprintf(stderr,"Cannot claim assigned device %s; releasing everything\n", argv[i]);
        libinput_unref(li);return 1;
    }
    fprintf(stderr,"READY: independent laptop keyboard and touchpad\n");
    const char *ready = getenv("MULTISEAT_READY_FILE");
    if (ready) {
        FILE *file=fopen(ready,"w");
        if (!file) {libinput_unref(li);return 1;}
        fprintf(file,"%d\n",getpid());fclose(file);
    }
    struct pollfd fds[] = {{libinput_get_fd(li), POLLIN, 0}, {wl_display_get_fd(display), POLLIN, 0}};
    while (running) {
        libinput_dispatch(li);
        struct libinput_event *event;
        while (running && (event = libinput_get_event(li))) {process(event);libinput_event_destroy(event);}
        if (wl_display_dispatch_pending(display) < 0 || wl_display_flush(display) < 0) break;
        if (poll(fds, 2, 250) < 0 && errno != EINTR) break;
        if (fds[1].revents & (POLLHUP | POLLERR)) break;
        if (fds[1].revents & POLLIN) if (wl_display_dispatch(display) < 0) break;
    }
    /* Closing these fds always restores the original compositor's input. */
    libinput_unref(li);
    zwp_virtual_keyboard_v1_destroy(keyboard);
    zwlr_virtual_pointer_v1_destroy(pointer);
    wl_display_flush(display);wl_display_disconnect(display);
    xkb_state_unref(xstate);xkb_keymap_unref(keymap);xkb_context_unref(xcontext);
    return 0;
}
