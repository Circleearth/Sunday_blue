"""Chat typography and timed segmentation settings, kept out of Settings orchestration."""
from pathlib import Path
import hashlib
import shutil
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import (QWidget,QFormLayout,QFontComboBox,QSpinBox,QComboBox,
    QCheckBox,QLineEdit,QDoubleSpinBox,QPushButton,QFileDialog,QMessageBox,QLabel)
from .chat_presentation import options,validate

class ChatPreferences(QWidget):
    def __init__(self,root,value):
        super().__init__();self.root=Path(root);self.current=options(value)
        form=QFormLayout(self)
        self.family=QFontComboBox();self.family.setCurrentFont(QFont(self.current['font_family']))
        self.family.currentFontChanged.connect(self.use_system_font)
        self.size=QSpinBox();self.size.setRange(9,30);self.size.setValue(self.current['font_size'])
        self.weight=QComboBox()
        for name,n in [('正常',400),('适中',500),('加粗',600)]:self.weight.addItem(name,n)
        self.weight.setCurrentIndex(max(0,self.weight.findData(self.current['font_weight'])))
        self.font_note=QLabel(self.current['font_file'] or '使用系统字体（可选楷体）');self.font_note.setWordWrap(True)
        upload=QPushButton('导入字体文件 .ttf / .otf / .ttc');upload.clicked.connect(self.import_font)
        self.enabled=QCheckBox('启用短回复分段（完成回复后逐段显示）');self.enabled.setChecked(self.current['segmented'])
        self.threshold=QSpinBox();self.threshold.setRange(1,10000);self.threshold.setValue(self.current['threshold'])
        self.pattern=QLineEdit(self.current['pattern'])
        self.interval=QComboBox();self.interval.addItems(['random','log']);self.interval.setCurrentText(self.current['interval'])
        self.minimum=QDoubleSpinBox();self.minimum.setRange(0,60);self.minimum.setValue(self.current['random_min'])
        self.maximum=QDoubleSpinBox();self.maximum.setRange(0,60);self.maximum.setValue(self.current['random_max'])
        self.base=QDoubleSpinBox();self.base.setRange(1.01,1000);self.base.setValue(self.current['log_base'])
        for title,w in [('聊天字体',self.family),('字号（pt）',self.size),('字重',self.weight),('',upload),('',self.font_note),('',self.enabled),('分段字数阈值（小于才分）',self.threshold),('分段正则',self.pattern),('间隔方式',self.interval),('随机最小秒数',self.minimum),('随机最大秒数',self.maximum),('log 底数',self.base)]:form.addRow(title,w)

    def use_system_font(self,font):
        self.current['font_file']=''
        self.font_note.setText('使用系统字体')

    def import_font(self):
        path,_=QFileDialog.getOpenFileName(self,'导入字体',filter='字体 (*.ttf *.otf *.ttc)')
        if not path:return
        try:
            p=Path(path)
            if p.stat().st_size>50*1024*1024:raise ValueError('字体文件最大 50 MiB。')
            fid=QFontDatabase.addApplicationFont(str(p))
            families=QFontDatabase.applicationFontFamilies(fid) if fid>=0 else []
            if not families:raise ValueError('Qt 无法加载该字体，请选择有效字体文件。')
            dest=self.root/'assets'/'fonts'/(hashlib.sha256(p.read_bytes()).hexdigest()[:20]+p.suffix.lower())
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copy2(p,dest)
            self.family.setCurrentFont(QFont(families[0]))
            self.current['font_file']=dest.relative_to(self.root).as_posix()
            self.font_note.setText(self.current['font_file'])
        except Exception as exc:QMessageBox.warning(self,'字体导入失败',str(exc))

    def value(self):
        return validate(dict(self.current,font_family=self.family.currentFont().family(),font_size=self.size.value(),font_weight=self.weight.currentData(),
            segmented=self.enabled.isChecked(),threshold=self.threshold.value(),pattern=self.pattern.text(),interval=self.interval.currentText(),
            random_min=self.minimum.value(),random_max=self.maximum.value(),log_base=self.base.value()))
