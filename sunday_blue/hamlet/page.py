"""Session-scoped bridge. The Godot client receives game data only."""
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox

from .world import Village


class Bridge:
    def __init__(self, world, exchanged=lambda:None):
        token = self.token = secrets.token_hex(32)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass

            def do_POST(self):
                if self.path!='/village' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    self.send_error(403);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4096:raise ValueError('无效的请求长度')
                    payload=json.loads(self.rfile.read(size))
                    if not isinstance(payload,dict):raise ValueError('无效的请求')
                    args=[payload.get('action','view'),payload.get('arg',''),payload.get('id','')]
                    if not all(isinstance(v,str) for v in args):raise ValueError('无效参数')
                    result=world.transact(*args);status=200
                    if args[0]=='exchange':exchanged()
                except (ValueError,UnicodeError) as exc:
                    result={'error':str(exc)};status=400
                except Exception:
                    import logging
                    logging.exception('Hamlet transaction failed')
                    result={'error':'本地存档暂时不可用，请重试'};status=503
                body=json.dumps(result,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(body)));self.end_headers()
                self.wfile.write(body)

        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()


class GameSession(QObject):
    exchanged=Signal()
    def __init__(self,hub):
        super().__init__(hub)
        self.hub=hub
        self.exchanged.connect(self.refresh_wallet)
        self.process=self.bridge=None
        self.watch=QTimer(self)
        self.watch.setInterval(1000)
        self.watch.timeout.connect(self.check)
        hub.closed.connect(self.close)

    def refresh_wallet(self):
        self.hub.changed.emit("work")

    def launch(self,extra=()):
        if self.process and self.process.poll() is None:
            return False
        self.close()
        root=self.hub.root
        engine=Path(os.environ.get('SUNDAY_GODOT') or root/'runtime/godot/Godot.exe')
        project=root/'assets/hamlet/game'
        if not engine.is_file():raise ValueError('请将 Godot 4.6 Windows 引擎放在 runtime/godot/Godot.exe')
        world=Village(self.hub.db,catalog=project/'catalog.json')
        self.bridge=Bridge(world,self.exchanged.emit)
        env=dict(os.environ,SUNDAY_VALLEY_PORT=str(self.bridge.server.server_port),SUNDAY_VALLEY_TOKEN=self.bridge.token)
        try:
            self.process=subprocess.Popen([str(engine),'--path',str(project),'--single-window',*extra],env=env,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:
            self.close();raise
        self.watch.start()
        return True

    def check(self):
        if self.process and self.process.poll() is not None:
            failed=self.process.returncode!=0
            self.close()
            if failed:self.hub.failed.emit('雾铃谷窗口意外退出。已提交的操作保存在本机，可重新进入。')

    def close(self):
        self.watch.stop()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process=None
        if self.bridge:self.bridge.close();self.bridge=None


def open_village(hub,parent):
    if not hasattr(hub,'hamlet'):hub.hamlet=GameSession(hub)
    try:
        if not hub.hamlet.launch():QMessageBox.information(parent,'雾铃谷','谷地已在独立窗口中运行。')
    except (ValueError,OSError) as exc:QMessageBox.warning(parent,'无法进入雾铃谷',str(exc))
