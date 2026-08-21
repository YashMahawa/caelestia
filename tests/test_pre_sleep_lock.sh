#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRE_SLEEP_LOCK="$(cd "$SCRIPT_DIR/../bin" && pwd)/caelestia-pre-sleep-lock"

TEST_COUNT=0
PASSED_COUNT=0

pass() {
    PASSED_COUNT=$((PASSED_COUNT + 1))
    printf '  \033[32m[PASS]\033[0m %s\n' "$1"
}

fail() {
    printf '  \033[31m[FAIL]\033[0m %s: %s\n' "$1" "$2"
}

run_test() {
    local test_name="$1"
    TEST_COUNT=$((TEST_COUNT + 1))
    printf 'Running test %d: %s...\n' "$TEST_COUNT" "$test_name"
}

# Cleanup temporary test directories on exit
TEST_TMP=""
cleanup() {
    if [[ -n "$TEST_TMP" && -d "$TEST_TMP" ]]; then
        rm -rf "$TEST_TMP"
    fi
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Test 1: Active session locking succeeds
# -----------------------------------------------------------------------------
run_test "Active graphical user session succeeds locking and sleep is allowed"
TEST_TMP="$(mktemp -d)"

MOCK_BIN="${TEST_TMP}/bin"
mkdir -p "$MOCK_BIN"

# Mock loginctl
cat << 'EOF' > "${MOCK_BIN}/loginctl"
#!/usr/bin/env bash
cmd="$1"
shift
if [[ "$cmd" == "list-sessions" ]]; then
    echo "2 1000 alice desktop"
elif [[ "$cmd" == "show-session" ]]; then
    sid="$1"
    prop="$2"
    if [[ "$prop" == "-p" ]]; then
        prop="$3"
    fi
    case "$prop" in
        Active) echo "yes" ;;
        Remote) echo "no" ;;
        Type) echo "wayland" ;;
        Class) echo "user" ;;
        User) echo "1000" ;;
        Name) echo "alice" ;;
        *) echo "" ;;
    esac
fi
EOF
chmod +x "${MOCK_BIN}/loginctl"

# Mock getent
cat << 'EOF' > "${MOCK_BIN}/getent"
#!/usr/bin/env bash
if [[ "$1" == "passwd" ]]; then
    echo "alice:x:1000:1000:Alice:/home/alice:/bin/bash"
fi
EOF
chmod +x "${MOCK_BIN}/getent"

# Mock IPC
IPC_BIN="${TEST_TMP}/caelestia-qs-ipc"
cat << 'EOF' > "$IPC_BIN"
#!/usr/bin/env bash
if [[ "$1" == "lock" && "$2" == "safeLock" ]]; then
    exit 0
elif [[ "$1" == "lock" && "$2" == "isLocked" ]]; then
    echo "true"
    exit 0
fi
EOF
chmod +x "$IPC_BIN"

OUTPUT_FILE="${TEST_TMP}/output.log"
set +e
CAELESTIA_TEST_NO_SETPRIV=1 \
CAELESTIA_IPC_PATH="$IPC_BIN" \
CAELESTIA_LOGIND_RETRIES=1 \
LOGINCTL="${MOCK_BIN}/loginctl" \
GETENT="${MOCK_BIN}/getent" \
"$PRE_SLEEP_LOCK" >"$OUTPUT_FILE" 2>&1
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 0 ]] && grep -q "secure lock confirmed" "$OUTPUT_FILE"; then
    pass "Active graphical session locked successfully"
else
    fail "Active graphical session locking" "Expected exit code 0 and lock confirmed message, got exit $EXIT_CODE. Output: $(cat "$OUTPUT_FILE")"
fi
rm -rf "$TEST_TMP"

# -----------------------------------------------------------------------------
# Test 2: SDDM / no user session allows sleep
# -----------------------------------------------------------------------------
run_test "SDDM / no graphical user session allows sleep (exit 0)"
TEST_TMP="$(mktemp -d)"

MOCK_BIN="${TEST_TMP}/bin"
mkdir -p "$MOCK_BIN"

# Mock loginctl with only greeter session (SDDM)
cat << 'EOF' > "${MOCK_BIN}/loginctl"
#!/usr/bin/env bash
cmd="$1"
shift
if [[ "$cmd" == "list-sessions" ]]; then
    echo "1 990 sddm display"
elif [[ "$cmd" == "show-session" ]]; then
    sid="$1"
    prop="$2"
    if [[ "$prop" == "-p" ]]; then
        prop="$3"
    fi
    case "$prop" in
        Active) echo "yes" ;;
        Remote) echo "no" ;;
        Type) echo "x11" ;;
        Class) echo "greeter" ;;
        User) echo "990" ;;
        Name) echo "sddm" ;;
        *) echo "" ;;
    esac
fi
EOF
chmod +x "${MOCK_BIN}/loginctl"

OUTPUT_FILE="${TEST_TMP}/output.log"
set +e
CAELESTIA_TEST_NO_SETPRIV=1 \
CAELESTIA_LOGIND_RETRIES=2 \
CAELESTIA_LOGIND_DELAY=0.01 \
LOGINCTL="${MOCK_BIN}/loginctl" \
"$PRE_SLEEP_LOCK" >"$OUTPUT_FILE" 2>&1
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 0 ]] && grep -q "no active graphical user session found; allowing sleep" "$OUTPUT_FILE"; then
    pass "SDDM / no user session allows sleep with exit code 0"
else
    fail "SDDM / no user session" "Expected exit 0 and 'no active graphical user session found', got exit $EXIT_CODE. Output: $(cat "$OUTPUT_FILE")"
fi
rm -rf "$TEST_TMP"

# -----------------------------------------------------------------------------
# Test 3: Disappearing session allows sleep
# -----------------------------------------------------------------------------
run_test "Disappearing session mid-way allows sleep (exit 0)"
TEST_TMP="$(mktemp -d)"

MOCK_BIN="${TEST_TMP}/bin"
mkdir -p "$MOCK_BIN"

STATE_FILE="${TEST_TMP}/state.txt"
echo "0" > "$STATE_FILE"

# Mock loginctl: first show-session returns Active=yes, subsequent calls return Active=no
cat << EOF > "${MOCK_BIN}/loginctl"
#!/usr/bin/env bash
cmd="\$1"
shift
if [[ "\$cmd" == "list-sessions" ]]; then
    echo "2 1000 alice desktop"
elif [[ "\$cmd" == "show-session" ]]; then
    sid="\$1"
    prop="\$2"
    if [[ "\$prop" == "-p" ]]; then
        prop="\$3"
    fi
    
    count=\$(cat "$STATE_FILE")
    count=\$((count + 1))
    echo "\$count" > "$STATE_FILE"

    case "\$prop" in
        Active)
            if [[ \$count -le 4 ]]; then
                echo "yes"
            else
                echo "no"
            fi
            ;;
        Remote) echo "no" ;;
        Type) echo "wayland" ;;
        Class) echo "user" ;;
        User) echo "1000" ;;
        Name) echo "alice" ;;
        *) echo "" ;;
    esac
fi
EOF
chmod +x "${MOCK_BIN}/loginctl"

cat << 'EOF' > "${MOCK_BIN}/getent"
#!/usr/bin/env bash
if [[ "$1" == "passwd" ]]; then
    echo "alice:x:1000:1000:Alice:/home/alice:/bin/bash"
fi
EOF
chmod +x "${MOCK_BIN}/getent"

# IPC fails because session disappeared
IPC_BIN="${TEST_TMP}/caelestia-qs-ipc"
cat << 'EOF' > "$IPC_BIN"
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$IPC_BIN"

OUTPUT_FILE="${TEST_TMP}/output.log"
set +e
CAELESTIA_TEST_NO_SETPRIV=1 \
CAELESTIA_IPC_PATH="$IPC_BIN" \
CAELESTIA_LOGIND_RETRIES=1 \
LOGINCTL="${MOCK_BIN}/loginctl" \
GETENT="${MOCK_BIN}/getent" \
"$PRE_SLEEP_LOCK" >"$OUTPUT_FILE" 2>&1
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 0 ]] && grep -q "disappeared" "$OUTPUT_FILE"; then
    pass "Disappearing session handled gracefully allowing sleep"
else
    fail "Disappearing session" "Expected exit 0 and session disappeared log, got exit $EXIT_CODE. Output: $(cat "$OUTPUT_FILE")"
fi
rm -rf "$TEST_TMP"

# -----------------------------------------------------------------------------
# Test 4: IPC timeout fails closed
# -----------------------------------------------------------------------------
run_test "IPC timeout fails closed (exit 1)"
TEST_TMP="$(mktemp -d)"

MOCK_BIN="${TEST_TMP}/bin"
mkdir -p "$MOCK_BIN"

cat << 'EOF' > "${MOCK_BIN}/loginctl"
#!/usr/bin/env bash
cmd="$1"
shift
if [[ "$cmd" == "list-sessions" ]]; then
    echo "2 1000 alice desktop"
elif [[ "$cmd" == "show-session" ]]; then
    sid="$1"
    prop="$2"
    if [[ "$prop" == "-p" ]]; then
        prop="$3"
    fi
    case "$prop" in
        Active) echo "yes" ;;
        Remote) echo "no" ;;
        Type) echo "wayland" ;;
        Class) echo "user" ;;
        User) echo "1000" ;;
        Name) echo "alice" ;;
        *) echo "" ;;
    esac
fi
EOF
chmod +x "${MOCK_BIN}/loginctl"

cat << 'EOF' > "${MOCK_BIN}/getent"
#!/usr/bin/env bash
if [[ "$1" == "passwd" ]]; then
    echo "alice:x:1000:1000:Alice:/home/alice:/bin/bash"
fi
EOF
chmod +x "${MOCK_BIN}/getent"

# Mock IPC hanging/timing out
IPC_BIN="${TEST_TMP}/caelestia-qs-ipc"
cat << 'EOF' > "$IPC_BIN"
#!/usr/bin/env bash
sleep 10
exit 0
EOF
chmod +x "$IPC_BIN"

OUTPUT_FILE="${TEST_TMP}/output.log"
set +e
CAELESTIA_TEST_NO_SETPRIV=1 \
CAELESTIA_IPC_PATH="$IPC_BIN" \
CAELESTIA_LOGIND_RETRIES=1 \
CAELESTIA_LOCK_ACK_TIMEOUT=1 \
LOGINCTL="${MOCK_BIN}/loginctl" \
GETENT="${MOCK_BIN}/getent" \
"$PRE_SLEEP_LOCK" >"$OUTPUT_FILE" 2>&1
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 1 ]] && grep -q "lock request failed; refusing unsafe sleep" "$OUTPUT_FILE"; then
    pass "IPC timeout fails closed with exit code 1"
else
    fail "IPC timeout" "Expected exit code 1 and lock request failed log, got exit $EXIT_CODE. Output: $(cat "$OUTPUT_FILE")"
fi
rm -rf "$TEST_TMP"

# -----------------------------------------------------------------------------
# Test 5: Logind state settling retries
# -----------------------------------------------------------------------------
run_test "Logind state settling retries before finding active session"
TEST_TMP="$(mktemp -d)"

MOCK_BIN="${TEST_TMP}/bin"
mkdir -p "$MOCK_BIN"

STATE_FILE="${TEST_TMP}/retry_state.txt"
echo "0" > "$STATE_FILE"

# Mock loginctl: list-sessions returns empty on 1st call, session on 2nd call
cat << EOF > "${MOCK_BIN}/loginctl"
#!/usr/bin/env bash
cmd="\$1"
shift
count=\$(cat "$STATE_FILE")
count=\$((count + 1))
echo "\$count" > "$STATE_FILE"

if [[ "\$cmd" == "list-sessions" ]]; then
    if [[ \$count -eq 1 ]]; then
        exit 0
    else
        echo "2 1000 alice desktop"
    fi
elif [[ "\$cmd" == "show-session" ]]; then
    sid="\$1"
    prop="\$2"
    if [[ "\$prop" == "-p" ]]; then
        prop="\$3"
    fi
    case "\$prop" in
        Active) echo "yes" ;;
        Remote) echo "no" ;;
        Type) echo "wayland" ;;
        Class) echo "user" ;;
        User) echo "1000" ;;
        Name) echo "alice" ;;
        *) echo "" ;;
    esac
fi
EOF
chmod +x "${MOCK_BIN}/loginctl"

cat << 'EOF' > "${MOCK_BIN}/getent"
#!/usr/bin/env bash
if [[ "$1" == "passwd" ]]; then
    echo "alice:x:1000:1000:Alice:/home/alice:/bin/bash"
fi
EOF
chmod +x "${MOCK_BIN}/getent"

IPC_BIN="${TEST_TMP}/caelestia-qs-ipc"
cat << 'EOF' > "$IPC_BIN"
#!/usr/bin/env bash
if [[ "$1" == "lock" && "$2" == "safeLock" ]]; then
    exit 0
elif [[ "$1" == "lock" && "$2" == "isLocked" ]]; then
    echo "true"
    exit 0
fi
EOF
chmod +x "$IPC_BIN"

OUTPUT_FILE="${TEST_TMP}/output.log"
set +e
CAELESTIA_TEST_NO_SETPRIV=1 \
CAELESTIA_IPC_PATH="$IPC_BIN" \
CAELESTIA_LOGIND_RETRIES=3 \
CAELESTIA_LOGIND_DELAY=0.01 \
LOGINCTL="${MOCK_BIN}/loginctl" \
GETENT="${MOCK_BIN}/getent" \
"$PRE_SLEEP_LOCK" >"$OUTPUT_FILE" 2>&1
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 0 ]] && grep -q "secure lock confirmed" "$OUTPUT_FILE"; then
    pass "Logind state settling successfully resolves session on retry"
else
    fail "Logind state settling" "Expected exit code 0 on retry, got exit $EXIT_CODE. Output: $(cat "$OUTPUT_FILE")"
fi
rm -rf "$TEST_TMP"

# -----------------------------------------------------------------------------
# Test 6: Lock confirmation timeout fails closed
# -----------------------------------------------------------------------------
run_test "Lock confirmation timeout fails closed (exit 1)"
TEST_TMP="$(mktemp -d)"

MOCK_BIN="${TEST_TMP}/bin"
mkdir -p "$MOCK_BIN"

cat << 'EOF' > "${MOCK_BIN}/loginctl"
#!/usr/bin/env bash
cmd="$1"
shift
if [[ "$cmd" == "list-sessions" ]]; then
    echo "2 1000 alice desktop"
elif [[ "$cmd" == "show-session" ]]; then
    sid="$1"
    prop="$2"
    if [[ "$prop" == "-p" ]]; then
        prop="$3"
    fi
    case "$prop" in
        Active) echo "yes" ;;
        Remote) echo "no" ;;
        Type) echo "wayland" ;;
        Class) echo "user" ;;
        User) echo "1000" ;;
        Name) echo "alice" ;;
        *) echo "" ;;
    esac
fi
EOF
chmod +x "${MOCK_BIN}/loginctl"

cat << 'EOF' > "${MOCK_BIN}/getent"
#!/usr/bin/env bash
if [[ "$1" == "passwd" ]]; then
    echo "alice:x:1000:1000:Alice:/home/alice:/bin/bash"
fi
EOF
chmod +x "${MOCK_BIN}/getent"

# IPC safeLock succeeds, but isLocked returns false
IPC_BIN="${TEST_TMP}/caelestia-qs-ipc"
cat << 'EOF' > "$IPC_BIN"
#!/usr/bin/env bash
if [[ "$1" == "lock" && "$2" == "safeLock" ]]; then
    exit 0
elif [[ "$1" == "lock" && "$2" == "isLocked" ]]; then
    echo "false"
    exit 0
fi
EOF
chmod +x "$IPC_BIN"

OUTPUT_FILE="${TEST_TMP}/output.log"
set +e
CAELESTIA_TEST_NO_SETPRIV=1 \
CAELESTIA_IPC_PATH="$IPC_BIN" \
CAELESTIA_LOGIND_RETRIES=1 \
CAELESTIA_LOCK_CONFIRM_RETRIES=2 \
CAELESTIA_LOCK_CONFIRM_INTERVAL=0.01 \
LOGINCTL="${MOCK_BIN}/loginctl" \
GETENT="${MOCK_BIN}/getent" \
"$PRE_SLEEP_LOCK" >"$OUTPUT_FILE" 2>&1
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 1 ]] && grep -q "secure lock confirmation timed out; refusing unsafe sleep" "$OUTPUT_FILE"; then
    pass "Lock confirmation timeout fails closed with exit code 1"
else
    fail "Lock confirmation timeout" "Expected exit code 1 and confirmation timed out log, got exit $EXIT_CODE. Output: $(cat "$OUTPUT_FILE")"
fi
rm -rf "$TEST_TMP"

# -----------------------------------------------------------------------------
# Test Summary
# -----------------------------------------------------------------------------
printf '\nTest Summary: %d / %d tests passed.\n' "$PASSED_COUNT" "$TEST_COUNT"
if [[ $PASSED_COUNT -ne $TEST_COUNT ]]; then
    exit 1
fi
exit 0
