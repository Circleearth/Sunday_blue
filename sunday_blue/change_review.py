"""Shared readable before/after review for files, confirmed memory and personas."""
import difflib
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel, QSplitter, QTextEdit


class ChangeReview(QWidget):
    def __init__(self, before, after, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split)
        self.before, self.after = QPlainTextEdit(before), QPlainTextEdit(after)
        for title, editor in (('修改前', self.before), ('修改后', self.after)):
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(0, 0, 0, 0)
            column.addWidget(QLabel(title))
            editor.setReadOnly(True)
            column.addWidget(editor)
            split.addWidget(panel)
        before_lines, after_lines = before.splitlines(), after.splitlines()
        old_ranges, new_ranges = [], []
        for kind, a, b, c, d in difflib.SequenceMatcher(None, before_lines, after_lines).get_opcodes():
            if kind != 'equal':
                old_ranges.extend(range(a, b))
                new_ranges.extend(range(c, d))
        self.highlight(self.before, old_ranges, QColor(210, 75, 85, 55))
        self.highlight(self.after, new_ranges, QColor(55, 170, 120, 55))

    @staticmethod
    def highlight(editor, lines, color):
        selections = []
        for line in lines:
            block = editor.document().findBlockByNumber(line)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.format.setBackground(color)
            selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        editor.setExtraSelections(selections)
