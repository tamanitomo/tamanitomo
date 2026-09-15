"""Profile-scoped native Hermes setup consoles, with no shell command endpoint.

Output lives only in memory. This provides OAuth and less common Hermes settings
without copying their provider-specific flows into the companion app.
"""
from __future__ import annotations
import codecs
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid

COMMANDS={'setup':['setup'],'models':['model'],'tools':['tools'],
          'messaging':['gateway','setup'],'config':['config'],
          'chat':['chat'],'update':['update'],'doctor':['doctor']}

class Console:
    def __init__(self, runtime, home, action):
        if action not in COMMANDS: raise ValueError('Unknown Hermes setup console')
        import pyte
        self.id=uuid.uuid4().hex
        self.scope=(str(runtime.root),str(home))
        self.action=action
        self.lock=threading.Lock()
        self.screen=pyte.Screen(110,32)
        self.screen.write_process_input=lambda data:self.write(data)
        self.stream=pyte.Stream(self.screen)
        self.finished=False;self.error='';self.last_access=time.monotonic()
        env=runtime.env(home);env.update(TERM='xterm-256color',COLUMNS='110',LINES='32')
        argv=runtime.command()+COMMANDS[action]
        if os.name=='nt':
            from winpty import PtyProcess
            self.process=PtyProcess.spawn(argv,cwd=str(home),env=env,dimensions=(32,110))
        else:
            import pty,fcntl,termios,struct
            self.master,slave=pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',32,110,0,0))
            try:
                self.process=subprocess.Popen(argv,cwd=str(home),env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
            finally:os.close(slave)
        threading.Thread(target=self._read,daemon=True,name='hermes-console').start()
        threading.Thread(target=self._expiry,daemon=True,name='hermes-console-expiry').start()

    def _expiry(self):
        while not self.finished:
            time.sleep(10)
            if time.monotonic()-self.last_access>1800:
                self.close();return

    def _read(self):
        decoder=codecs.getincrementaldecoder('utf-8')('replace')
        try:
            while True:
                data=self.process.read(16384) if os.name=='nt' else decoder.decode(os.read(self.master,16384))
                if not data:break
                with self.lock:self.stream.feed(data)
        except (OSError,EOFError):pass
        except Exception as exc:self.error=str(exc)
        finally:
            self.finished=True
            if os.name!='nt':
                try:os.close(self.master)
                except OSError:pass
                self.process.wait()

    def read(self):
        self.last_access=time.monotonic()
        with self.lock:
            return {'id':self.id,'action':self.action,'screen':'\n'.join(self.screen.display),
                    'finished':self.finished,'error':self.error,
                    'cursor':{'x':self.screen.cursor.x,'y':self.screen.cursor.y}}

    def write(self,data):
        self.last_access=time.monotonic()
        if self.finished:raise ValueError('This Hermes console has finished')
        if not isinstance(data,str) or len(data)>12000:raise ValueError('Invalid console input')
        if os.name=='nt':self.process.write(data)
        else:os.write(self.master,data.encode('utf-8'))

    def close(self):
        if self.finished:return
        if os.name=='nt':self.process.terminate(force=True)
        else:
            try:os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        self.finished=True

class Consoles:
    def __init__(self):self.rows={};self.lock=threading.Lock()
    def open(self,rt,home,action):
        home.mkdir(parents=True,exist_ok=True)
        with self.lock:
            for row in self.rows.values():
                if row.scope[0]==str(rt.root) and not row.finished:
                    if row.scope==(str(rt.root),str(home)):return row
                    raise ValueError('Close the other setup console for this installation first')
            # Completed consoles contain private output; do not retain them.
            self.rows={k:v for k,v in self.rows.items() if not v.finished}
            row=Console(rt,home,action);self.rows[row.id]=row;return row
    def get(self,ident,rt,home):
        with self.lock:row=self.rows.get(ident)
        if not row or row.scope!=(str(rt.root),str(home)):raise ValueError('Console not found for this profile')
        return row
