"""Work, daily life and duty-slot views. Domain services own validation and all writes."""
from datetime import date
import json
from PySide6.QtCore import Qt,QDate,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QLineEdit,QPlainTextEdit,QComboBox,QCheckBox,QSpinBox,QDoubleSpinBox,QDateEdit,
    QFrame,QTreeWidget,QTreeWidgetItem,QListWidget,QListWidgetItem,QProgressBar,QTabWidget,
    QDialog,QDialogButtonBox,QMessageBox,QInputDialog,QScrollArea)
from ..roles import list_roles
from ..modules.life_state import MUSCLES

STATUS={'todo':'待开始','doing':'进行中','paused':'暂缓','done':'已完成'}
INTENSITY={'light':'轻','moderate':'中','high':'高'}

from .module_forms import ModulePage,button,hm_pair,clock_pair,PlaceholderSpin,form_dialog,spin

class WorkPage(ModulePage):
    module='work'
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub
        layout=self.layout_header('工作管理','时间记录投入，进度记录实际推进。子任务最多一层；归档保留历史。')
        row=QHBoxLayout();button('新建任务',lambda:self.edit_task(),row,True);button('添加子任务',self.add_child,row)
        self.archived=QCheckBox('显示已归档');self.archived.toggled.connect(self.refresh);row.addStretch();row.addWidget(self.archived);layout.addLayout(row)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['任务','状态','完成进度','投入 / 预计（时间比例）','截止','优先级']);self.tree.setRootIsDecorated(True);self.tree.setAlternatingRowColors(True);layout.addWidget(self.tree,1)
        self.tree.setStyleSheet('QTreeWidget {border: none;} QTreeWidget::item {padding: 12px 6px; border-bottom: 1px solid rgba(128,128,128,45);} QTreeWidget::item:selected {background: rgba(100,120,150,45); color: palette(text); border-left: 3px solid #7189d9;}')
        self.tree.setIndentation(26)
        self.tree.itemDoubleClicked.connect(lambda *_:self.edit_selected())
        actions=QHBoxLayout();button('编辑 / 更新进度',self.edit_selected,actions);button('暂缓 / 继续',self.pause_task,actions);button('归档 / 恢复',self.archive_task,actions);button('查看历史',self.show_history,actions);layout.addLayout(actions)
        focus=QHBoxLayout();focus.addWidget(QLabel('陪伴人格'));self.roles=QComboBox();focus.addWidget(self.roles)
        button('开始所选任务的番茄钟',self.start_selected,focus,True);focus.addStretch();layout.addLayout(focus)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        button('查看今日安排建议',self.suggestions,layout)
        row=QHBoxLayout();button('下班结算 · 进入恢复',self.end_work,row,True);button('我的状态 / 恢复安排',self.recovery_options,row);layout.addLayout(row)
        self.recovery_note=QLabel();self.recovery_note.setWordWrap(True);layout.addWidget(self.recovery_note)
        hub.feedback.connect(self.afterwork_feedback)
        hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def afterwork_feedback(self,role,text):
        director=next((s['role_id'] for s in self.hub.duties.slots() if s['id']=='director'),None)
        if self.hub.recovery.status().get('active') and role==director:self.recovery_note.setText(text)
    def end_work(self):
        minutes,ok=QInputDialog.getInt(self,'下班恢复','休息多久（分钟，不消耗金币）',60,5,240)
        if ok:
            result=self.invoke(lambda:self.hub.end_work(minutes))
            if result:self.recovery_note.setText(f"今天 {result['minutes']} 分钟有效工作，{len(result['completed'])} 项确认完成，{len(result['progress'])} 项进展。"+self.hub.recovery.suggestion())
    def recovery_options(self):
        choices=['我有些疲惫','我有些难过','我有些烦躁','情绪已平静','恢复后继续休息','结束恢复，我想轻量学习','结束恢复，我想轻量活动']
        text,ok=QInputDialog.getItem(self,'状态与意愿','不会因为缺少记录扣分，也不会自动派新任务',choices,0,False)
        if not ok:return
        index=choices.index(text)
        if index<4:self.hub.recovery.report(['tired','sad','irritable','calm'][index])
        else:self.hub.recovery.finish(['rest','study','activity'][index-4])
        self.recovery_note.setText(self.hub.recovery.suggestion());self.hub.changed.emit('recovery')
    def selected(self):
        item=self.tree.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else None
    def refresh(self,*args):
        selected=self.selected();selected_id=selected['id'] if selected else None
        rows=self.hub.work.tasks(self.archived.isChecked());self.tree.clear();items={}
        for row in rows:
            item=QTreeWidgetItem([row['title']+('（归档）' if row['archived'] else ''),STATUS.get(row['status'],row['status']),'',f"{row['actual_seconds']/60:.1f} / {row['estimate_minutes'] or '未设'} 分钟"+(f" · {row['actual_seconds']/60/row['estimate_minutes']:.0%}" if row['estimate_minutes'] else ''),row['due'] or '未设置',str(row['priority'])])
            item.setData(0,Qt.ItemDataRole.UserRole,row);items[row['id']]=item
        for row in rows:
            item=items[row['id']];parent_item=items.get(row['parent_id'])
            if parent_item:parent_item.addChild(item)
            else:self.tree.addTopLevelItem(item)
            progress=QProgressBar();progress.setRange(0,100);progress.setValue(round(row['progress']));progress.setFormat('完成 %p%');progress.setMaximumHeight(20);self.tree.setItemWidget(item,2,progress)
            if row['id']==selected_id:self.tree.setCurrentItem(item)
        self.tree.expandAll();self.tree.setColumnWidth(0,280);self.tree.setColumnWidth(2,150);self.tree.setColumnWidth(3,255)
        selected_role=self.roles.currentData();self.roles.blockSignals(True);self.roles.clear()
        for rid,name,*_ in list_roles(self.hub.root):self.roles.addItem(name,rid)
        self.roles.setCurrentIndex(max(0,self.roles.findData(selected_role or 'rui')));self.roles.blockSignals(False)
        state=self.hub.focus.status();self.summary.setText('计时进行中。切换任务前请先结束当前轮，已有时间不会转移到另一个任务。' if state['state']!='idle' else '选择任务可启动工作番茄钟，也可以在专注页不绑定任务。工作每有效分钟 1 积分，不兑换商城金币。')
    def add_child(self):
        row=self.selected()
        if not row:return
        if row['parent_id']:QMessageBox.information(self,'两级任务','请选择父任务，再添加同级子任务。');return
        self.edit_task(parent_id=row['id'])
    def edit_selected(self):
        row=self.selected()
        if row:self.edit_task(row)
    def edit_task(self,row=None,parent_id=None):
        row=row or {};dlg,form,error,buttons=form_dialog(self,'编辑工作任务' if row else '新建工作任务')
        title=QLineEdit(row.get('title',''));estimate=spin(row.get('estimate_minutes'),24000,' 分钟',zero_placeholder=True)
        due=QLineEdit(row.get('due',''));due.setPlaceholderText('YYYY-MM-DD；留空不设截止')
        priority=QSpinBox();priority.setRange(0,3);priority.setValue(row.get('priority',1))
        dida=QLineEdit(row.get('dida_id',''));dida.setPlaceholderText('可选：已有滴答任务 ID，仅关联标识')
        for label,w in [('任务名称',title),('预计时长',estimate),('截止日期',due),('优先级（越大越优先）',priority),('滴答关联',dida)]:form.addRow(label,w)
        status=QComboBox()
        for key,label in STATUS.items():status.addItem(label,key)
        status.setCurrentIndex(max(0,status.findData(row.get('status','todo'))));progress=spin(row.get('progress'),100,' %')
        if row:form.addRow('状态',status);form.addRow('实际进度',progress)
        if row and any(t['parent_id']==row['id'] for t in self.hub.work.tasks(True)):
            progress.setEnabled(False);form.addRow(QLabel('父任务进度由子任务汇总，请更新子任务。'))
        def save():
            values=dict(title=title.text(),estimate_minutes=estimate.value(),due=due.text().strip(),priority=priority.value(),dida_id=dida.text().strip())
            if row:
                values['status']=status.currentData()
                if progress.isEnabled():values['progress']=progress.value()
                self.hub.work.update(row['id'],**values)
            else:self.hub.work.create(parent_id=parent_id,**values)
        buttons.accepted.connect(lambda:self.save_dialog(dlg,error,save));dlg.exec()
    def pause_task(self):
        row=self.selected()
        if row:self.invoke(lambda:self.hub.work.update(row['id'],status='doing' if row['status']=='paused' else 'paused'))
    def archive_task(self):
        row=self.selected()
        if row:self.invoke(lambda:self.hub.work.archive(row['id'],not row['archived']))
    def start_selected(self):
        row=self.selected()
        if row:
            def start():
                self.hub.start_focus('工作',row['title'],self.roles.currentData(),duration=self.hub.focus.options()['focus_minutes']*60,task_id=row['id'])
                self.hub.navigate.emit('focus')
            self.invoke(start)
    def show_history(self):
        row=self.selected()
        if not row:return
        dlg=QDialog(self);dlg.setWindowTitle(row['title']+' · 历史');dlg.resize(650,480);layout=QVBoxLayout(dlg);view=QPlainTextEdit();view.setReadOnly(True);layout.addWidget(view)
        entries=self.hub.work.history(row['id']);view.setPlainText('\n\n'.join(f"{r['created']} · {r['kind']}\n"+(json.dumps(r['payload'],ensure_ascii=False,indent=2) if isinstance(r['payload'],(dict,list)) else str(r['payload'])) for r in entries) or '暂无变更记录')
        button('关闭',dlg.accept,layout);dlg.exec()
    def suggestions(self):
        rows=self.hub.work.suggest();text='\n'.join(f"{i+1}. {r['title']} · 截止 {r['due'] or '未设置'} · 预计 {r['estimate_minutes']} 分钟" for i,r in enumerate(rows))
        QMessageBox.information(self,'今日安排建议','根据截止日期、优先级和预计时长排序，仅供选择，不会自动改动计划。\n\n'+(text or '暂无可安排任务。'))

class DutiesPage(ModulePage):
    module='duties'
    def __init__(self,hub,parent=None):
        super().__init__(parent);self.hub=hub
        layout=self.layout_header('职责与交接','职责槽位长期稳定；更换人格只改变负责人，不移动真实数据、不删除旧人格。')
        tabs=QTabWidget();layout.addWidget(tabs,1)
        assignments=QWidget();al=QVBoxLayout(assignments);tabs.addTab(assignments,'职责负责人')
        self.slots=QTreeWidget();self.slots.setHeaderLabels(['固定职责','当前人格']);al.addWidget(self.slots,1)
        button('替换所选职责的人格',self.assign,al,True)
        button('配置职责插件与 Skill',self.configure_extensions,al)
        inbox=QWidget();il=QVBoxLayout(inbox);tabs.addTab(inbox,'记录与整理交接')
        row=QHBoxLayout();button('快速记录并交接',self.capture,row,True);self.done=QCheckBox('显示已处理');row.addStretch();row.addWidget(self.done);il.addLayout(row)
        self.handoffs=QListWidget();self.handoffs.setWordWrap(True);il.addWidget(self.handoffs,1)
        row=QHBoxLayout();button('查看交接内容',self.inspect,row);button('确认整理完成',self.complete,row);button('标记处理失败',self.fail,row);il.addLayout(row)
        hint=QLabel('记录原文不会因交接结束而删除。分类完成后才从待办中移出；失败保留。涉及文件移动时仍须通过已有授权文件工具执行。');hint.setWordWrap(True);hint.setObjectName('muted');il.addWidget(hint)
        self.done.toggled.connect(self.refresh);hub.changed.connect(lambda *_:self.refresh());self.refresh()
    def refresh(self,*args):
        selected=self.slots.currentItem();sid=selected.data(0,Qt.ItemDataRole.UserRole)['id'] if selected else None
        names={r[0]:r[1] for r in list_roles(self.hub.root)};self.slots.clear()
        for row in self.hub.duties.slots():
            item=QTreeWidgetItem([row['title'],names.get(row['role_id'],'未分配' if not row['role_id'] else row['role_id']+'（已停用）')]);item.setData(0,Qt.ItemDataRole.UserRole,row);self.slots.addTopLevelItem(item)
            if row['id']==sid:self.slots.setCurrentItem(item)
        self.slots.setColumnWidth(0,260)
        selected=self.handoffs.currentItem();hid=selected.data(Qt.ItemDataRole.UserRole)['id'] if selected else None;self.handoffs.clear()
        labels={'pending':'待整理','failed':'处理失败','done':'已完成','completed':'已完成'}
        for row in self.hub.duties.handoffs(self.done.isChecked()):
            item=QListWidgetItem(f"{row['title']} · {labels.get(row['status'],row['status'])}\n{row.get('request','')}\n{row.get('result','')}");item.setData(Qt.ItemDataRole.UserRole,row);self.handoffs.addItem(item)
            if row['id']==hid:self.handoffs.setCurrentItem(item)
    def configure_extensions(self):
        item=self.slots.currentItem()
        if not item:return
        row=item.data(0,Qt.ItemDataRole.UserRole);ext=row.get('extensions',{})
        dlg,form,error,buttons=form_dialog(self,'职责能力绑定')
        plugins=QPlainTextEdit('\n'.join(ext.get('plugins',[])));skills=QPlainTextEdit('\n'.join(ext.get('skills',[])))
        form.addRow('插件 ID（每行一个）',plugins);form.addRow('Skill 目录名（每行一个）',skills)
        note=QLabel('仅绑定已安装扩展，按需加载。更换人格会保留职责绑定；插件角色限制仍生效，不搬运私人密钥或角色参数。');note.setWordWrap(True);form.addRow(note)
        buttons.accepted.connect(lambda:self.save_dialog(dlg,error,lambda:self.hub.duties.set_extensions(row['id'],[v.strip() for v in plugins.toPlainText().splitlines() if v.strip()],[v.strip() for v in skills.toPlainText().splitlines() if v.strip()])))
        dlg.exec()
    def assign(self):
        item=self.slots.currentItem()
        if not item:return
        row=item.data(0,Qt.ItemDataRole.UserRole);roles=[(None,'未分配')]+[(r[0],r[1]) for r in list_roles(self.hub.root)]
        labels=[name+' · '+(rid or '无') for rid,name in roles];selected=next((i for i,(rid,_) in enumerate(roles) if rid==row['role_id']),0)
        text,ok=QInputDialog.getItem(self,'替换人格',row['title'],labels,selected,False)
        if ok:self.invoke(lambda:self.hub.duties.assign(row['id'],roles[labels.index(text)][0]))
    def capture(self):
        dlg,form,error,buttons=form_dialog(self,'快速记录')
        title=QLineEdit();body=QPlainTextEdit();request=QLineEdit();files=QPlainTextEdit();files.setMaximumHeight(70);files.setPlaceholderText('每行一个涉及文件路径；这里只记录，不执行文件修改')
        for label,w in [('标题',title),('原始信息',body),('整理要求',request),('涉及文件',files)]:form.addRow(label,w)
        buttons.accepted.connect(lambda:self.save_dialog(dlg,error,lambda:self.hub.duties.capture(title.text(),body.toPlainText(),request.text(),files.toPlainText())));dlg.exec()
    def selected_handoff(self):
        item=self.handoffs.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
    def inspect(self):
        row=self.selected_handoff()
        if not row:return
        dlg=QDialog(self);dlg.setWindowTitle('交接详情');dlg.resize(600,450);layout=QVBoxLayout(dlg);text=QPlainTextEdit();text.setReadOnly(True);text.setPlainText(json.dumps(row,ensure_ascii=False,indent=2));layout.addWidget(text);button('关闭',dlg.accept,layout);dlg.exec()
    def complete(self):
        row=self.selected_handoff()
        if not row or row['status'] in ('done','completed'):return
        dlg,form,error,buttons=form_dialog(self,'确认整理结果')
        category=QComboBox();category.addItems(self.hub.organizer.categories());title=QLineEdit(row['title']);note=QLineEdit();note.setPlaceholderText('简述已完成的分类/文件操作，拿不准请保留待办')
        form.addRow('分类',category);form.addRow('整理后标题',title);form.addRow('完成说明',note)
        buttons.accepted.connect(lambda:self.save_dialog(dlg,error,lambda:self.hub.duties.complete_handoff(row['id'],category.currentText(),title.text(),note.text())));dlg.exec()
    def fail(self):
        row=self.selected_handoff()
        if not row or row['status'] in ('done','completed'):return
        text,ok=QInputDialog.getText(self,'保留失败交接','失败原因 / 需要用户澄清的内容：')
        if ok:self.invoke(lambda:self.hub.duties.fail_handoff(row['id'],text))

# Compatibility import: shared form helpers above remain available to Work/Duties.
from .life import LifePage
from ..numeric_inputs import NumberSpin as QSpinBox, DecimalSpin as QDoubleSpinBox
