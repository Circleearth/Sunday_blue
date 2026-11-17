from PySide6.QtWidgets import QTreeWidget,QAbstractItemView
from PySide6.QtCore import Signal,Qt
class OrderedTree(QTreeWidget):
 reordered=Signal(object)
 def __init__(self):
  super().__init__();self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
 def dropEvent(self,event):
  item=self.currentItem();target=self.itemAt(event.position().toPoint())
  if not item or not target or item is target or item.parent()!=target.parent():event.ignore();return
  parent=item.parent();siblings=[parent.child(i) for i in range(parent.childCount())] if parent else [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
  siblings.remove(item);siblings.insert(siblings.index(target),item)
  self.reordered.emit([i.data(0,Qt.ItemDataRole.UserRole)['id'] for i in siblings]);event.accept()
