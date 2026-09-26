"""Portable host probes never invent measurements, signal Windows PIDs, or hang."""
import ctypes
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import companion_platform as platform
from kit.app import local_models
from kit.app.terminal import Console


def test_process_existence_distinguishes_missing_and_unavailable():
    with patch.object(platform.sys, "platform", "darwin"), patch.object(platform.os, "kill") as kill:
        assert platform.process_exists(123) is True
        kill.assert_called_once_with(123, 0)
        kill.side_effect = ProcessLookupError()
        assert platform.process_exists(123) is False
        kill.side_effect = PermissionError()
        assert platform.process_exists(123) is None
        kill.reset_mock()
        for invalid in (None, "123", -1, 0, True):
            assert platform.process_exists(invalid) is False
        kill.assert_not_called()


def test_windows_process_query_closes_handles_and_never_sends_a_signal():
    kernel = SimpleNamespace(
        OpenProcess=MagicMock(return_value=42),
        GetExitCodeProcess=MagicMock(),
        CloseHandle=MagicMock(),
    )

    def exit_code(handle, result):
        assert handle == 42
        result._obj.value = 259
        return True

    kernel.GetExitCodeProcess.side_effect = exit_code
    with patch.object(platform.sys, "platform", "win32"), patch.object(
        ctypes, "WinDLL", return_value=kernel, create=True
    ), patch.object(ctypes, "get_last_error", return_value=87, create=True), patch.object(
        platform.os, "kill"
    ) as kill:
        assert platform.process_exists(123) is True
        kernel.CloseHandle.assert_called_once_with(42)
        kernel.GetExitCodeProcess.side_effect = None
        kernel.GetExitCodeProcess.return_value = False
        assert platform.process_exists(123) is None
        assert kernel.CloseHandle.call_count == 2
        kernel.OpenProcess.return_value = None
        assert platform.process_exists(123) is False
        kill.assert_not_called()


def test_linux_identity_is_optional_and_recycled_pids_are_rejected():
    stat = "123 (a process with spaces) " + " ".join(["S"] + ["0"] * 18 + ["456"])
    with patch.object(platform.sys, "platform", "linux"), patch.object(
        platform, "process_exists", return_value=True
    ), patch.object(Path, "read_text", return_value=stat) as read:
        assert platform.process_matches(123, 456) is True
        assert platform.process_matches(123, 457) is False
        assert platform.process_matches(123, None) is None
        read.return_value = stat.replace(") S", ") Z")
        assert platform.process_matches(123, 456) is False
        read.side_effect = PermissionError()
        assert platform.process_matches(123, 456) is None


def test_non_linux_identity_does_not_read_process_files():
    with patch.object(platform.sys, "platform", "darwin"), patch.object(
        platform, "process_exists", return_value=True
    ) as exists, patch.object(Path, "read_text") as read:
        assert platform.process_matches(123, 456) is None
        exists.return_value = False
        assert platform.process_matches(123, 456) is False
        read.assert_not_called()


def test_unix_memory_uses_standard_system_configuration():
    values = {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 2097152, "SC_AVPHYS_PAGES": 524288}
    with patch.object(platform.sys, "platform", "linux"), patch.object(
        platform.os, "sysconf", side_effect=values.__getitem__, create=True
    ), patch.object(Path, "read_text") as read:
        memory = platform.host_memory()
        assert memory["total_mb"] == 8192
        assert memory["available_mb"] == 2048
        assert memory["total_known"] and memory["available_known"]
        read.assert_not_called()


def test_macos_memory_reads_real_page_counts_instead_of_assuming_half():
    replies = [
        SimpleNamespace(returncode=0, stdout=str(8 * 1024**3)),
        SimpleNamespace(
            returncode=0,
            stdout="Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
            "Pages free: 65536.\nPages inactive: 32768.\nPages speculative: 32768.\n",
        ),
    ]
    with patch.object(platform.sys, "platform", "darwin"), patch.object(
        platform.os, "sysconf", side_effect=ValueError(), create=True
    ), patch.object(platform.subprocess, "run", side_effect=replies) as run:
        memory = platform.host_memory()
        assert memory["total_mb"] == 8192
        assert memory["available_mb"] == 2048
        assert all(call.kwargs["timeout"] == 1 for call in run.call_args_list)


def test_windows_memory_uses_the_native_measurement():
    def fill(result):
        status = result._obj
        assert status.length == 64
        status.total = 16 * 1024**3
        status.available = 3 * 1024**3
        return True

    kernel = SimpleNamespace(GlobalMemoryStatusEx=MagicMock(side_effect=fill))
    with patch.object(platform.sys, "platform", "win32"), patch.object(
        ctypes, "WinDLL", return_value=kernel, create=True
    ):
        assert platform.host_memory()["total_mb"] == 16384
        assert platform.host_memory()["available_mb"] == 3072


def test_failed_memory_probes_stay_unknown_in_the_model_api():
    with patch.object(platform.sys, "platform", "linux"), patch.object(
        platform.os, "sysconf", side_effect=OSError(), create=True
    ), patch.object(local_models, "is_mobile", return_value=False):
        memory = local_models.get_host_memory()
        assert memory["total_mb"] == memory["available_mb"] == 0
        assert not memory["total_known"] and not memory["available_known"]


def test_network_probe_closes_its_socket_when_offline():
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.connect.side_effect = OSError("no route")
    with patch.object(platform.socket, "getaddrinfo", side_effect=OSError()), patch.object(
        platform.socket, "socket", return_value=probe
    ):
        assert platform.lan_addresses() == []
        probe.__exit__.assert_called_once()


def test_network_addresses_are_deduplicated_and_loopback_is_excluded():
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.getsockname.return_value = ("192.168.1.4", 123)
    addresses = [(None, None, None, None, (address, 0)) for address in (
        "127.0.0.1", "0.0.0.0", "192.168.1.4", "10.0.0.2"
    )]
    with patch.object(platform.socket, "getaddrinfo", return_value=addresses), patch.object(
        platform.socket, "socket", return_value=probe
    ):
        assert platform.lan_addresses() == ["10.0.0.2", "192.168.1.4"]


def test_console_close_falls_back_when_process_groups_are_unavailable():
    console = Console.__new__(Console)
    console.finished = False
    console.error = ""
    console.process = MagicMock()
    console.process.poll.return_value = None
    with patch.object(os, "name", "posix"), patch.object(os, "killpg", side_effect=OSError(), create=True):
        console.close()
    console.process.terminate.assert_called_once()
    console.process.wait.assert_called_once_with(timeout=1)
    assert console.finished


def test_console_close_forces_stubborn_children_with_bounded_waits():
    console = Console.__new__(Console)
    console.finished = False
    console.error = ""
    console.process = MagicMock()
    console.process.poll.return_value = None
    console.process.wait.side_effect = subprocess.TimeoutExpired("hermes", 1)
    with patch.object(os, "name", "posix"), patch.object(os, "killpg", create=True) as group:
        console.close()
    assert group.call_count == 2
    assert console.process.wait.call_count == 2
    assert all(call.kwargs == {"timeout": 1} for call in console.process.wait.call_args_list)
    assert console.finished and "did not exit" in console.error
    console.finished = False
    with patch.object(os, "name", "nt"), patch.object(os, "killpg", create=True) as group:
        console.close()
        group.assert_not_called()
    console.process.terminate.assert_called_once_with(force=True)
