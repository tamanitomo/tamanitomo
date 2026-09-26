"""Portable filesystem and command primitives. No agent-specific state."""
from __future__ import annotations
import contextlib
import os
import pathlib
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time

WINDOWS_RESERVED = {'con','prn','aux','nul','root','default', *('com'+str(i) for i in range(1,10)), *('lpt'+str(i) for i in range(1,10))}

def profile_name(value):
    name=value.lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,47}',name) or name in WINDOWS_RESERVED:
        raise ValueError('Profile names must be 1–48 letters, digits, hyphens or underscores, start with a letter/digit, and not be reserved.')
    return name

def profile_path(root,name):
    base=pathlib.Path(root).resolve()/'profiles'
    target=base/profile_name(name)
    if base.is_symlink() or target.is_symlink() or target.resolve().parent!=base:
        raise ValueError('Refusing a profile path through a symlink or outside profiles.')
    return target

def command(argv):
    """Quote an argv for the host shell used by Hermes hook commands."""
    return subprocess.list2cmdline([str(x) for x in argv]) if os.name=='nt' else shlex.join([str(x) for x in argv])

def kit_python():
    """The interpreter that has the kit's dependencies: the app's own venv when it has one.

    Commands written into job prompts and hooks run later, from Hermes, long after
    whoever rendered them has exited. Rendering them with sys.executable meant a
    repair started from the `companion` launcher -- system python3 -- wrote the
    system interpreter into every prompt, and image jobs then failed for hours
    with "No module named 'PIL'".
    """
    root=pathlib.Path(__file__).resolve().parents[2]
    for candidate in (root/'.venv'/'bin'/'python',root/'.venv'/'Scripts'/'python.exe'):
        if candidate.is_file():return str(candidate)
    return sys.executable

def python_command(script,*args):
    return command([kit_python(),script,*args])

def hermes_command(*args):
    # JSON argv permits test doubles and a Python module command without shell evaluation.
    import json
    override=os.environ.get('COMPANION_HERMES_COMMAND')
    if not override:
        home=default_home()
        root=home.parent.parent if home.parent.name=='profiles' else home
        config=root/'.companion-runtime.json'
        if config.is_file():
            override=json.dumps(json.loads(config.read_text(encoding='utf-8'))['command'])
    prefix=json.loads(override) if override else ['hermes']
    if not isinstance(prefix,list) or not prefix or not all(isinstance(x,str) and x for x in prefix):
        raise ValueError('COMPANION_HERMES_COMMAND must be a nonempty JSON array of arguments')
    return prefix+list(args)

@contextlib.contextmanager
def file_lock(path,timeout=30):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        if os.name=='nt':
            import msvcrt
            handle.seek(0,2)
            if not handle.tell():handle.write(b'\0');handle.flush()
            deadline=time.monotonic()+timeout
            while True:
                handle.seek(0)
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    if time.monotonic()>=deadline:raise TimeoutError(f'Lock busy: {path}')
                    time.sleep(.05)
            try:yield
            finally:
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            deadline=time.monotonic()+timeout
            while True:
                try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise TimeoutError(f'Lock busy: {path}')
                    time.sleep(.05)
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)

def atomic_write(path,text):
    """Write a file so that a power cut leaves either the old one or the new one.

    The contents were being fsynced and the rename was not, which is only half of
    it: `os.replace` is atomic with respect to a reader, but the directory entry
    it creates can still be lost on an unclean shutdown, taking the file with it.
    For a memory file or a day's plan that is the difference between the old
    version and no version. Syncing the directory afterwards is what makes the
    rename durable, and it is cheap.
    """
    path=pathlib.Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        if path.exists():os.chmod(tmp,path.stat().st_mode & 0o777)
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as out:
            out.write(text);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
        _sync_dir(path.parent)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def _sync_dir(folder):
    """Durability for the rename itself. Not every platform allows it; Windows
    has no directory file descriptor to sync, and a read-only mount will refuse.
    Neither is a reason to fail a write that has already landed."""
    try:
        fd=os.open(str(folder),os.O_RDONLY)
    except (OSError,AttributeError):
        return False
    try:
        os.fsync(fd)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)

def default_home():
    """Match Hermes native Windows and POSIX data locations."""
    if os.environ.get('HERMES_HOME'):return pathlib.Path(os.environ['HERMES_HOME']).expanduser()
    if os.name=='nt':return pathlib.Path(os.environ.get('LOCALAPPDATA',str(pathlib.Path.home()/'AppData/Local')))/'hermes'
    return pathlib.Path.home()/'.hermes'

def venv_executable(checkout,name='python'):
    """The interpreter (or entry point) inside a checkout's virtualenv.

    Hermes's own checkout is made by whoever installed it, and `uv venv` -- now
    the ordinary way to make one -- writes `.venv`, not `venv`. Every bridge
    here looked only for `venv` and reported "Hermes Python is unavailable" on a
    perfectly working install, which sent people looking at their model settings
    for a problem that was a directory name. Kit-created venvs keep their own
    fixed layout and do not come through here.
    """
    leaf=(f'Scripts/{name}.exe' if os.name=='nt' else f'bin/{name}')
    checkout=pathlib.Path(checkout)
    for folder in ('venv','.venv'):
        candidate=checkout/folder/leaf
        if candidate.is_file():return candidate
    return checkout/'venv'/leaf

def terminal_command(argv):
    """Hermes terminal tool uses POSIX shells, including Git Bash on Windows."""
    parts=[str(x).replace('\\','/') if os.name=='nt' else str(x) for x in argv]
    return shlex.join(parts)

def terminal_python_command(script,*args):
    return terminal_command([kit_python(),script,*args])

def is_terminal(stream=None):
    """True only when stream is attached to an interactive terminal, never for NUL or pipes."""
    s=sys.stdin if stream is None else stream
    if not (s and hasattr(s,'isatty') and s.isatty()):return False
    if os.name=='nt':
        try:
            import msvcrt, ctypes
            handle=msvcrt.get_osfhandle(s.fileno())
            mode=ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
        except Exception:
            return False
    return True


def lan_addresses():
    """Discover IPv4 routes with portable socket APIs, including offline hosts."""
    addresses = set()
    try:
        addresses.update(
            row[4][0]
            for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    try:
        # Connecting a UDP socket asks the kernel for a route without sending data.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.2)
            probe.connect(("192.0.2.1", 9))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    return sorted(
        address
        for address in addresses
        if not address.startswith("127.") and address != "0.0.0.0"
    )


def _windows_process_exists(pid):
    """Query a Windows process handle without sending a signal to the process."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False if ctypes.get_last_error() == 87 else None
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def process_exists(pid):
    """Return live, absent, or unknown; a live PID alone never proves identity."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            # Windows os.kill(pid, 0) is not a harmless existence check.
            return _windows_process_exists(pid)
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (OSError, AttributeError, OverflowError):
        return None


def process_matches(pid, start_time):
    """Verify Hermes' Linux start ticks when available; otherwise report unknown.

    Existing gateway records use kernel start ticks, not a portable timestamp.
    A missing/restricted process filesystem must not label a live service dead,
    and checking only its PID would mistake a recycled PID for that service.
    """
    exists = process_exists(pid)
    if exists is False:
        return False
    if sys.platform.startswith("linux"):
        try:
            fields = (pathlib.Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
            if start_time is None:
                return None
            return fields[0] != "Z" and int(fields[19]) == start_time
        except (OSError, ValueError, IndexError):
            pass
    return None


def _positive_sysconf(name):
    try:
        value = int(os.sysconf(name))
        return value if value > 0 else 0
    except (AttributeError, OSError, ValueError):
        return 0


def _windows_memory():
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint32),
            ("load", ctypes.c_uint32),
            ("total", ctypes.c_uint64),
            ("available", ctypes.c_uint64),
            ("total_page_file", ctypes.c_uint64),
            ("available_page_file", ctypes.c_uint64),
            ("total_virtual", ctypes.c_uint64),
            ("available_virtual", ctypes.c_uint64),
            ("extended_virtual", ctypes.c_uint64),
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GlobalMemoryStatusEx.argtypes = (ctypes.POINTER(MemoryStatus),)
    kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0, 0
    return status.total, status.available


def host_memory():
    """Measured RAM in MiB; unavailable measurements stay zero, never invented.

    Unix sysconf reports conservatively available pages without a Linux process
    filesystem. macOS exposes free/reclaimable pages through its native vm_stat.
    """
    total = available = 0
    if sys.platform == "win32":
        try:
            total, available = _windows_memory()
        except (OSError, AttributeError, ValueError):
            pass
    else:
        page_size = _positive_sysconf("SC_PAGE_SIZE")
        total = page_size * _positive_sysconf("SC_PHYS_PAGES")
        available = page_size * _positive_sysconf("SC_AVPHYS_PAGES")
        if sys.platform == "darwin":
            try:
                if not total:
                    result = subprocess.run(
                        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=1
                    )
                    if result.returncode == 0:
                        total = max(0, int(result.stdout.strip()))
                result = subprocess.run(
                    ["vm_stat"], capture_output=True, text=True, timeout=1
                )
                if result.returncode == 0:
                    size = re.search(r"page size of (\d+) bytes", result.stdout)
                    if size:
                        pages = sum(
                            int(match.group(1))
                            for match in re.finditer(
                                r"^Pages (?:free|inactive|speculative):\s*(\d+)",
                                result.stdout,
                                re.MULTILINE,
                            )
                        )
                        available = pages * int(size.group(1))
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
    if total:
        available = min(available, total)
    return {
        "total_mb": total // (1024 * 1024),
        "available_mb": available // (1024 * 1024),
        "total_known": total > 0,
        "available_known": available > 0,
    }

if os.name=='nt':
    # Also works when scripts are invoked directly rather than via the launcher.
    for stream in (sys.stdin,sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    os.environ.setdefault('PYTHONUTF8','1')
    os.environ.setdefault('PYTHONIOENCODING','utf-8')
