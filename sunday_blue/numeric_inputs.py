"""Numeric fields with units outside the editable text."""
from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import QLabel, QSpinBox, QDoubleSpinBox


class NumericMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._units = {}
        for side in ("left", "right"):
            label = QLabel(self)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setObjectName("muted")
            label.hide()
            self._units[side] = label
        self._select_on_release = False
        self.lineEdit().installEventFilter(self)

    def setSuffix(self, text):
        self._set_unit("right", text)

    def setPrefix(self, text):
        self._set_unit("left", text)

    def _set_unit(self, side, text):
        label = self._units[side]
        label.setText(str(text).strip())
        label.setVisible(bool(label.text()))
        self._place_units()
        self.updateGeometry()

    def _unit_width(self, side):
        label = self._units[side]
        return label.fontMetrics().horizontalAdvance(label.text()) + 8 if label.text() else 0

    def _place_units(self):
        if not hasattr(self, "_units"):
            return
        edit = self.lineEdit()
        left, right = self._unit_width("left"), self._unit_width("right")
        edit.setTextMargins(left, 0, right, 0)
        rect = edit.geometry()
        self._units["left"].setGeometry(rect.left()+3, rect.top(), left, rect.height())
        self._units["right"].setGeometry(rect.right()-right+4, rect.top(), right, rect.height())
        for label in self._units.values():
            label.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_units()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._place_units()

    def sizeHint(self):
        size = super().sizeHint()
        if hasattr(self, "_units"):
            size += QSize(self._unit_width("left") + self._unit_width("right"), 0)
        return size

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        if hasattr(self, "_units"):
            size += QSize(self._unit_width("left") + self._unit_width("right"), 0)
        return size

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._on_focus(event)

    def focusOutEvent(self, event):
        self._select_on_release = False
        super().focusOutEvent(event)

    def _on_focus(self, event):
        self._select_on_release = event.reason() == Qt.FocusReason.MouseFocusReason
        edit = self.lineEdit()
        QTimer.singleShot(0, edit, edit.selectAll)

    def eventFilter(self, obj, event):
        if obj is self.lineEdit():
            if event.type() == QEvent.Type.FocusIn:
                self._on_focus(event)
            elif event.type() == QEvent.Type.MouseButtonRelease and self._select_on_release:
                self._select_on_release = False
                QTimer.singleShot(0, obj, obj.selectAll)
            elif event.type() == QEvent.Type.FocusOut:
                self._select_on_release = False
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NumberSpin(NumericMixin, QSpinBox):
    pass


class DecimalSpin(NumericMixin, QDoubleSpinBox):
    pass
