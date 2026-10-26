#define _GNU_SOURCE
/* Private Sway virtual input. The CLI validates its managed socket first. No evdev/uinput. */
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <sys/mman.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <limits.h>
#include "virtual-keyboard-unstable-v1-client-protocol.h"
#include "wlr-virtual-pointer-unstable-v1-client-protocol.h"

struct test_seat { struct wl_seat *seat; char name[128]; };
static struct test_seat seats[16];
static unsigned seat_count;
static struct zwp_virtual_keyboard_manager_v1 *keyboards;
static struct zwlr_virtual_pointer_manager_v1 *pointers;
static void caps(void *data, struct wl_seat *seat, uint32_t cap) { (void)data; (void)seat; (void)cap; }
static void name(void *data, struct wl_seat *seat, const char *value) {
    (void)seat;
    snprintf(((struct test_seat *)data)->name, 128, "%s", value);
}
static const struct wl_seat_listener seat_listener = {caps, name};
static void global(void *data, struct wl_registry *registry, uint32_t id, const char *interface, uint32_t version) {
    (void)data;
    if (!strcmp(interface, "wl_seat") && seat_count < 16) {
        struct test_seat *seat = &seats[seat_count++];
        seat->seat = wl_registry_bind(registry, id, &wl_seat_interface, version < 9 ? version : 9);
        wl_seat_add_listener(seat->seat, &seat_listener, seat);
    } else if (!strcmp(interface, "zwp_virtual_keyboard_manager_v1"))
        keyboards = wl_registry_bind(registry, id, &zwp_virtual_keyboard_manager_v1_interface, 1);
    else if (!strcmp(interface, "zwlr_virtual_pointer_manager_v1"))
        pointers = wl_registry_bind(registry, id, &zwlr_virtual_pointer_manager_v1_interface, version < 2 ? version : 2);
}
static void removed(void *data, struct wl_registry *registry, uint32_t id) { (void)data; (void)registry; (void)id; }
static const struct wl_registry_listener registry_listener = {global, removed};
static uint32_t now(void) {
    struct timespec time;
    clock_gettime(CLOCK_MONOTONIC, &time);
    return (uint32_t)((uint64_t)time.tv_sec * 1000 + time.tv_nsec / 1000000);
}

int main(int argc, char **argv) {
    char resolved[PATH_MAX], expected[PATH_MAX];
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    if (!runtime || argc != 3 || strcmp(argv[2], "seat0") || !realpath(argv[1], resolved)) return 2;
    snprintf(expected, sizeof(expected), "%s/caelestia-multiseat/wayland.sock", runtime);
    char managed[PATH_MAX];
    if (!realpath(expected, managed) || strcmp(resolved, managed) || !getenv("CAELESTIA_AGENT_DESKTOP")) {
        fprintf(stderr, "Refusing input outside the managed private desktop\n"); return 2;
    }
    struct wl_display *display = wl_display_connect(resolved);
    if (!display) return 3;
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(display) < 0 || wl_display_roundtrip(display) < 0) return 4;
    struct wl_seat *selected = NULL;
    for (unsigned i = 0; i < seat_count; ++i)
        if (!strcmp(seats[i].name, argv[2])) selected = seats[i].seat;
    if (!selected || !keyboards || !pointers) return 5;
    struct zwp_virtual_keyboard_v1 *keyboard = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(keyboards, selected);
    struct zwlr_virtual_pointer_v1 *pointer = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(pointers, selected);
    struct xkb_context *context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
    const struct xkb_rule_names rules = {.rules="evdev", .model="pc105", .layout="us"};
    struct xkb_keymap *keymap = xkb_keymap_new_from_names(context, &rules, XKB_KEYMAP_COMPILE_NO_FLAGS);
    if (!keymap) return 6;
    struct xkb_state *state = xkb_state_new(keymap);
    char *text = xkb_keymap_get_as_string(keymap, XKB_KEYMAP_FORMAT_TEXT_V1);
    size_t size = strlen(text) + 1;
    int fd = memfd_create("native-seat-test-keymap", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, size) || pwrite(fd, text, size, 0) != (ssize_t)size) return 7;
    zwp_virtual_keyboard_v1_keymap(keyboard, WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1, fd, size);
    close(fd); free(text);
    if (wl_display_roundtrip(display) < 0) return 8;
    puts("ready"); fflush(stdout);
    char line[256], command[32];
    while (fgets(line, sizeof(line), stdin)) {
        unsigned code, pressed, x, y, width, height;
        double dx, dy;
        command[0] = 0;
        sscanf(line, "%31s", command);
        if (!strcmp(command, "quit")) break;
        if (sscanf(line, "key %u %u", &code, &pressed) == 2) {
            zwp_virtual_keyboard_v1_key(keyboard, now(), code, pressed);
            xkb_state_update_key(state, code + 8, pressed ? XKB_KEY_DOWN : XKB_KEY_UP);
            zwp_virtual_keyboard_v1_modifiers(keyboard,
                xkb_state_serialize_mods(state, XKB_STATE_MODS_DEPRESSED),
                xkb_state_serialize_mods(state, XKB_STATE_MODS_LATCHED),
                xkb_state_serialize_mods(state, XKB_STATE_MODS_LOCKED),
                xkb_state_serialize_layout(state, XKB_STATE_LAYOUT_EFFECTIVE));
        } else if (sscanf(line, "move %lf %lf", &dx, &dy) == 2) {
            zwlr_virtual_pointer_v1_motion(pointer, now(), wl_fixed_from_double(dx), wl_fixed_from_double(dy));
            zwlr_virtual_pointer_v1_frame(pointer);
        } else if (sscanf(line, "abs %u %u %u %u", &x, &y, &width, &height) == 4) {
            zwlr_virtual_pointer_v1_motion_absolute(pointer, now(), x, y, width, height);
            zwlr_virtual_pointer_v1_frame(pointer);
        } else if (sscanf(line, "button %u %u", &code, &pressed) == 2) {
            zwlr_virtual_pointer_v1_button(pointer, now(), code, pressed);
            zwlr_virtual_pointer_v1_frame(pointer);
        } else if (sscanf(line, "scroll %lf %lf", &dx, &dy) == 2) {
            zwlr_virtual_pointer_v1_axis_source(pointer, WL_POINTER_AXIS_SOURCE_WHEEL);
            if (dx) zwlr_virtual_pointer_v1_axis_discrete(pointer, now(), WL_POINTER_AXIS_HORIZONTAL_SCROLL,
                wl_fixed_from_double(dx * 15), (int)dx);
            if (dy) zwlr_virtual_pointer_v1_axis_discrete(pointer, now(), WL_POINTER_AXIS_VERTICAL_SCROLL,
                wl_fixed_from_double(dy * 15), (int)dy);
            zwlr_virtual_pointer_v1_frame(pointer);
        } else if (sscanf(line, "sleep %u", &code) == 1) {
            usleep(code * 1000);
        } else if (strcmp(command, "sync")) {
            fprintf(stderr, "Unknown test input command\n"); return 9;
        }
        if (wl_display_roundtrip(display) < 0) return 10;
        puts("ok"); fflush(stdout);
    }
    zwlr_virtual_pointer_v1_destroy(pointer);
    zwp_virtual_keyboard_v1_destroy(keyboard);
    wl_display_roundtrip(display);
    xkb_state_unref(state); xkb_keymap_unref(keymap); xkb_context_unref(context);
    wl_display_disconnect(display);
    return 0;
}
