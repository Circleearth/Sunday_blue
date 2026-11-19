"""Opt-in LAN receiver for screen-break events. No app names or screen contents."""
import hmac
import ipaddress
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .notices import notify

class PhoneLink:
    def __init__(self,db):
        self.db=db
        self.server=None

    def start(self, bind_ip=None, port=38192):
        if self.server:return self.address
        ip=bind_ip
        if ip is None:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
                probe.connect(('192.0.2.1',9))
                ip=probe.getsockname()[0]
        if not ipaddress.ip_address(ip).is_private:raise ValueError('请先接入本地 Wi-Fi')
        token=self.db.get('phone_token','') or secrets.token_urlsafe(24)
        self.db.set('phone_token',token)
        db=self.db
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.path!='/break' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    self.send_error(403);return
                try:
                    when=int(self.headers.get('X-Sunday-Time','0'))
                    minutes=int(self.headers.get('X-Sunday-Minutes','0'))
                    if abs(time.time()-when)>300 or not 5<=minutes<=120:raise ValueError()
                except ValueError:self.send_error(400);return
                with db.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    recent=c.execute("SELECT 1 FROM reminder_occurrences WHERE id LIKE 'phone-break:%' AND julianday(due)>julianday('now','-5 minutes')").fetchone()
                    if not recent:notify(c,'phone-break:'+str(when),f'手机已连续亮屏 {minutes} 分钟，可以放下手机换个姿势。')
                self.send_response(204);self.end_headers()
        self.server=ThreadingHTTPServer((ip,port),Handler)
        self.address=f'http://{ip}:{self.server.server_port}'
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        return self.address

    def stop(self):
        if self.server:self.server.shutdown();self.server.server_close();self.server=None
