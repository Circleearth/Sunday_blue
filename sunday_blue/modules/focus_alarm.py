"""One-shot local alarms. Construct multimedia objects only when sound is requested."""
import math
import struct
import wave
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWidgets import QApplication
from .focus_preferences import sound_path


class FocusAlarm(QObject):
    problem = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.player = self.output = None
        self.fallback_used = False
        self.limit = QTimer(self)
        self.limit.setSingleShot(True)
        self.limit.timeout.connect(self.stop)

    def _default(self):
        path = self.root / 'data/sounds/focus/default-chime.wav'
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            samples = []
            rate = 22050
            for frequency in (659.25, 830.61, 987.77):
                for i in range(int(rate * .38)):
                    t = i / rate
                    envelope = min(1, t / .015) * math.exp(-7 * t)
                    samples.append(int(10000 * envelope * math.sin(2 * math.pi * frequency * t)))
            with wave.open(str(path), 'wb') as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
                output.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
        return path

    def play(self, phase, options):
        self.stop()
        if not options['sound_enabled'] or options['volume'] == 0: return
        self.fallback_used = False
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            if self.player is None:
                self.player = QMediaPlayer(self)
                self.output = QAudioOutput(self)
                self.player.setAudioOutput(self.output)
                self.player.errorOccurred.connect(self._failed)
            relative = options.get('sounds', {}).get(phase, '')
            path = sound_path(self.root, relative) if relative else self._default()
            if not path.is_file(): raise FileNotFoundError('提示音文件不存在')
            self.output.setVolume(options['volume'] / 100)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
            self.limit.start(30000)
        except Exception:
            self._failed()

    def _failed(self, *args):
        if self.fallback_used: return
        self.fallback_used = True
        self.stop()
        QApplication.beep()
        self.problem.emit('提示音无法播放，已尝试系统提示音；请重新选择音频或检查音频设备。')

    def stop(self):
        self.limit.stop()
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl())  # Release Windows file handles on stop/close.
