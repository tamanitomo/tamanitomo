"""Portable filesystem and command primitives. No agent-specific state."""
from __future__ import annotations
import contextlib
import os
import pathlib
import re
import shlex
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

def python_command(script,*args):
    return command([sys.executable,script,*args])

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

def terminal_command(argv):
    """Hermes terminal tool uses POSIX shells, including Git Bash on Windows."""
    parts=[str(x).replace('\\','/') if os.name=='nt' else str(x) for x in argv]
    return shlex.join(parts)

def terminal_python_command(script,*args):
    return terminal_command([sys.executable,script,*args])

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

if os.name=='nt':
    # Also works when scripts are invoked directly rather than via the launcher.
    for stream in (sys.stdin,sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    os.environ.setdefault('PYTHONUTF8','1')
    os.environ.setdefault('PYTHONIOENCODING','utf-8')

