"""Reusable, local artwork slots. Metadata and prompts are editable external assets."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPixmap,QPainter,QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QDialog,QPlainTextEdit,QApplication,QTabWidget

DEFAULTS={
 'recovery_body':dict(name='恢复站 · 人体底图',path='assets/ui/recovery_body.png',size='880 × 660',ratio='4:3',transparent=True,placement='正面居左、背面居右；保持四肢自然分开。动态肌群由程序绘制，底图不可自带红绿状态。',positive='Clean Japanese visual novel interface illustration, two neutral adult anatomical mannequin silhouettes, front view on the left and back view on the right, full body, symmetrical relaxed standing pose, arms slightly away from torso, pale cool grey contours, simplified smooth forms, flat orthographic view, even soft studio light, transparent background, generous margins, no muscle colors, no labels, crisp high resolution edges.',negative='text, letters, labels, watermark, logo, colored muscle groups, red heatmap, green heatmap, medical wounds, gore, exaggerated muscles, sexualized anatomy, extra limbs, extra fingers, missing limbs, distorted proportions, busy background, perspective distortion, dramatic shadows, blur'),
 'recovery_scene':dict(name='恢复站 · 休息角',path='assets/ui/recovery_scene.png',size='1200 × 360',ratio='10:3',transparent=False,placement='植物与靠枕在右侧；左侧约65%保持低细节留白，文字另由界面显示。',positive='Refined Japanese visual novel background, a quiet sunlit resting corner, ivory wall, pale sage cushions and a small potted plant on the far right, soft morning light, warm white and muted mint palette, wide horizontal composition, left sixty five percent clean low detail negative space for interface content, delicate cel shading, calm domestic atmosphere, high quality illustration.',negative='people, face, text, logo, watermark, clutter, multiple focal points, saturated neon colors, harsh contrast, deep black shadows, detailed patterns in left area, messy perspective, blur, low resolution')
}

DEFAULTS['settlement_host']=dict(name='结算看板娘',path='assets/ui/settlement_host.png',size='600 × 900',ratio='2:3',transparent=True,fit='contain',placement='成年陪伴角色居中，完整半身或立绘；四周留白，文字由界面显示。',positive='Refined Japanese visual novel character illustration, an adult woman companion with warm composed expression, elegant casual cream cardigan and muted blue skirt, relaxed welcoming pose, hands naturally visible, soft even lighting, clean cel shading, centered three quarter body composition, generous empty margins, transparent background, crisp high resolution silhouette.',negative='child, text, watermark, logo, extra fingers, missing fingers, distorted hands, extra limbs, malformed anatomy, exaggerated proportions, cluttered background, harsh shadows, blurry edges')

def asset_spec(root,key):
    spec=dict(DEFAULTS[key])
    path=Path(root)/'assets/ui/resources.json'
    if path.is_file():
        try:spec.update(json.loads(path.read_text(encoding='utf-8')).get(key,{}))
        except (ValueError,OSError):pass
    candidate=(Path(root)/spec['path']).resolve()
    # Metadata cannot read arbitrary paths outside this installation's assets.
    if not candidate.is_relative_to((Path(root)/'assets').resolve()):candidate=Path(root)/DEFAULTS[key]['path']
    spec['file']=candidate
    return spec

def asset_details(parent,root,key):
    spec=asset_spec(root,key);dialog=QDialog(parent);dialog.setWindowTitle(spec['name']+' · 素材说明');dialog.resize(640,540)
    layout=QVBoxLayout(dialog);info=QLabel(f"{spec['size']} · {spec['ratio']} · {'透明 PNG' if spec['transparent'] else '不透明背景'}\n{spec['placement']}\n保存到：{spec['file']}\n替换后重新打开页面或重启应用；不需改代码。")
    info.setWordWrap(True);info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(info)
    tabs=QTabWidget();layout.addWidget(tabs)
    for label,key in [('Positive Prompt','positive'),('Negative Prompt','negative')]:
        page=QWidget();box=QVBoxLayout(page);text=QPlainTextEdit(spec[key]);text.setReadOnly(True);box.addWidget(text)
        copy=QPushButton('复制完整 '+label);copy.clicked.connect(lambda checked=False,t=spec[key]:QApplication.clipboard().setText(t));box.addWidget(copy);tabs.addTab(page,label)
    close=QPushButton('关闭');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec()

from .image_layouts import EditableImage
class ArtworkSlot(EditableImage):
    def __init__(self,root,key,parent=None):
        spec=asset_spec(root,key);a,b=map(float,spec['ratio'].split(':'));super().__init__(root,key,spec['file'],'选择图片 / 调整',a/b,parent);self.spec=spec
        button=QPushButton(spec['name']+' · 素材说明');button.clicked.connect(lambda:asset_details(self,root,key));self.layout().addWidget(button,0,Qt.AlignmentFlag.AlignRight)
