import importlib.machinery
import importlib.util
import socket
from unittest.mock import patch, MagicMock

# Load caelestia-display module dynamically
loader = importlib.machinery.SourceFileLoader('caelestia_display', '/app/caelestia/bin/caelestia-display')
spec = importlib.util.spec_from_loader(loader.name, loader)
caelestia_display = importlib.util.module_from_spec(spec)
loader.exec_module(caelestia_display)


def test_resume_grace_constants():
    assert caelestia_display.RESUME_GRACE_SECONDS == 2.0
    assert caelestia_display.SUSPEND_OFFSET_THRESHOLD == 0.5


def test_is_display_ready_single_monitor():
    with patch.object(caelestia_display, 'connected_output_names', return_value=['eDP-1']), \
         patch.object(caelestia_display, 'monitors', return_value=[
             {'name': 'eDP-1', 'width': 1920, 'height': 1080, 'scale': 1.0, 'disabled': False}
         ]):
        assert caelestia_display.is_display_ready() is True


def test_is_display_ready_multi_monitor_settled():
    with patch.object(caelestia_display, 'connected_output_names', return_value=['eDP-1', 'HDMI-A-1']), \
         patch.object(caelestia_display, 'monitors', return_value=[
             {'name': 'eDP-1', 'width': 1920, 'height': 1080, 'scale': 1.0, 'disabled': False},
             {'name': 'HDMI-A-1', 'width': 3840, 'height': 2160, 'scale': 2.0, 'disabled': False}
         ]):
        assert caelestia_display.is_display_ready() is True


def test_is_display_ready_multi_monitor_unsettled():
    # DRM lists HDMI-A-1 as connected, but Hyprland IPC hasn't registered it yet
    with patch.object(caelestia_display, 'connected_output_names', return_value=['eDP-1', 'HDMI-A-1']), \
         patch.object(caelestia_display, 'monitors', return_value=[
             {'name': 'eDP-1', 'width': 1920, 'height': 1080, 'scale': 1.0, 'disabled': False}
         ]):
        assert caelestia_display.is_display_ready() is False


def test_is_display_ready_invalid_geometry():
    with patch.object(caelestia_display, 'connected_output_names', return_value=['eDP-1']), \
         patch.object(caelestia_display, 'monitors', return_value=[
             {'name': 'eDP-1', 'width': 0, 'height': 0, 'scale': 1.0, 'disabled': False}
         ]):
        assert caelestia_display.is_display_ready() is False


def test_is_display_ready_headless_only():
    with patch.object(caelestia_display, 'connected_output_names', return_value=[]), \
         patch.object(caelestia_display, 'monitors', return_value=[
             {'name': 'HEADLESS-1', 'width': 1920, 'height': 1080, 'scale': 1.0, 'disabled': False}
         ]):
        assert caelestia_display.is_display_ready() is False


def test_is_display_ready_empty_monitors():
    with patch.object(caelestia_display, 'connected_output_names', return_value=['eDP-1']), \
         patch.object(caelestia_display, 'monitors', return_value=[]):
        assert caelestia_display.is_display_ready() is False


def test_suspend_clock_offset():
    offset = caelestia_display.suspend_clock_offset()
    assert isinstance(offset, float)
    assert offset >= 0.0


def test_watch_dynamic_grace_termination():
    mock_socket = MagicMock()
    # First recv times out, second returns EOF b"", then second socket attempt raises KeyboardInterrupt
    mock_socket.recv.side_effect = [socket.timeout(), b""]
    
    with patch("socket.socket", side_effect=[mock_socket, KeyboardInterrupt]), \
         patch.object(caelestia_display, "event_socket_path", return_value="/tmp/test.sock"), \
         patch.object(caelestia_display, "apply_automatic") as mock_apply, \
         patch.object(caelestia_display, "sync_shell_to_external_state") as mock_sync, \
         patch.object(caelestia_display, "suspend_clock_offset", side_effect=[0.0, 1.0, 1.0, 1.0, 1.0]), \
         patch.object(caelestia_display, "is_display_ready", return_value=True):
        
        caelestia_display.watch()
        
        # Verify apply_automatic and sync_shell_to_external_state were called post-resume
        assert mock_apply.called
        assert mock_sync.called


def test_watch_upper_limit_timeout_cap():
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [socket.timeout(), socket.timeout(), b""]

    # Monotonic timestamps: t=10.0, t=10.0 (suspend check), t=12.1 (surpasses 2.0s grace cap), t=12.1
    time_mock_values = [10.0, 10.0, 12.1, 12.1, 12.1, 12.1, 12.1]

    with patch("socket.socket", side_effect=[mock_socket, KeyboardInterrupt]), \
         patch.object(caelestia_display, "event_socket_path", return_value="/tmp/test.sock"), \
         patch.object(caelestia_display, "apply_automatic") as mock_apply, \
         patch.object(caelestia_display, "sync_shell_to_external_state") as mock_sync, \
         patch("time.monotonic", side_effect=time_mock_values), \
         patch.object(caelestia_display, "suspend_clock_offset", side_effect=[0.0, 1.0, 1.0, 1.0, 1.0]), \
         patch.object(caelestia_display, "is_display_ready", return_value=False):

        caelestia_display.watch()

        # Even though is_display_ready stayed False, 2.0s upper limit timeout cap triggered reconciliation
        assert mock_apply.called
        assert mock_sync.called

