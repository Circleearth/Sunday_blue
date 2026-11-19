"""Application-owned drag moves: never let Qt remove a refreshed source row."""
import uuid
from PySide6.QtWidgets import QTreeWidget,QAbstractItemView,QToolTip,QMenu,QInputDialog
from PySide6.QtCore import Signal,Qt,QMimeData
from PySide6.QtGui import QDrag
class OrderedTree(QTreeWidget):
 move_requested=Signal(str,object,object)
 choose_parent=Signal(str)
 MIME='application/x-sunday-node'
 def __init__(self):
  super().__init__();self.token=uuid.uuid4().hex;self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.customContextMenuRequested.connect(self.context_menu);self.setDragEnabled(True);self.setAcceptDrops(True);self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop);self.setDefaultDropAction(Qt.DropAction.CopyAction);self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.setToolTip('上下边缘排序；同级工作向右放入子级。也可右键选择移动到。')
 def context_menu(self,point):
  item=self.itemAt(point)
  if not item:return
  self.setCurrentItem(item);key=item.data(0,Qt.ItemDataRole.UserRole)['id'];menu=QMenu(self);action=menu.addAction('移动到…')
  if menu.exec(self.viewport().mapToGlobal(point))==action:self.choose_parent.emit(key)
 def startDrag(self,actions):
  item=self.currentItem()
  if not item:return
  drag=QDrag(self);mime=QMimeData();mime.setData(self.MIME,(self.token+':'+item.data(0,Qt.ItemDataRole.UserRole)['id']).encode());drag.setMimeData(mime)
  drag.exec(Qt.DropAction.CopyAction) # Transport only; domain service performs the actual move.
 def source_id(self,event):
  try:
   token,key=bytes(event.mimeData().data(self.MIME)).decode().split(':',1)
   return key if token==self.token else None
  except Exception:return None
 def dragEnterEvent(self,event):
  if self.source_id(event):event.setDropAction(Qt.DropAction.CopyAction);event.accept()
  else:event.ignore()
 def destination(self,point,source=None):
  target=self.itemAt(point)
  if target is None:return None,None,'移到顶层末尾'
  r=target.data(0,Qt.ItemDataRole.UserRole);rect=self.visualItemRect(target);offset=point.y()-rect.top();parent=target.parent();pid=parent.data(0,Qt.ItemDataRole.UserRole)['id'] if parent else None
  if offset<rect.height()*.25:return pid,r['id'],'放在此项之前'
  if offset>rect.height()*.75:
   index=parent.indexOfChild(target) if parent else self.indexOfTopLevelItem(target);count=parent.childCount() if parent else self.topLevelItemCount();following=(parent.child(index+1) if parent else self.topLevelItem(index+1)) if index+1<count else None
   return pid,following.data(0,Qt.ItemDataRole.UserRole)['id'] if following else None,'放在此项之后'
  current=self.currentItem()
  if self.property('treeDomain')!='learning' and current and current.parent()==target.parent() and point.x()<rect.left()+rect.width()*.65:return pid,r['id'],'调整同级顺序；向右拖可移入'
  if self.property('treeDomain')=='learning' and current and current.data(0,Qt.ItemDataRole.UserRole)['kind']==r['kind']:return pid,r['id'],'放在此项之前'
  return r['id'],None,'移入此项'
 def dragMoveEvent(self,event):
  if not self.source_id(event):event.ignore();return
  _,_,hint=self.destination(event.position().toPoint());QToolTip.showText(self.viewport().mapToGlobal(event.position().toPoint()),hint,self);event.setDropAction(Qt.DropAction.CopyAction);event.accept()
 def dropEvent(self,event):
  key=self.source_id(event)
  if not key:event.ignore();return
  target=self.itemAt(event.position().toPoint())
  if target and target.data(0,Qt.ItemDataRole.UserRole)['id']==key:event.ignore();return
  parent,before,_=self.destination(event.position().toPoint());event.setDropAction(Qt.DropAction.CopyAction);event.accept();QToolTip.hideText()
  self.move_requested.emit(key,parent,before)
  matches=self.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive,0)
  for item in matches:
   if item.data(0,Qt.ItemDataRole.UserRole)['id']==key:
    self.setCurrentItem(item);self.scrollToItem(item);break

def choose_parent(page,domain,key):
 rows=page.hub.work.tasks() if domain=='work' else page.hub.learning.notebook_rows();byid={r['id']:r for r in rows};col='parent_id' if domain=='work' else 'parent'
 if key not in byid:return
 excluded={key}
 while True:
  updated=excluded|{r['id'] for r in rows if r[col] in excluded}
  if updated==excluded:break
  excluded=updated
 targets=[(None,'顶层')] if domain=='work' or byid[key]['kind']=='subject' else []
 wanted={'chapter':'subject','unit':'chapter'}.get(byid[key].get('kind'))
 for r in rows:
  if r['id'] in excluded or domain=='learning' and r['kind']!=wanted:continue
  parts=[r['title']];p=r[col]
  while p in byid:parts.insert(0,byid[p]['title']);p=byid[p][col]
  targets.append((r['id'],' / '.join(parts)+' · '+r['id'][:6]))
 if not targets:return
 text,ok=QInputDialog.getItem(page,'移动归属','选择目标目录；备注、历史及计时关联保留',[t[1] for t in targets],0,False)
 if ok:page.move_node(key,dict((title,nid) for nid,title in targets)[text],None)
