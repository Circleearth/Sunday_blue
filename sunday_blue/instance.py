"""Per-installation, current-user activation channel; QLockFile remains authoritative."""
import hashlib
import os
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class Instance(QObject):
    activated = Signal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        key = str(root.resolve()).casefold() + os.environ.get('USERNAME', '')
        self.name = 'SundayBlue-' + hashlib.sha256(key.encode()).hexdigest()[:24]
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)

    def wake(self):
        for _ in range(6):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(400):
                socket.write(b'show\n');socket.waitForBytesWritten(400)
                socket.disconnectFromServer()
                return True
        return False

    def listen(self):
        # Only call after acquiring the installation lock.
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            raise RuntimeError('无法建立窗口唤醒通道：' + self.server.errorString())

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.activated.emit()
            socket.disconnectFromServer();socket.deleteLater()

    def close(self):
        self.server.close()
