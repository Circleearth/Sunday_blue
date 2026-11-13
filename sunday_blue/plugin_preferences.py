"""Schema-generated plugin forms (AstrBot-style basic field vocabulary)."""
import json
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QDialogButtonBox,QCheckBox,
    QSpinBox,QDoubleSpinBox,QLineEdit,QPlainTextEdit,QComboBox,QLabel,QScrollArea,QWidget,QMessageBox,
    QStyledItemDelegate,QStyleOptionViewItem)
from .numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox

class PluginRowDelegate(QStyledItemDelegate):
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator


class PluginPreferences(QDialog):
    def __init__(self,meta,values,parent=None,extra_widget=None):
        super().__init__(parent);self.setWindowTitle(meta['name']+' · 参数设置');self.resize(560,430)
        self.values=dict(values);self.fields={}
        layout=QVBoxLayout(self)
        # Optional control panel the plugin supplies (PLUGIN_SPEC 3b): shown ABOVE
        # the parameter form so restart/stop-style buttons are immediately
        # visible, not buried below a long form.
        if extra_widget is not None:
            cap = QLabel(getattr(extra_widget, '_settings_extra_title', '插件运行状态 · 重启/停止'))
            cap.setObjectName('section')
            layout.addWidget(cap)
            layout.addWidget(extra_widget)
            sep = QLabel('参数');sep.setObjectName('muted')
            layout.addWidget(sep)
        scroll=QScrollArea();scroll.setWidgetResizable(True);layout.addWidget(scroll)
        content=QWidget();form=QFormLayout(content);scroll.setWidget(content)
        for key,spec in meta['schema'].items():
            if spec.get('invisible'):continue
            value=values.get(key,spec.get('default'));kind=spec.get('type')
            if spec.get('options'):
                w=QComboBox()
                for index,option in enumerate(spec['options']):
                    labels=spec.get('labels',[]);w.addItem(str(labels[index] if index<len(labels) else option),option)
                w.setCurrentIndex(max(0,w.findData(value)))
            elif kind=='bool':w=QCheckBox();w.setChecked(bool(value))
            elif kind in ('int','float'):
                w=QSpinBox() if kind=='int' else QDoubleSpinBox()
                bounds=spec.get('slider',{});w.setRange(bounds.get('min',-1000000),bounds.get('max',1000000));w.setValue(value or 0)
            elif kind in ('text','object','list','dict'):
                w=QPlainTextEdit(value or '' if kind=='text' else json.dumps(value,ensure_ascii=False,indent=2))
            elif kind=='string':
                w=QLineEdit(value or '')
                if spec.get('secret'):w.setEchoMode(QLineEdit.EchoMode.Password)
            else:
                form.addRow(spec.get('description',key),QLabel('不支持此配置类型：'+str(kind)));continue
            w.setToolTip(spec.get('hint',''));form.addRow(spec.get('description',key),w);self.fields[key]=(w,kind)
        if not self.fields:form.addRow(QLabel('此插件没有可配置参数。'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('应用参数')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def save(self):
        try:
            for key,(w,kind) in self.fields.items():
                if isinstance(w,QComboBox):v=w.currentData()
                elif isinstance(w,QCheckBox):v=w.isChecked()
                elif isinstance(w,(QSpinBox,QDoubleSpinBox)):v=w.value()
                elif isinstance(w,QLineEdit):v=w.text()
                elif kind=='text':v=w.toPlainText()
                else:
                    v=json.loads(w.toPlainText())
                    if not isinstance(v,list if kind=='list' else dict):raise ValueError(key+' 的 JSON 类型不正确')
                self.values[key]=v
            self.accept()
        except ValueError as exc:QMessageBox.warning(self,'参数有误',str(exc))
