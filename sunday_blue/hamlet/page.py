from pathlib import Path
import time
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QWidget
from .world import Village

class VillageWindow(QDialog):
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.setWindowTitle('雾铃谷')
        self.resize(800,570)
        self.world = Village(hub.db)
        box = QVBoxLayout(self)
        art = QLabel()
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scene_path = hub.root/'assets/hamlet/village.png'
        picture = QPixmap(str(scene_path)) if scene_path.is_file() else QPixmap()
        if not picture.isNull():
            art.setPixmap(picture.scaled(740,260,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            box.addWidget(art)
        self.stats = QLabel()
        box.addWidget(self.stats)
        tabs = QTabWidget()
        box.addWidget(tabs)
        self.fields = []
        for title, actions in [('农田', [('田地','field')]*3), ('铁匠铺',[('锻造 · 矿石 ×2','forge'),('试打木桩','dummy')]),
                               ('遗迹',[('进入下一层','dungeon')]),('魔物牧场',[('喂养苔灵 · 麦穗 ×1','feed')])]:
            page = QWidget()
            layout = QHBoxLayout(page)
            for index,(label,action) in enumerate(actions):
                btn = QPushButton(label)
                btn.clicked.connect(lambda checked=False,a=action,i=index:self.act(a,i))
                layout.addWidget(btn)
                if action=='field': self.fields.append(btn)
            tabs.addTab(page,title)
        self.inventory = QLabel()
        box.addWidget(self.inventory)
        self.message = QLabel('守谷人铃禾：「先去遗迹看看吧，第一层的小家伙很好相处。」')
        self.message.setWordWrap(True)
        box.addWidget(self.message)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def act(self, action, index):
        try: message = self.world.act(action,index)
        except ValueError as exc: message = str(exc)
        self.message.setText(message)
        self.refresh()

    def refresh(self):
        s = self.world.view()
        self.stats.setText(f"雾铃谷   Lv.{1+s['xp']//8}     可用货币 {s['balance']}     遗迹第 {s['floor']} 层")
        self.inventory.setText(f"背包   麦穗 {s['wheat']}    矿石 {s['ore']}    武器 +{s['weapon']}    圣遗物 {s['relic']}    苔灵 {s['enemies']}    羁绊 {s['bond']}")
        for i,ready in enumerate(s['plots']):
            remaining = max(0,int(ready-time.time()+.99))
            self.fields[i].setText(f'田地 {i+1}   '+('播种 · 1 积分' if not ready else f'{remaining} 秒' if remaining else '收获'))
