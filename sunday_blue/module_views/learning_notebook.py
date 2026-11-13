"""A small learning notebook: hierarchy, familiarity and local notes."""
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QTreeWidget,QTreeWidgetItem,QHeaderView,QLineEdit,QPlainTextEdit,QTabWidget,QComboBox,QCheckBox,QMessageBox,QInputDialog,QProgressBar,QDialog,QPushButton,QDialogButtonBox
from .module_forms import ModulePage,button,form_dialog,spin
from .life_widgets import label
from ..modules.learning import FAMILIARITY
class NotebookDialog(QDialog):
 def __init__(self,parent=None):super().__init__(parent);self.editors={}
 def reject(self):
  if any(e.document().isModified() for e in self.editors.values()) and QMessageBox.question(self,'未保存笔记','放弃本次修改？')!=QMessageBox.StandardButton.Yes:return
  super().reject()

class LearningPage(ModulePage):
 module='learning'
 def __init__(self,hub,parent=None):
  super().__init__(parent);self.hub=hub;self.rows=[];box=self.layout_header('学习笔记本','整理课程，记下疑惑，积累自己的理解。章节阅读与知识点熟悉状态分别保留。')
  row=QHBoxLayout()
  for title,kind in [('添加课程','subject'),('添加章节','chapter'),('添加知识点','unit')]:button(title,lambda checked=False,k=kind:self.add(k),row,kind=='subject')
  self.search=QLineEdit();self.search.setPlaceholderText('搜索名称、备注、疑惑或拓展');self.search.setClearButtonEnabled(True);row.addWidget(self.search,1);box.addLayout(row)
  self.summary=label();box.addWidget(self.summary)
  self.split=QSplitter();self.tree=QTreeWidget();self.tree.setHeaderLabels(['课程 / 章节 / 知识点','熟悉进度','备注']);self.tree.setIndentation(22);self.tree.setAlternatingRowColors(True);self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents);self.tree.header().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents);self.split.addWidget(self.tree)
  self.tree.setStyleSheet('QTreeWidget::item {padding: 8px 4px;} QTreeWidget::item:selected {background: rgba(100,120,150,45); color: palette(text);} QTreeWidget::branch:selected {background: rgba(100,120,150,45);}');self.tree.header().setStretchLastSection(False);self.split.setChildrenCollapsible(False)
  pane=QWidget();right=QVBoxLayout(pane);self.detail_title=label('选择一个条目','cardTitle');right.addWidget(self.detail_title);self.detail=label();right.addWidget(self.detail)
  self.progress=QProgressBar();self.progress.setRange(0,100);right.addWidget(self.progress)
  controls=QHBoxLayout();controls.addWidget(label('熟悉状态'));self.familiarity=QComboBox()
  for key,(name,_) in FAMILIARITY.items():self.familiarity.addItem(name,key)
  controls.addWidget(self.familiarity,1);right.addLayout(controls);self.read_done=QCheckBox('这个章节已读完');right.addWidget(self.read_done)
  self.note_tabs=QTabWidget();self.readers={}
  for key,title in [('note','备注 / 小结'),('questions','疑惑'),('extensions','拓展')]:
   text=QPlainTextEdit();text.setReadOnly(True);self.readers[key]=text;self.note_tabs.addTab(text,title)
  right.addWidget(self.note_tabs,1);row=QHBoxLayout();button('查看 / 编辑笔记',self.edit_notes,row,True);button('重命名',self.rename,row);right.addLayout(row)
  button('练习与旧记录',self.legacy_history,right);self.split.addWidget(pane);self.split.setSizes([600,390]);box.addWidget(self.split,1)
  row=QHBoxLayout();button('学习当前知识点',self.start,row,True);next_button=button('下一知识点',self.next_unit,row);next_button.setToolTip('只切换笔记条目；正在进行的专注仍属于原知识点。');row.addStretch();box.addLayout(row)
  self.tree.currentItemChanged.connect(lambda *_:self.inspect());self.tree.itemDoubleClicked.connect(lambda *_:self.edit_notes());self.familiarity.activated.connect(self.change_state);self.read_done.clicked.connect(self.chapter);self.search.textChanged.connect(self.filter_items);hub.changed.connect(lambda m:self.refresh() if m in ('learning','focus','modules') else None);self.refresh()
 def selected(self,unit=False):
  item=self.tree.currentItem();r=item.data(0,Qt.ItemDataRole.UserRole) if item else None
  if not r or unit and r['kind']!='unit':raise ValueError('请先选择一个知识点' if unit else '请先选择课程、章节或知识点')
  return r
 def add(self,kind):
  parent=None
  if kind!='subject':
   try:
    r=self.selected();byid={n['id']:n for n in self.rows};wanted='subject' if kind=='chapter' else 'chapter'
    while r['kind']!=wanted:
     if not r['parent']:raise ValueError('请先选择课程中的章节，再添加知识点')
     r=byid[r['parent']]
    parent=r['id']
   except ValueError as exc:QMessageBox.information(self,'选择位置',str(exc));return
  title,ok=QInputDialog.getText(self,'添加'+dict(subject='课程',chapter='章节',unit='知识点')[kind],'名称')
  if ok:
   nid=self.invoke(lambda:self.hub.learning.add(kind,title,parent))
   if nid and nid in self.items:self.tree.setCurrentItem(self.items[nid])
 def refresh(self):
  item=self.tree.currentItem();selected=item.data(0,Qt.ItemDataRole.UserRole)['id'] if item else None
  self.rows=self.hub.learning.notebook_rows();self.items={};children={}
  with QSignalBlocker(self.tree):
   self.tree.clear()
   for r in self.rows:
    state=FAMILIARITY[r['state']][0] if r['kind']=='unit' else f"{r['progress']:.0f}% · 熟悉 {r['familiar_count']}/{r['unit_count']}"+((' · 已读完' if r['done'] else '') if r['kind']=='chapter' else '')
    item=QTreeWidgetItem([r['title'],state,'有笔记' if any(r[k] for k in ('note','questions','extensions')) else '']);item.setData(0,Qt.ItemDataRole.UserRole,r);self.items[r['id']]=item;children.setdefault(r['parent'],[]).append(r)
   for r in self.rows:
    parent=self.items.get(r['parent']);parent.addChild(self.items[r['id']]) if parent else self.tree.addTopLevelItem(self.items[r['id']])
   self.tree.expandAll()
   if selected in self.items:self.tree.setCurrentItem(self.items[selected])
   elif self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
  self.unit_order=[]
  def visit(parent):
   for r in children.get(parent,[]):
    if r['kind']=='unit':self.unit_order.append(r['id'])
    visit(r['id'])
  visit(None);units=[r for r in self.rows if r['kind']=='unit'];self.summary.setText(f"{sum(r['kind']=='subject' for r in self.rows)} 门课程 · {len(units)} 个知识点 · 已熟悉 {sum(r['state']=='familiar' for r in units)} 个 · 绑定专注 {sum(r['minutes'] for r in units):.1f} 分钟")
  self.filter_items();self.inspect()
 def filter_items(self,*args):
  query=self.search.text().strip().casefold();byid={r['id']:r for r in self.rows};visible=set()
  matches={r['id'] for r in self.rows if not query or any(query in r[k].casefold() for k in ('title','note','questions','extensions'))}
  for r in self.rows:
   parent=r['parent'];line=[r['id']]
   while parent:line.append(parent);parent=byid[parent]['parent']
   if any(n in matches for n in line):visible.update(line)
  for nid,item in self.items.items():item.setHidden(nid not in visible)
 def inspect(self):
  try:r=self.selected()
  except ValueError:
   self.detail_title.setText('先添加课程，再建立章节和知识点');self.detail.setText('双击条目即可打开笔记。');self.familiarity.setEnabled(False);self.read_done.hide();self.progress.setValue(0)
   for text in self.readers.values():text.clear()
   return
  self.detail_title.setText(r['title']);self.detail.setText(f"绑定学习 {r['minutes']:.1f} 分钟 · 熟悉 {r['familiar_count']}/{r['unit_count']} 个知识点\n熟悉状态用于个人整理，不自动生成练习或契约掌握证据。")
  self.progress.setValue(round(r['progress']));self.progress.setFormat('熟悉进度 %p%');self.familiarity.setEnabled(r['kind']=='unit');self.familiarity.setCurrentIndex(self.familiarity.findData(r['state']));self.read_done.setVisible(r['kind']=='chapter');self.read_done.setChecked(bool(r['done']))
  for key,text in self.readers.items():text.setPlainText(r[key] or {'note':'这里可以记下摘要、资料链接或自己的解释。','questions':'还有哪里没想明白？把问题留在这里。','extensions':'想到的应用、关联知识、延伸阅读。'}[key])
 def change_state(self,*args):
  try:r=self.selected(True)
  except ValueError:return
  self.invoke(lambda:self.hub.learning.save_notebook(r['id'],r['note'],r['questions'],r['extensions'],self.familiarity.currentData(),expected=r))
 def chapter(self,*args):
  try:r=self.selected()
  except ValueError:return
  if r['kind']=='chapter':self.invoke(lambda:self.hub.learning.chapter_done(r['id'],self.read_done.isChecked()))
 def next_unit(self):
  order=[nid for nid in self.unit_order if not self.items[nid].isHidden()]
  if not order:return
  try:r=self.selected()
  except ValueError:r={}
  if r.get('id') in order:target=order[(order.index(r['id'])+1)%len(order)]
  else:
   children=[n['id'] for n in self.rows if n['parent']==r.get('id')];target=next((nid for nid in order if nid in children or next(n for n in self.rows if n['id']==nid)['parent'] in children),order[0])
  self.tree.setCurrentItem(self.items[target]);self.tree.scrollToItem(self.items[target])
 def edit_notes(self):
  try:r=self.selected()
  except ValueError:return
  dlg=NotebookDialog(self);dlg.setWindowTitle(r['title']+' · 笔记');area=dlg.screen().availableGeometry();dlg.resize(min(760,area.width()-40),min(600,area.height()-40));box=QVBoxLayout(dlg);tabs=QTabWidget();box.addWidget(tabs,1);editors={}
  for key,title in [('note','备注 / 小结'),('questions','疑惑'),('extensions','拓展')]:
   editor=QPlainTextEdit(r[key]);editor.document().setModified(False);editors[key]=editor;tabs.addTab(editor,title)
  error=label();box.addWidget(error);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);box.addWidget(buttons)
  def save():self.save_dialog(dlg,error,lambda:self.hub.learning.save_notebook(r['id'],**{k:e.toPlainText() for k,e in editors.items()},expected=r))
  dlg.editors=editors;buttons.accepted.connect(save);buttons.rejected.connect(dlg.reject);dlg.exec()

 def rename(self):
  try:r=self.selected()
  except ValueError:return
  title,ok=QInputDialog.getText(self,'重命名','名称',text=r['title'])
  if ok:self.invoke(lambda:self.hub.learning.rename(r['id'],title))
 def legacy_history(self):
  try:r=self.selected(True)
  except ValueError as exc:QMessageBox.information(self,'选择知识点',str(exc));return
  e=self.hub.learning.evidence(r['id']);dlg=QDialog(self);dlg.setWindowTitle('旧练习记录 · '+r['title']);box=QVBoxLayout(dlg);text=QPlainTextEdit();text.setReadOnly(True);box.addWidget(text)
  with self.hub.db.connect() as c:
   attempts=list(c.execute('SELECT created,total,correct,note FROM learning_attempts WHERE unit=? ORDER BY created DESC',(r['id'],)));reviews=list(c.execute('SELECT day,passed,note FROM learning_reviews WHERE unit=? ORDER BY day DESC',(r['id'],)))
  text.setPlainText(f"旧证据分 {e['score']:.0f} · 练习 {e['correct']}/{e['total']} · 复检 {e['reviews']} 次\n\n"+'\n'.join(f"{a['created']} 练习 {a['correct']}/{a['total']}：{a['note']}" for a in attempts)+'\n'+'\n'.join(f"{a['day']} 复检 {'通过' if a['passed'] else '未通过'}：{a['note']}" for a in reviews));button('记录练习（可选）',lambda:(dlg.accept(),self.practice()),box);button('关闭',dlg.accept,box);dlg.resize(600,420);dlg.exec()
 def practice(self):
  try:r=self.selected(True)
  except ValueError:return
  dlg,form,error,buttons=form_dialog(self,'记录练习');total=spin(1,10000);correct=spin(0,10000);note=QPlainTextEdit();note.setPlaceholderText('可记录错题、错因或练习心得。有错题时需填写。')
  form.addRow('题数',total);form.addRow('答对',correct);form.addRow('练习记录',note)
  buttons.accepted.connect(lambda:self.save_dialog(dlg,error,lambda:self.hub.learning.practice(r['id'],total.value(),correct.value(),note.toPlainText())));dlg.exec()
 def start(self):
  def action():
   r=self.selected(True);role=next((s['role_id'] for s in self.hub.duties.slots() if s['id']=='study' and s['role_id']),None)
   if not role:
    from ..roles import list_roles
    roles=list_roles(self.hub.root);role=next((x[0] for x in roles if x[0]=='loluns'),roles[0][0])
   self.hub.start_focus('学习',r['title'],role,duration=self.hub.focus.options()['focus_minutes']*60);self.hub.learning.bind(self.hub.focus.status()['id'],r['id']);self.hub.db.set('focus_loop',self.hub.db.get('focus_loop',{})|{'learning_unit':r['id']});self.hub.navigate.emit('focus')
  self.invoke(action)
