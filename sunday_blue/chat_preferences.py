"""Appearance settings: a fixed-size UI font and per-role chat typography."""
from pathlib import Path
import hashlib
import shutil
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import (QWidget,QFormLayout,QSpinBox,QComboBox,QCheckBox,QLineEdit,
    QDoubleSpinBox,QPushButton,QFileDialog,QMessageBox,QLabel,QVBoxLayout,QFrame,QHBoxLayout)
from .chat_presentation import options,validate,font_options
from .design_system import UI_FONTS,CHAT_FONTS,ROLE_FONT_DEFAULTS
from .roles import list_roles
from .numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox

def _card(title, description=''):
    frame=QFrame();frame.setObjectName('card');layout=QVBoxLayout(frame);layout.setContentsMargins(16,14,16,16);layout.setSpacing(10)
    heading=QLabel(title);heading.setObjectName('cardTitle');layout.addWidget(heading)
    if description:
        note=QLabel(description);note.setObjectName('muted');note.setWordWrap(True);layout.addWidget(note)
    return frame,layout

def _font_combo(choices):
    combo=QComboBox()
    available=set(QFontDatabase.families())
    for family,label in choices:
        if family in available:combo.addItem(label,family)
    return combo

class ChatPreferences(QWidget):
    def __init__(self,root,value,ui_value=None,role='rui'):
        super().__init__();self.root=Path(root);self.current=options(value);self.ui_current=dict(ui_value or {})
        self.role_fonts={k:dict(v) for k,v in self.current.get('role_fonts',{}).items()}
        self.current_role=role
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(12)

        ui_card,ui_layout=_card('界面字体','用于导航、按钮、设置和状态文字。字号由设计系统固定，避免模块间比例失控。')
        self.ui_family=_font_combo(UI_FONTS);self._select(self.ui_family,self.ui_current.get('font_family','Noto Sans SC'))
        ui_form=QFormLayout();ui_form.addRow('字体',self.ui_family);ui_layout.addLayout(ui_form);outer.addWidget(ui_card)

        font_card,font_layout=_card('角色气泡字体','每个角色保存自己的字体。下列字体均支持中文；也可以为当前角色导入字体文件。')
        role_row=QHBoxLayout();role_row.addWidget(QLabel('角色'))
        self.role=QComboBox()
        for rid,name,desc,_ in list_roles(root):self.role.addItem(f'{name} · {desc}',rid)
        self.role.setCurrentIndex(max(0,self.role.findData(role)));role_row.addWidget(self.role,1);font_layout.addLayout(role_row)
        form=QFormLayout()
        self.family=_font_combo(CHAT_FONTS)
        self.size=QSpinBox();self.size.setRange(9,30)
        self.weight=QComboBox()
        for name,n in [('正常',400),('适中',500),('加粗',600)]:self.weight.addItem(name,n)
        self.font_note=QLabel();self.font_note.setObjectName('muted');self.font_note.setWordWrap(True)
        upload=QPushButton('为当前角色导入字体文件');upload.clicked.connect(self.import_font)
        reset=QPushButton('恢复该角色推荐字体');reset.clicked.connect(self.reset_role_font)
        actions=QHBoxLayout();actions.addWidget(upload);actions.addWidget(reset)
        form.addRow('气泡字体',self.family);form.addRow('字号（pt）',self.size);form.addRow('字重',self.weight)
        font_layout.addLayout(form);font_layout.addLayout(actions);font_layout.addWidget(self.font_note);outer.addWidget(font_card)

        segment_card,segment_layout=_card('短回复分段','短于阈值的回复按标点逐段出现；长回复保持为一个连续气泡。')
        seg=QFormLayout()
        self.enabled=QCheckBox('启用逐段显示');self.enabled.setChecked(self.current['segmented'])
        self.threshold=QSpinBox();self.threshold.setRange(1,10000);self.threshold.setValue(self.current['threshold'])
        self.pattern=QLineEdit(self.current['pattern'])
        self.interval=QComboBox();self.interval.addItem('随机间隔','random');self.interval.addItem('按字数计算','log');self.interval.setCurrentIndex(max(0,self.interval.findData(self.current['interval'])))
        self.minimum=QDoubleSpinBox();self.minimum.setRange(0,60);self.minimum.setValue(self.current['random_min']);self.minimum.setSuffix(' 秒')
        self.maximum=QDoubleSpinBox();self.maximum.setRange(0,60);self.maximum.setValue(self.current['random_max']);self.maximum.setSuffix(' 秒')
        self.base=QDoubleSpinBox();self.base.setRange(1.01,1000);self.base.setValue(self.current['log_base'])
        for title,w in [('',self.enabled),('分段阈值',self.threshold),('分段正则',self.pattern),('间隔方式',self.interval),('最短间隔',self.minimum),('最长间隔',self.maximum),('log 底数',self.base)]:seg.addRow(title,w)
        segment_layout.addLayout(seg);outer.addWidget(segment_card)
        self.role.currentIndexChanged.connect(self._switch_role);self.family.currentIndexChanged.connect(self._system_font_changed)
        self._load_role(role)

    @staticmethod
    def _select(combo,value):
        i=combo.findData(value)
        if i>=0:combo.setCurrentIndex(i)

    def _role_value(self,role):
        value=dict(ROLE_FONT_DEFAULTS.get(role,ROLE_FONT_DEFAULTS['rui']));value['font_file']=''
        value.update(self.role_fonts.get(role,{}));return value

    def _store_role(self):
        if not self.current_role:return
        old=self._role_value(self.current_role)
        self.role_fonts[self.current_role]={'font_family':self.family.currentData() or old['font_family'],
            'font_file':old.get('font_file',''),'font_size':self.size.value(),'font_weight':self.weight.currentData()}

    def _load_role(self,role):
        self.current_role=role;v=self._role_value(role)
        self.family.blockSignals(True)
        if self.family.findData(v['font_family'])<0:self.family.addItem(v['font_family']+'（已导入）',v['font_family'])
        self._select(self.family,v['font_family']);self.size.setValue(v['font_size'])
        self.family.blockSignals(False)
        self.weight.setCurrentIndex(max(0,self.weight.findData(v['font_weight'])))
        self.font_note.setText(v.get('font_file') or '使用精选系统字体')

    def _switch_role(self):
        self._store_role();self._load_role(self.role.currentData())

    def _system_font_changed(self):
        if not self.current_role:return
        self.role_fonts.setdefault(self.current_role,self._role_value(self.current_role))['font_file']=''
        self.font_note.setText('使用精选系统字体')

    def reset_role_font(self):
        self.role_fonts[self.current_role]=dict(ROLE_FONT_DEFAULTS.get(self.current_role, ROLE_FONT_DEFAULTS['rui']),font_file='')
        self._load_role(self.current_role)

    def import_font(self):
        path,_=QFileDialog.getOpenFileName(self,'为当前角色导入字体',filter='字体 (*.ttf *.otf *.ttc)')
        if not path:return
        try:
            p=Path(path)
            if p.stat().st_size>50*1024*1024:raise ValueError('字体文件最大 50 MiB。')
            fid=QFontDatabase.addApplicationFont(str(p));families=QFontDatabase.applicationFontFamilies(fid) if fid>=0 else []
            if not families:raise ValueError('Qt 无法加载该字体，请选择有效字体文件。')
            dest=self.root/'assets'/'fonts'/(hashlib.sha256(p.read_bytes()).hexdigest()[:20]+p.suffix.lower())
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copy2(p,dest)
            family=families[0]
            if self.family.findData(family)<0:self.family.addItem(family+'（已导入）',family)
            self._select(self.family,family)
            self.role_fonts.setdefault(self.current_role,self._role_value(self.current_role))['font_file']=dest.relative_to(self.root).as_posix()
            self.font_note.setText(self.role_fonts[self.current_role]['font_file'])
        except Exception as exc:QMessageBox.warning(self,'字体导入失败',str(exc))

    def ui_value(self):
        return {'font_family':self.ui_family.currentData() or 'Noto Sans SC'}

    def value(self):
        self._store_role()
        active=self.role_fonts[self.current_role]
        return validate(dict(self.current,role_fonts=self.role_fonts,
            font_family=active['font_family'],font_file=active.get('font_file',''),font_size=active['font_size'],font_weight=active['font_weight'],
            segmented=self.enabled.isChecked(),threshold=self.threshold.value(),pattern=self.pattern.text(),interval=self.interval.currentData(),
            random_min=self.minimum.value(),random_max=self.maximum.value(),log_base=self.base.value()))
