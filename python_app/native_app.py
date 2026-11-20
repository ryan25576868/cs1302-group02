"""Prism Native — a pure-Python desktop code analysis workspace.

This is the Python-first edition. The UI, editor, four analysis views, guide,
trace playback and file handling are implemented with PySide6. There is no
HTML, CSS or JavaScript application code.
"""

from __future__ import annotations

import html
import math
import sys
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPauseAnimation, QPoint,
    QPropertyAnimation, QRegularExpression, QSettings, Qt, QThread, QTimer,
    QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QRadialGradient,
    QResizeEvent, QShowEvent, QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGraphicsOpacityEffect, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QStackedWidget,
    QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

try:
    from python_app.ai import AIError, AISettings, PROVIDERS, complete, test_connection
except ImportError:  # direct script execution
    from ai import AIError, AISettings, PROVIDERS, complete, test_connection

try:
    from python_app.analysis import analyze_python
    from python_app.js_analysis import analyze_javascript
    from python_app.compiled_analysis import analyze_compiled
    from python_app.compare import ComparePage
    from python_app.function_pov_ui import FunctionPOVPage
    from python_app.i18n import LANGUAGES as UI_LANGUAGES, set_language as _apply_ui_language, tr
except ImportError:  # running the file directly
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from python_app.analysis import analyze_python
    from python_app.js_analysis import analyze_javascript
    from python_app.compiled_analysis import analyze_compiled
    from python_app.compare import ComparePage
    from python_app.function_pov_ui import FunctionPOVPage
    from python_app.i18n import LANGUAGES as UI_LANGUAGES, set_language as _apply_ui_language, tr

APP_NAME = "Prism"
APP_TAGLINE = "Code, made clear."
LANGUAGE_LABELS = [
    ("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript"),
    ("java", "Java"), ("cpp", "C++"), ("c", "C"),
]
FILE_EXTENSIONS = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "java": ".java", "cpp": ".cpp", "c": ".c",
}
LANGUAGE_NAMES = dict(LANGUAGE_LABELS)
MAX_SOURCE = 60_000
CASES = {
    "Loop and total": """prices = [12, 8, 25]
total = 0
for price in prices:
    if price >= 10:
        total += price
print(total)
""",
    "Discount helper": """def apply_discount(price, is_member):
    if is_member:
        return price * 0.9
    return price

prices = [12, 8, 25]
total = 0
for price in prices:
    total += apply_discount(price, True)
print("Total:", total)
""",
    "Scores and counters": """scores = [72, 88, 91, 65]
passed = 0
for score in scores:
    if score >= 70:
        passed += 1
print(f"Passed: {passed}")
""",
}
JS_CASES = {
    "Loop and total": """const prices = [12, 8, 25];
let total = 0;
for (const price of prices) {
  if (price >= 10) {
    total += price;
  }
}
console.log(total);
""",
    "Discount helper": """function applyDiscount(price, isMember) {
  if (isMember) {
    return price * 0.9;
  }
  return price;
}
const total = applyDiscount(40, true);
console.log("Total:", total);
""",
    "Scores and counters": """const scores = [72, 88, 91, 65];
let passed = 0;
for (const score of scores) {
  if (score >= 70) {
    passed += 1;
  }
}
console.log("Passed:", passed);
""",
}
COMPILED_CASES = {
    "java": {
        "Loop and total": """public class Main {
    public static void main(String[] args) {
        int[] prices = {12, 8, 25};
        int total = 0;
        for (int price : prices) {
            if (price >= 10) {
                total += price;
            }
        }
        System.out.println(total);
    }
}
""",
    },
    "cpp": {
        "Loop and total": """#include <iostream>
using namespace std;

int main() {
    int prices[] = {12, 8, 25};
    int total = 0;
    for (int price : prices) {
        if (price >= 10) {
            total += price;
        }
    }
    cout << total << endl;
    return 0;
}
""",
    },
    "c": {
        "Loop and total": """#include <stdio.h>

int main() {
    int prices[] = {12, 8, 25};
    int total = 0;
    for (int i = 0; i < 3; i++) {
        if (prices[i] >= 10) {
            total += prices[i];
        }
    }
    printf("%d\\n", total);
    return 0;
}
""",
    },
}

STYLE = """
* { font-family: "Segoe UI", "Noto Sans", sans-serif; font-size: 10pt; }
QWidget { background: #1b1d21; color: #e5e8ec; }
QLabel { background: transparent; }
QFrame#TopBar { background: #202227; border-bottom: 1px solid #34383f; }
QFrame#Card { background: #23262b; border: 1px solid #363a41; border-radius: 10px; }
QLabel#Brand { font-size: 15pt; font-weight: 700; color: #ffffff; }
QLabel#Muted { color: #9aa2ad; }
QLabel#Tiny { color: #8d96a1; font-size: 9pt; }
QLabel#Title { font-size: 29pt; font-weight: 700; color: #f4f5f6; }
QLabel#Subtitle { color: #aab2bd; font-size: 11pt; }
QLabel#CardTitle { font-size: 13pt; font-weight: 600; color: #f2f3f5; }
QLabel#Kicker { color: #ff8d6f; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
QLabel#Feature { color: #c4cad2; padding: 5px 0; }
QLabel#Step { color: #ff8d6f; font-weight: 700; font-size: 9pt; }
QPushButton {
  background: #2b2f36; border: 1px solid #41464f; border-radius: 6px;
  color: #e9ecf0; padding: 7px 14px;
}
QPushButton:hover { background: #343941; border-color: #59606b; }
QPushButton:pressed { background: #262a31; }
QPushButton#Primary {
  background: #ff7852; border-color: #ff7852; color: #201310; font-weight: 600;
}
QPushButton#Primary:hover { background: #ff8d6c; }
QPushButton#Ghost { background: transparent; border-color: transparent; color: #b8c0ca; }
QPushButton#Ghost:hover { background: #2b2f36; color: #fff; }
QPushButton#Chip { background: #252930; border-color: #353a42; color: #b8c0ca; padding: 6px 10px; }
QPushButton#Chip:hover { border-color: #ff7852; color: #fff; }
QPlainTextEdit {
  background: #17191d; border: 1px solid #34383f; border-radius: 7px;
  color: #dfe4ea; selection-background-color: #5a3529;
  font-family: "Cascadia Code", "Consolas", monospace; font-size: 10.5pt;
}
QPlainTextEdit#ReadOnly { background: #181a1e; }
QTextBrowser { background: #1c1f24; border: 1px solid #34383f; border-radius: 7px; padding: 7px; }
QTabWidget::pane { border: 1px solid #34383f; border-radius: 7px; background: #1c1f24; top: -1px; }
QTabBar::tab {
  background: transparent; color: #98a1ac; padding: 8px 14px;
  border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #fff; border-bottom-color: #ff7852; }
QTabBar::tab:hover { color: #e8ecf1; }
QTreeWidget, QTableWidget, QListWidget {
  background: #1c1f24; border: 1px solid #34383f; border-radius: 7px;
  alternate-background-color: #202329; color: #dfe4ea;
}
QTreeWidget::item, QListWidget::item { padding: 5px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #493027; color: #fff; }
QHeaderView::section { background: #24272d; color: #9ea7b2; border: 0; padding: 6px; }
QScrollBar:vertical { background: #1b1d21; width: 10px; }
QScrollBar::handle:vertical { background: #424750; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #2b2e34; width: 2px; }
QStatusBar { background: #202227; color: #98a1ac; border-top: 1px solid #34383f; }
QMenuBar { background: #202227; color: #dfe4ea; }
QMenuBar::item:selected { background: #343941; }
QMenu { background: #25282e; border: 1px solid #3b4048; color: #e7eaee; }
QMenu::item:selected { background: #493027; }
QMessageBox { background: #23262b; }
"""


def fade_in(widget: QWidget, duration: int = 220) -> None:
    """Fade a widget without changing its layout or visibility."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    def cleanup() -> None:
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
    animation.finished.connect(cleanup)
    widget._prism_fade_animation = animation
    animation.start()


class PreviewArt(QWidget):
    """Small living illustration for the welcome page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(360, 166)
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(45)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self) -> None:
        self.phase = (self.phase + 0.045) % 6.283
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#363b43"), 1))
        painter.setBrush(QColor("#1f2227"))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        glow = QRadialGradient(300, 20, 170)
        glow.setColorAt(0.0, QColor(255, 120, 82, 42))
        glow.setColorAt(1.0, QColor(255, 120, 82, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        painter.setPen(QColor("#8d96a1"))
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.DemiBold))
        painter.drawText(18, 22, "LIVE STRUCTURE")

        nodes = [
            ("FLOW", 30, 54, "#ff8d6f"),
            ("TREE", 180, 40, "#c49a63"),
            ("TRACE", 232, 104, "#6ca7c9"),
            ("DATA", 64, 108, "#a9c68c"),
        ]
        for i in range(len(nodes) - 1):
            x1, y1 = nodes[i][1] + 42, nodes[i][2] + 15
            x2, y2 = nodes[i + 1][1] + 42, nodes[i + 1][2] + 15
            painter.setPen(QPen(QColor(255, 120, 82, 55), 1))
            painter.drawLine(x1, y1, x2, y2)
        for index, (label, x, y, color) in enumerate(nodes):
            float_y = int(3 * math.sin(self.phase + index * 1.7))
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(QColor("#20242a"))
            painter.drawRoundedRect(x, y + float_y, 86, 30, 5, 5)
            painter.setPen(QColor(color))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.DemiBold))
            painter.drawText(x + 10, y + 19 + float_y, label)
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x + 69, y + 12 + float_y, 5, 5)


class CodeHighlighter(QSyntaxHighlighter):
    def __init__(self, document, language: str = "python"):
        super().__init__(document)
        self.language = language
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        keyword = QTextCharFormat()
        keyword.setForeground(QColor("#ff9a7d"))
        keyword.setFontWeight(QFont.Weight.DemiBold)
        python_words = (
            "False", "None", "True", "and", "as", "assert", "async", "await",
            "break", "class", "continue", "def", "del", "elif", "else", "except",
            "finally", "for", "from", "global", "if", "import", "in", "is",
            "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
            "while", "with", "yield",
        )
        js_words = (
            "async", "await", "break", "case", "catch", "class", "const",
            "continue", "default", "delete", "do", "else", "export", "extends",
            "false", "finally", "for", "from", "function", "if", "import", "in",
            "instanceof", "let", "new", "null", "of", "return", "static", "super",
            "switch", "this", "throw", "true", "try", "typeof", "undefined", "var",
            "void", "while", "yield", "interface", "type", "implements", "private",
            "public", "protected", "readonly", "as", "enum", "namespace", "declare",
        )
        for word in (python_words if language == "python" else js_words):
            self.rules.append((QRegularExpression(rf"\b{word}\b"), keyword))
        if language in {"java", "cpp", "c"}:
            for word in ("abstract", "boolean", "char", "double", "float", "int", "long",
                         "short", "void", "volatile", "transient", "native", "synchronized",
                         "include", "define", "struct", "union", "typedef", "sizeof"):
                self.rules.append((QRegularExpression(rf"\b{word}\b"), keyword))
        number = QTextCharFormat()
        number.setForeground(QColor("#d8b87a"))
        self.rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), number))
        string = QTextCharFormat()
        string.setForeground(QColor("#a8c68f"))
        self.rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), string))
        self.rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), string))
        comment = QTextCharFormat()
        comment.setForeground(QColor("#75808c"))
        comment.setFontItalic(True)
        comment_pattern = r"#[^\n]*" if language == "python" else r"//[^\n]*"
        self.rules.append((QRegularExpression(comment_pattern), comment))
        builtin = QTextCharFormat()
        builtin.setForeground(QColor("#82b7d8"))
        builtins = ("print", "len", "range", "int", "str", "float", "list", "dict", "sum", "min", "max") if language == "python" else ("console", "Math", "JSON", "parseInt", "parseFloat", "String", "Number", "Array", "Object")
        for word in builtins:
            self.rules.append((QRegularExpression(rf"\b{word}\b"), builtin))

    def highlightBlock(self, text: str) -> None:
        for expression, fmt in self.rules:
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None, language: str = "python"):
        super().__init__(parent)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(10)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.language = language
        self.highlighter = CodeHighlighter(self.document(), language)
        self.setPlaceholderText("Write code here…")

    def set_language(self, language: str) -> None:
        if language == self.language:
            return
        self.language = language
        self.highlighter = CodeHighlighter(self.document(), language)


def format_value(value) -> str:
    text = str(value)
    return text if len(text) <= 90 else text[:87] + "…"


def guide_html(guide: dict, analysis: dict, ai_text: str | None = None) -> str:
    def esc(text):
        return html.escape(str(text)).replace("`", "").replace("**", "")

    parts = [f"<h1>{esc(guide.get('headline', 'How this program works'))}</h1>"]
    parts.append(f"<p style='color:#b9c1cb'>{esc(guide.get('summary', ''))}</p>")
    mental = guide.get("overview", {}).get("mentalModel", {})
    if mental:
        parts.append(f"<h2>Mental model</h2><p><b>{esc(mental.get('title', ''))}</b><br>{esc(mental.get('body', ''))}</p>")
    parts.append("<h2>Overview</h2>")
    for paragraph in guide.get("overview", {}).get("paragraphs", []):
        parts.append(f"<p>{esc(paragraph)}</p>")
    walkthrough = guide.get("walkthrough", [])
    if walkthrough:
        parts.append("<h2>How it runs</h2>")
        for item in walkthrough:
            points = "".join(f"<li>{esc(point)}</li>" for point in item.get("points", []))
            parts.append(
                f"<h3>{esc(item.get('title', ''))}</h3>"
                f"<p>{esc(item.get('body', ''))}</p>"
                + (f"<ul>{points}</ul>" if points else "")
            )
    notes = guide.get("lineNotes", [])
    if notes:
        parts.append("<h2>Line by line</h2>")
        for note in notes:
            parts.append(
                f"<p><b>Line {note.get('line', '?')}</b> "
                f"<code style='color:#ffb59f'>{esc(note.get('code', ''))}</code><br>"
                f"{esc(note.get('note', ''))}</p>"
            )
    concepts = guide.get("concepts", [])
    if concepts:
        parts.append("<h2>Concepts</h2>")
        for concept in concepts:
            parts.append(
                f"<p><b>{esc(concept.get('term', ''))}</b><br>"
                f"{esc(concept.get('definition', ''))}<br>"
                f"<span style='color:#aab3be'>{esc(concept.get('inThisCode', ''))}</span></p>"
            )
    watch_outs = guide.get("watchOuts", [])
    if watch_outs:
        parts.append("<h2>Watch out for</h2>")
        for item in watch_outs:
            parts.append(f"<p><b>{esc(item.get('title', ''))}</b><br>{esc(item.get('body', ''))}</p>")
    quiz = guide.get("quiz", [])
    if quiz:
        parts.append("<h2>Quick check</h2>")
        for item in quiz:
            parts.append(f"<p><b>{esc(item.get('question', ''))}</b><br>{esc(item.get('answer', ''))}</p>")
    if ai_text:
        parts.append("<h2>AI explanation</h2>")
        for paragraph in str(ai_text).split("\n\n"):
            if paragraph.strip():
                parts.append(f"<p>{esc(paragraph.strip())}</p>")
    parts.append("<hr><p style='color:#8d96a1'>Generated locally by the Python analysis engine.</p>")
    return "".join(parts)


class FlowchartView(QGraphicsView):
    """A readable top-down flow outline rendered entirely with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor("#1c1f24"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._fit_scene)

    def set_analysis(self, analysis: dict, trace: dict | None = None) -> None:
        self._scene.clear()
        self._trace = trace
        self._animation_groups = []
        y = 18
        x = 18
        entry = analysis.get("entry") or {}
        focus = entry.get("node") if entry.get("kind") == "function" and entry.get("node") else analysis.get("root")
        self._column(x, y, analysis, focus)
        self._schedule_fit()
        QTimer.singleShot(20, self._animate_items)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._schedule_fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._schedule_fit()

    def _schedule_fit(self) -> None:
        if self.isVisible() and self.viewport().width() > 0 and self.viewport().height() > 0:
            self._fit_timer.start(0)

    def _fit_scene(self) -> None:
        if not self.isVisible() or self.viewport().width() <= 0 or self.viewport().height() <= 0:
            return
        bounds = self._scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        self.fitInView(
            bounds.adjusted(-20, -20, 20, 20),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _animate_items(self) -> None:
        items = sorted(self._scene.items(), key=lambda item: item.sceneBoundingRect().top())
        for index, item in enumerate(items[:70]):
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(0.0)
            item.setGraphicsEffect(effect)
            fade = QPropertyAnimation(effect, b"opacity", self)
            fade.setDuration(260)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            group = QParallelAnimationGroup(self)
            group.addAnimation(QPauseAnimation(index * 22))
            group.addAnimation(fade)
            group.start()
            self._animation_groups.append(group)

    def _text(self, text: str, max_len: int = 56) -> str:
        text = " ".join(str(text).split())
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    def _box(self, x, y, width, height, title, body="", accent="#ff7852", dashed=False):
        pen = QPen(QColor(accent if dashed else "#464c56"))
        pen.setWidthF(1.2)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        rect = self._scene.addRect(x, y, width, height, pen, QColor("#252930"))
        rect.setZValue(1)
        tag = self._scene.addSimpleText(self._text(title, 34))
        tag.setBrush(QColor(accent if dashed else "#aeb7c1"))
        tag.setFont(QFont("Segoe UI", 7, QFont.Weight.DemiBold))
        tag.setPos(x + 14, y + 10)
        tag.setZValue(2)
        if body:
            line = self._scene.addSimpleText(self._text(body))
            line.setBrush(QColor("#e9edf2"))
            line.setFont(QFont("Cascadia Code", 9))
            line.setPos(x + 14, y + 29)
            line.setZValue(2)
        return (x + width / 2, y + height)

    def _arrow(self, start, end, dashed=False):
        pen = QPen(QColor("#5d6672"))
        pen.setWidthF(1.3)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        self._scene.addLine(start[0], start[1], end[0], end[1], pen)
        self._scene.addEllipse(end[0] - 2, end[1] - 2, 4, 4, pen, QColor("#5d6672"))

    def _column(self, x: int, y: int, analysis: dict, focus: dict | None = None) -> int:
        width = 370
        language_name = analysis.get("language", {}).get("name", "Program")
        body = (focus or {}).get("body") if focus and focus.get("type") == "function" else analysis["root"].get("body")
        self._box(x, y, width, 48, "START", f"{language_name} program", "#ff7852")
        previous_exit = (x + width / 2, y + 48)
        y += 68
        y = self._sequence((body or {}).get("children", []), x, y, width, previous_exit)
        if (body or {}).get("children"):
            previous_exit = (x + width / 2, y - 25)
        trace = self._trace
        messages = []
        if trace is None:
            messages.append("Program finished")
        elif not trace.get("complete"):
            messages.append(tr("Simulation incomplete"))
            messages.append(str((trace.get("warnings") or [trace.get("stoppedReason", "")])[-1]))
        elif not trace.get("output") and not trace.get("lastTopLevelReturn"):
            messages.append(tr("Completed · no output"))
        output = trace.get("output", "") if trace else ""
        if output:
            label = tr("Output") if trace.get("complete") else tr("Partial output")
            lines = output.splitlines() or [output]
            messages.append(label + ": " + lines[0])
            if len(lines) > 1:
                messages.append(lines[1] + (" …" if len(lines) > 2 else ""))
        result = trace.get("lastTopLevelReturn") if trace and trace.get("complete") else None
        if result:
            lines = str(result["value"]).splitlines() or [""]
            messages.append(tr("Return") + ": " + result["name"] + " → " + lines[0])
            if len(lines) > 1:
                messages.append(lines[1] + (" …" if len(lines) > 2 else ""))
        height = 40 + len(messages) * 17
        self._arrow(previous_exit, (x + width / 2, y))
        self._box(x, y, width, height, "END", "", "#ff7852")
        for index, message in enumerate(messages):
            line = self._scene.addSimpleText(self._text(message, 48))
            line.setBrush(QColor("#e9edf2"))
            line.setFont(QFont("Cascadia Code", 9))
            line.setPos(x + 14, y + 29 + index * 17)
            line.setZValue(2)
        return y + height

    def _sequence(self, nodes, x, y, width, previous_exit):
        for node in nodes:
            kind = node.get("type")
            if kind in {"function", "class"}:
                continue
            before = y
            self._arrow(previous_exit, (x + width / 2, y))
            if kind in {"for", "while"}:
                previous_exit = self._box(x, y, width, 48, "LOOP", node.get("header", "loop"), "#d7a84d")
                y = previous_exit[1] + 18
                y = self._sequence(node.get("body", {}).get("children", []), x + 34, y, width - 34, previous_exit)
                if node.get("alternate"):
                    y = self._sequence(node["alternate"].get("children", []), x + 34, y, width - 34, (x + width / 2, y))
                y += 22
                previous_exit = (x + width / 2, y)
            elif kind == "if":
                previous_exit = self._box(x, y, width, 48, "IF", node.get("condition", "condition"), "#d7a84d")
                y = previous_exit[1] + 16
                y = self._sequence(node.get("consequent", {}).get("children", []), x + 34, y, width - 34, previous_exit)
                alternate = node.get("alternate")
                if alternate and alternate.get("children"):
                    self._arrow((x + width / 2, y), (x + width / 2 + 22, y))
                    y = self._sequence(alternate.get("children", []), x + 56, y + 18, width - 56, (x + width / 2, y))
                y += 12
                previous_exit = (x + width / 2, y)
            elif kind == "action":
                action = node.get("action") or {}
                subtype = action.get("subtype", "statement")
                accent = "#ff8d6f" if subtype in {"return", "break", "continue"} else "#5d6672"
                previous_exit = self._box(x, y, width, 54, subtype.upper(), node.get("text", ""), accent)
                y = previous_exit[1]
            else:
                previous_exit = self._box(x, y, width, 50, str(kind).upper(), node.get("header", ""))
                y = previous_exit[1]
            y += 25
            if y <= before:
                break
        return y


class SyntaxTreeView(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Structure", "Line"])
        self.setAlternatingRowColors(True)
        self.setColumnWidth(0, 350)
        self.setAnimated(True)

    def set_analysis(self, analysis: dict) -> None:
        self.clear()
        root = QTreeWidgetItem(["Program", str(analysis.get("lineCount", ""))])
        self.addTopLevelItem(root)
        self._add_nodes(analysis["root"]["body"].get("children", []), root)
        root.setExpanded(True)

    def _add_nodes(self, nodes, parent):
        for node in nodes:
            kind = node.get("type")
            label = node.get("name") or node.get("header") or node.get("text") or kind
            item = QTreeWidgetItem([str(kind).title(), str(node.get("startLine", ""))])
            item.setToolTip(0, str(label))
            parent.addChild(item)
            if kind in {"function", "class", "if", "for", "while"}:
                body = node.get("body") or node.get("consequent")
                if body:
                    self._add_nodes(body.get("children", []), item)
                alternate = node.get("alternate")
                if alternate:
                    alt = QTreeWidgetItem(["Else", str(alternate.get("startLine", ""))])
                    item.addChild(alt)
                    self._add_nodes(alternate.get("children", []), alt)
                item.setExpanded(True)


class TraceView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.steps = QListWidget()
        self.steps.setMinimumWidth(220)
        self.steps.currentRowChanged.connect(self.show_step)
        split.addWidget(self.steps)
        self.detail = QTextBrowser()
        split.addWidget(self.detail)
        split.setSizes([260, 620])
        layout.addWidget(split, 1)
        controls = QHBoxLayout()
        self.prev = QPushButton("Previous")
        self.next = QPushButton("Next")
        self.play = QPushButton("Play")
        self.prev.clicked.connect(lambda: self.move(-1))
        self.next.clicked.connect(lambda: self.move(1))
        self.play.clicked.connect(self.toggle_play)
        controls.addWidget(self.prev)
        controls.addWidget(self.next)
        controls.addWidget(self.play)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.timer = QTimer(self)
        self.timer.setInterval(750)
        self.timer.timeout.connect(lambda: self.move(1))
        self.items: list[dict] = []
        self.trace = {}

    def set_trace(self, trace: dict) -> None:
        self.trace = trace
        self.timer.stop()
        self.play.setText("Play")
        self.steps.clear()
        self.items = trace.get("steps", [])
        self.play.setEnabled(len(self.items) > 1)
        for step in self.items:
            item = QListWidgetItem(f"L{step.get('line', '?')} · {step.get('title', 'Step')}")
            self.steps.addItem(item)
        if self.items:
            self.steps.setCurrentRow(0)
        else:
            self.detail.setHtml("<p style='color:#9aa2ad'>No trace steps were recorded.</p>")

    def show_step(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return
        step = self.items[index]
        variables = "".join(
            f"<tr><td style='color:#b8c0ca'>{html.escape(str(v.get('name', '')))}</td>"
            f"<td style='color:#f0c48a'>{html.escape(format_value(v.get('display', '')))}</td></tr>"
            for v in step.get("vars", [])
        )
        output = html.escape(step.get("output", "")).replace("\n", "<br>") or "—"
        self.detail.setHtml(
            f"<h2 style='color:#f1f3f5'>{html.escape(step.get('title', 'Step'))}</h2>"
            f"<p style='color:#aab2bd'>Line {step.get('line', '?')} · {html.escape(step.get('scope', 'Global'))}</p>"
            f"<p>{html.escape(step.get('detail', ''))}</p>"
            f"<h3>Variables</h3><table>{variables or '<tr><td>No variables yet.</td></tr>'}</table>"
            f"<h3>Output</h3><pre style='color:#c8d2b5'>{output}</pre>"
            + ("<p>" + html.escape("; ".join(self.trace.get("warnings", []))) + "</p>" if not self.trace.get("complete", True) else "")
        )
        self.prev.setEnabled(index > 0)
        self.next.setEnabled(index + 1 < len(self.items))
        fade_in(self.detail, 160)

    def move(self, delta: int) -> None:
        index = self.steps.currentRow() + delta
        if 0 <= index < len(self.items):
            self.steps.setCurrentRow(index)
        if self.steps.currentRow() >= len(self.items) - 1:
            self.timer.stop()
            self.play.setText("Play")

    def toggle_play(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.play.setText("Play")
        else:
            if self.steps.currentRow() >= len(self.items) - 1:
                self.steps.setCurrentRow(0)
            self.timer.start()
            self.play.setText("Pause")


class DataFlowView(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Line", "Target", "Expression / value", "Depends on", "Scope"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setColumnWidth(0, 60)
        self.setColumnWidth(1, 140)
        self.setColumnWidth(2, 260)
        self.setColumnWidth(3, 180)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def set_analysis(self, analysis: dict, trace: dict) -> None:
        rows = []
        seen = set()
        for event in trace.get("events", []):
            if event.get("kind") != "assignment":
                continue
            key = (event.get("line"), event.get("target"))
            if key in seen:
                continue
            seen.add(key)
            rows.append((
                event.get("line", ""), event.get("target", ""),
                f"{event.get('expressionText') or ''} → {event.get('value', '')}",
                ", ".join(event.get("dependencies", []) or []),
                event.get("scope", "Global"),
            ))
        if not rows:
            for assignment in analysis.get("assignments", []):
                rows.append((
                    assignment.get("line", ""), assignment.get("target", ""),
                    f"{assignment.get('expressionText', '')}",
                    ", ".join(assignment.get("dependencies", []) or []),
                    assignment.get("scope", "Global"),
                ))
        self.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.setItem(row, column, QTableWidgetItem(format_value(value)))
        self.resizeRowsToContents()


class AIWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job

    def run(self) -> None:
        try:
            self.succeeded.emit(self.job())
        except AIError as error:
            self.failed.emit(str(error))
        except Exception as error:  # pragma: no cover - network boundary
            self.failed.emit(str(error))


class AISettingsDialog(QDialog):
    def __init__(self, settings: AISettings, remember: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect AI")
        self.setMinimumWidth(540)
        self.settings = settings
        self.remember_value = remember
        self.worker = None
        layout = QVBoxLayout(self)
        title = QLabel("Connect your AI")
        title.setObjectName("Title")
        title.setStyleSheet("font-size: 20pt;")
        layout.addWidget(title)
        description = QLabel(
            "Optional. The local guide always works without AI. A request is sent only when you test or enhance."
        )
        description.setObjectName("Muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self.provider = QComboBox()
        for key, item in PROVIDERS.items():
            self.provider.addItem(item["name"], key)
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.provider)))
        form.addRow("Provider", self.provider)
        self.base_url = QLineEdit(settings.base_url)
        form.addRow("Base URL", self.base_url)
        self.model = QLineEdit(settings.model)
        form.addRow("Model", self.model)
        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Optional for local compatible servers")
        form.addRow("API key", self.api_key)
        layout.addLayout(form)

        self.remember = QCheckBox("Remember the key on this device")
        self.remember.setChecked(remember)
        layout.addWidget(self.remember)
        note = QLabel("The key is sent only to the provider for the request you start. It is never logged.")
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.test = QPushButton("Test connection")
        self.test.clicked.connect(self.test_ai)
        buttons.addWidget(self.test)
        buttons.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.save)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)
        layout.addLayout(buttons)
        self.provider.currentIndexChanged.connect(self.provider_changed)

    def provider_changed(self) -> None:
        key = self.provider.currentData()
        defaults = PROVIDERS.get(key)
        if not defaults:
            return
        if not self.base_url.text().strip() or self.base_url.text().strip() in {
            item["base"] for item in PROVIDERS.values()
        }:
            self.base_url.setText(defaults["base"])
        if not self.model.text().strip() or self.model.text().strip() in {
            item["model"] for item in PROVIDERS.values()
        }:
            self.model.setText(defaults["model"])

    def current_settings(self) -> AISettings:
        return AISettings(
            provider=self.provider.currentData(),
            base_url=self.base_url.text().strip(),
            model=self.model.text().strip(),
            api_key=self.api_key.text(),
        )

    def test_ai(self) -> None:
        settings = self.current_settings()
        self.test.setEnabled(False)
        self.status.setText("Testing connection…")
        self.worker = AIWorker(lambda: test_connection(settings), self)
        self.worker.succeeded.connect(lambda text: self._test_done(text, None))
        self.worker.failed.connect(lambda error: self._test_done("", error))
        self.worker.start()

    def _test_done(self, text: str, error: str | None) -> None:
        self.test.setEnabled(True)
        if error:
            self.status.setText(f"Connection failed: {error}")
        else:
            self.status.setText(f"Connected. Provider replied: {text.strip()[:80]}")

    def save(self) -> None:
        settings = self.current_settings()
        if not settings.base_url or not settings.model:
            self.status.setText("Base URL and model are required.")
            return
        self.settings = settings
        self.remember_value = self.remember.isChecked()
        self.accept()


class WelcomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(70, 36, 70, 36)
        outer.setSpacing(18)
        intro_row = QHBoxLayout()
        intro_row.setSpacing(24)
        intro_copy = QVBoxLayout()
        intro_copy.setSpacing(8)
        kicker = QLabel(tr("LOCAL CODE WORKSPACE"))
        kicker.setObjectName("Kicker")
        intro_copy.addWidget(kicker)
        title = QLabel(tr(APP_TAGLINE))
        title.setObjectName("Title")
        intro_copy.addWidget(title)
        subtitle = QLabel(
            tr("Write or import code. Prism explains the flow, structure, execution, "
               "and data without leaving this window.")
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(720)
        intro_copy.addWidget(subtitle)
        intro_row.addLayout(intro_copy, 1)
        self.preview = PreviewArt()
        intro_row.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(intro_row)
        self.intro_widgets = [kicker, title, subtitle, self.preview]
        self.kicker = kicker
        self.title = title
        self.subtitle = subtitle

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)
        card_title = QLabel(tr("Start an analysis"))
        card_title.setObjectName("CardTitle")
        card_layout.addWidget(card_title)
        card_sub = QLabel(
            tr("The document starts blank. Open the editor, import a source file, or try a case.")
        )
        card_sub.setObjectName("Muted")
        card_sub.setWordWrap(True)
        card_layout.addWidget(card_sub)
        language_row = QHBoxLayout()
        language_label = QLabel(tr("Language"))
        language_label.setObjectName("Muted")
        self.language = QComboBox()
        for language_id, name in LANGUAGE_LABELS:
            self.language.addItem(name, language_id)
        language_row.addWidget(language_label)
        language_row.addWidget(self.language)
        language_row.addStretch(1)
        card_layout.addLayout(language_row)
        buttons = QHBoxLayout()
        self.editor_button = QPushButton(tr("Open editor"))
        self.editor_button.setObjectName("Primary")
        self.import_button = QPushButton(tr("Import file"))
        self.example_button = QPushButton(tr("Try a case"))
        self.compare_button = QPushButton(tr("Compare versions"))
        buttons.addWidget(self.editor_button)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.example_button)
        buttons.addWidget(self.compare_button)
        buttons.addStretch(1)
        card_layout.addLayout(buttons)
        features = QLabel(
            tr("FLOWCHART   Trace decisions and loops\n"
               "SYNTAX TREE   Inspect the AST structure\n"
               "LIVE TRACE   Step through the safe run\n"
               "DATA FLOW   Follow values to their use\n"
               "GUIDE   Read the explanation beside the code")
        )
        features.setObjectName("Feature")
        features.setWordWrap(True)
        card_layout.addWidget(features)
        outer.addWidget(card)
        outer.addStretch(1)
        footnote = QLabel(
            tr("Local only · Python · JavaScript · TypeScript · Java · C++ · C")
        )
        footnote.setObjectName("Tiny")
        outer.addWidget(footnote)

        self.card_title = card_title
        self.card_sub = card_sub
        self.language_label = language_label
        self.features = features
        self.footnote = footnote

    def retranslate(self) -> None:
        self.kicker.setText(tr("LOCAL CODE WORKSPACE"))
        self.title.setText(tr(APP_TAGLINE))
        self.subtitle.setText(
            tr("Write or import code. Prism explains the flow, structure, execution, "
               "and data without leaving this window.")
        )
        self.card_title.setText(tr("Start an analysis"))
        self.card_sub.setText(
            tr("The document starts blank. Open the editor, import a source file, or try a case.")
        )
        self.language_label.setText(tr("Language"))
        self.editor_button.setText(tr("Open editor"))
        self.import_button.setText(tr("Import file"))
        self.example_button.setText(tr("Try a case"))
        self.compare_button.setText(tr("Compare versions"))
        self.features.setText(
            tr("FLOWCHART   Trace decisions and loops\n"
               "SYNTAX TREE   Inspect the AST structure\n"
               "LIVE TRACE   Step through the safe run\n"
               "DATA FLOW   Follow values to their use\n"
               "GUIDE   Read the explanation beside the code")
        )
        self.footnote.setText(
            tr("Local only · Python · JavaScript · TypeScript · Java · C++ · C")
        )

    def play_intro(self) -> None:
        for index, widget in enumerate(self.intro_widgets):
            QTimer.singleShot(index * 55, lambda w=widget: fade_in(w, 360))


class EditorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)
        head = QHBoxLayout()
        self.back = QPushButton(tr("← Welcome"))
        self.back.setObjectName("Ghost")
        head.addWidget(self.back)
        self.file_label = QLabel("main.py")
        self.file_label.setObjectName("CardTitle")
        head.addWidget(self.file_label)
        head.addStretch(1)
        self.import_button = QPushButton(tr("Import"))
        self.clear_button = QPushButton(tr("Clear"))
        head.addWidget(self.import_button)
        head.addWidget(self.clear_button)
        layout.addLayout(head)
        self.editor = CodeEditor()
        self.editor.setPlaceholderText(tr("Write Python code here…"))
        layout.addWidget(self.editor, 1)
        foot = QHBoxLayout()
        self.meta = QLabel(tr("Blank document"))
        self.meta.setObjectName("Tiny")
        foot.addWidget(self.meta)
        foot.addStretch(1)
        self.analyze = QPushButton(tr("Visualize & explain"))
        self.analyze.setObjectName("Primary")
        foot.addWidget(self.analyze)
        layout.addLayout(foot)

    def retranslate(self) -> None:
        self.back.setText(tr("← Welcome"))
        self.import_button.setText(tr("Import"))
        self.clear_button.setText(tr("Clear"))
        self.editor.setPlaceholderText(tr("Write Python code here…"))
        if self.meta.text().strip() in ("Blank document", ""):
            self.meta.setText(tr("Blank document"))
        self.analyze.setText(tr("Visualize & explain"))


class ResultsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.guide = None
        self.trace = None
        self.analysis = None
        self.language = "python"
        self.function_pov_supported = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        head = QHBoxLayout()
        self.back = QPushButton(tr("← Welcome"))
        self.back.setObjectName("Ghost")
        head.addWidget(self.back)
        self.file_label = QLabel("main.py")
        self.file_label.setObjectName("CardTitle")
        head.addWidget(self.file_label)
        self.summary = QLabel("")
        self.summary.setObjectName("Tiny")
        head.addWidget(self.summary)
        head.addStretch(1)
        self.ai_button = QPushButton(tr("Enhance guide"))
        self.edit = QPushButton(tr("Edit code"))
        self.export = QPushButton(tr("Save guide"))
        self.function_pov_button = QPushButton(tr("Function POV"))
        self.function_pov_button.setEnabled(False)
        self.function_pov_button.setVisible(False)
        self.function_pov_button.setToolTip(tr("Function POV currently supports Python only."))
        head.addWidget(self.function_pov_button)
        head.addWidget(self.ai_button)
        head.addWidget(self.edit)
        head.addWidget(self.export)
        layout.addLayout(head)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setObjectName("ReadOnly")
        self.source.setMinimumWidth(260)
        self.source_highlighter = CodeHighlighter(self.source.document(), "python")
        split.addWidget(self.source)
        self.tabs = QTabWidget()
        self.flow = FlowchartView()
        self.tree = SyntaxTreeView()
        self.trace_view = TraceView()
        self.data = DataFlowView()
        self.guide_view = QTextBrowser()
        self.tabs.addTab(self.flow, tr("Flowchart"))
        self.tabs.addTab(self.tree, tr("Syntax Tree"))
        self.tabs.addTab(self.trace_view, tr("Live Trace"))
        self.tabs.addTab(self.data, tr("Data Flow"))
        self.tabs.addTab(self.guide_view, tr("Guide"))
        self.tabs.currentChanged.connect(self._tab_changed)
        split.addWidget(self.tabs)
        split.setSizes([320, 940])
        layout.addWidget(split, 1)

    def retranslate(self) -> None:
        self.back.setText(tr("← Welcome"))
        self.ai_button.setText(tr("Enhance guide"))
        self.edit.setText(tr("Edit code"))
        self.export.setText(tr("Save guide"))
        self.function_pov_button.setText(tr("Function POV"))
        self.function_pov_button.setToolTip(
            tr("Function POV is available for this Python analysis.")
            if self.function_pov_supported
            else tr("Open Function POV to see language support.")
        )
        self.tabs.setTabText(0, tr("Flowchart"))
        self.tabs.setTabText(1, tr("Syntax Tree"))
        self.tabs.setTabText(2, tr("Live Trace"))
        self.tabs.setTabText(3, tr("Data Flow"))
        self.tabs.setTabText(4, tr("Guide"))
        if self.analysis:
            self.flow.set_analysis(self.analysis, self.trace if self.language == "python" else None)

    def _tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is not None:
            fade_in(widget, 180)

    def set_result(self, result: dict, filename: str, language: str = "python") -> None:
        self.analysis = result["analysis"]
        self.trace = result["trace"]
        self.guide = result["guide"]
        self.ai_text = ""
        self.language = language
        self.function_pov_supported = language == "python"
        self.function_pov_button.setVisible(self.function_pov_supported)
        self.function_pov_button.setEnabled(self.function_pov_supported)
        self.function_pov_button.setToolTip(
            tr("Function POV is available for this Python analysis.")
            if self.function_pov_supported
            else tr("Open Function POV to see language support.")
        )
        self.file_label.setText(filename)
        language_name = LANGUAGE_NAMES.get(language, language.title())
        self.summary.setText(
            f"{language_name} · {self.analysis['lineCount']} lines · "
            f"{len(self.trace.get('steps', []))} trace steps"
        )
        self.source_highlighter = CodeHighlighter(self.source.document(), language)
        self.source.setPlainText(self.analysis.get("source", ""))
        self.flow.set_analysis(self.analysis, self.trace if language == "python" else None)
        self.tree.set_analysis(self.analysis)
        self.trace_view.set_trace(self.trace)
        self.data.set_analysis(self.analysis, self.trace)
        self.guide_view.setHtml(guide_html(self.guide, self.analysis, self.ai_text))
        self.tabs.setCurrentIndex(0)

    def set_ai_text(self, text: str) -> None:
        self.ai_text = text
        if self.guide:
            self.guide_view.setHtml(guide_html(self.guide, self.analysis, self.ai_text))
            self.tabs.setCurrentIndex(4)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Prism", "Prism Native")
        saved_language = str(self.settings.value("ui/language", "en"))
        _apply_ui_language(saved_language)

        self.setWindowTitle(tr("Prism — code analysis workspace"))
        self.resize(1400, 900)
        self.setMinimumSize(980, 680)
        icon = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        top = QFrame()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(18, 9, 18, 9)
        brand = QLabel("prism")
        brand.setObjectName("Brand")
        top_layout.addWidget(brand)
        self.activity = QLabel(tr("CODE WORKSPACE"))
        self.activity.setObjectName("Tiny")
        top_layout.addWidget(self.activity)
        language_label = QLabel(tr("UI language"))
        language_label.setObjectName("Tiny")
        top_layout.addWidget(language_label)
        self.ui_language = QComboBox()
        for code, name in UI_LANGUAGES:
            self.ui_language.addItem(name, code)
        index = self.ui_language.findData(saved_language)
        self.ui_language.setCurrentIndex(index if index >= 0 else 0)
        self.ui_language.currentIndexChanged.connect(
            lambda _index: self.set_ui_language(self.ui_language.currentData())
        )
        top_layout.addWidget(self.ui_language)
        top_layout.addStretch(1)
        self.ai_button = QPushButton(tr("Connect AI"))
        self.ai_button.setObjectName("Chip")
        top_layout.addWidget(self.ai_button)
        self.local_label = QLabel(tr("Local · six languages"))
        self.local_label.setObjectName("Tiny")
        top_layout.addWidget(self.local_label)
        self.language_label = language_label

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(top)
        self.stack = QStackedWidget()
        self.welcome = WelcomePage()
        self.editor_page = EditorPage()
        self.results = ResultsPage()
        self.function_pov_page = FunctionPOVPage()
        self.compare_page = ComparePage()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.editor_page)
        self.stack.addWidget(self.results)
        self.stack.addWidget(self.function_pov_page)
        self.stack.addWidget(self.compare_page)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(container)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(tr("Local · Python"))

        self.current_file = "main.py"
        self.language_id = "python"
        self.ai_settings, self.remember_key, self.ai_saved = self._load_ai_settings()
        self.ai_worker = None
        self.ai_busy = False
        self._wire()
        self._menu()
        self._update_ai_button()
        self.show_welcome()

    def _wire(self):
        self.welcome.editor_button.clicked.connect(self.show_editor)
        self.welcome.import_button.clicked.connect(self.import_file)
        self.welcome.example_button.clicked.connect(self.choose_case)
        self.welcome.compare_button.clicked.connect(self.show_compare)
        self.welcome.language.currentIndexChanged.connect(
            lambda _index: self.set_language(self.welcome.language.currentData())
        )
        self.editor_page.back.clicked.connect(self.show_welcome)
        self.editor_page.import_button.clicked.connect(self.import_file)
        self.editor_page.clear_button.clicked.connect(self.clear_code)
        self.editor_page.analyze.clicked.connect(self.analyze)
        self.results.back.clicked.connect(self.show_welcome)
        self.results.edit.clicked.connect(self.show_editor)
        self.results.export.clicked.connect(self.save_guide)
        self.results.ai_button.clicked.connect(self.enhance_guide)
        self.results.function_pov_button.clicked.connect(self.open_function_pov)
        self.function_pov_page.backRequested.connect(self.show_results)
        self.compare_page.back.connect(self.show_welcome)
        self.ai_button.clicked.connect(self.open_ai_settings)

    def _menu(self):
        menu = self.menuBar().addMenu(tr("&File"))
        new_action = QAction(tr("New analysis"), self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.show_editor)
        open_action = QAction(tr("Open Python file…"), self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.import_file)
        save_action = QAction(tr("Save guide…"), self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_guide)
        quit_action = QAction(tr("Quit"), self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        menu.addActions([new_action, open_action, save_action])
        menu.addSeparator()
        menu.addAction(quit_action)
        view = self.menuBar().addMenu(tr("&View"))
        full = QAction(tr("Toggle full screen"), self)
        full.setShortcut("F11")
        full.triggered.connect(self.toggle_fullscreen)
        view.addAction(full)
        tools = self.menuBar().addMenu(tr("&Tools"))
        compare_action = QAction(tr("Compare two versions…"), self)
        compare_action.setShortcut("Ctrl+D")
        compare_action.triggered.connect(self.show_compare)
        tools.addAction(compare_action)
        tools.addSeparator()
        ai_action = QAction(tr("Connect AI…"), self)
        ai_action.triggered.connect(self.open_ai_settings)
        tools.addAction(ai_action)
        enhance_action = QAction(tr("Enhance current guide…"), self)
        enhance_action.setShortcut("Ctrl+E")
        enhance_action.triggered.connect(self.enhance_guide)
        tools.addAction(enhance_action)
        help_menu = self.menuBar().addMenu(tr("&Help"))
        about_action = QAction(tr("About Prism"), self)
        about_action.triggered.connect(self.about)
        help_menu.addAction(about_action)

        self.menus = {
            "file": (menu, "&File"),
            "view": (view, "&View"),
            "tools": (tools, "&Tools"),
            "help": (help_menu, "&Help"),
        }
        self.actions = {
            "new": (new_action, "New analysis"),
            "open": (open_action, "Open Python file…"),
            "save": (save_action, "Save guide…"),
            "quit": (quit_action, "Quit"),
            "full": (full, "Toggle full screen"),
            "compare": (compare_action, "Compare two versions…"),
            "ai": (ai_action, "Connect AI…"),
            "enhance": (enhance_action, "Enhance current guide…"),
            "about": (about_action, "About Prism"),
        }

    def retranslate(self) -> None:
        """Re-apply every string after the interface language changed."""
        self.setWindowTitle(tr("Prism — code analysis workspace"))
        self.activity.setText(tr("CODE WORKSPACE"))
        self.language_label.setText(tr("UI language"))
        self.ai_button.setText(tr("Connect AI"))
        self.local_label.setText(tr("Local · six languages"))
        for widget, key in self.menus.values():
            widget.setTitle(tr(key))
        for widget, key in self.actions.values():
            widget.setText(tr(key))
        self.welcome.retranslate()
        self.editor_page.retranslate()
        self.results.retranslate()
        self.function_pov_page.retranslate()
        self.compare_page.retranslate()
        self.statusBar().showMessage(tr("Local · Python"))

    def set_ui_language(self, code: str) -> None:
        code = code or "en"
        _apply_ui_language(code)
        self.settings.setValue("ui/language", code)
        index = self.ui_language.findData(code)
        if index >= 0 and self.ui_language.currentIndex() != index:
            self.ui_language.blockSignals(True)
            self.ui_language.setCurrentIndex(index)
            self.ui_language.blockSignals(False)
        self.retranslate()

    def show_welcome(self):
        self.stack.setCurrentWidget(self.welcome)
        fade_in(self.welcome, 220)
        self.welcome.play_intro()
        self.statusBar().showMessage(tr("Local · Python / JavaScript / TypeScript / Java / C++ / C"))

    def show_editor(self):
        self.stack.setCurrentWidget(self.editor_page)
        fade_in(self.editor_page, 200)
        self.editor_page.editor.setFocus()
        self.statusBar().showMessage(f"{self.current_file} · {LANGUAGE_NAMES[self.language_id]}")

    def show_compare(self):
        index = self.compare_page.language_box.findData(self.language_id)
        if index >= 0 and self.compare_page.language_box.currentIndex() != index:
            self.compare_page.language_box.blockSignals(True)
            self.compare_page.language_box.setCurrentIndex(index)
            self.compare_page.language_box.blockSignals(False)
            self.compare_page.language = self.language_id
        self.stack.setCurrentWidget(self.compare_page)
        fade_in(self.compare_page, 200)
        self.statusBar().showMessage(tr("Compare · structural diff between two versions"))

    def open_function_pov(self) -> None:
        if not self.results.analysis:
            return
        if self.results.function_pov_supported:
            self.function_pov_page.set_source(
                self.results.analysis.get("source", ""),
                self.results.file_label.text(),
            )
        else:
            language = LANGUAGE_NAMES.get(self.results.language, self.results.language.title())
            self.function_pov_page.set_unsupported_language(language)
        self.stack.setCurrentWidget(self.function_pov_page)
        fade_in(self.function_pov_page, 220)
        self.statusBar().showMessage(tr("Function POV · safe Python simulation"))

    def show_results(self) -> None:
        if not self.results.analysis:
            self.show_welcome()
            return
        self.stack.setCurrentWidget(self.results)
        fade_in(self.results, 180)
        self.statusBar().showMessage(
            f"{self.results.file_label.text()} · "
            f"{LANGUAGE_NAMES.get(self.results.language, self.results.language.title())}"
        )

    def set_language(self, language_id: str) -> None:
        if language_id not in LANGUAGE_NAMES:
            language_id = "python"
        self.language_id = language_id
        index = self.welcome.language.findData(language_id)
        if index >= 0 and self.welcome.language.currentIndex() != index:
            self.welcome.language.blockSignals(True)
            self.welcome.language.setCurrentIndex(index)
            self.welcome.language.blockSignals(False)
        ext = FILE_EXTENSIONS.get(language_id, ".txt")
        if not self.current_file or self.current_file in {"main.py", "main.js", "main.ts", "main.java", "main.cpp", "main.c"}:
            self.current_file = "main" + ext
        self.editor_page.file_label.setText(self.current_file)
        self.editor_page.editor.set_language(language_id)
        self.statusBar().showMessage(f"{self.current_file} · {LANGUAGE_NAMES[language_id]}")

    def _cases(self) -> dict[str, str]:
        if self.language_id == "python":
            return CASES
        if self.language_id in {"javascript", "typescript"}:
            return JS_CASES
        return COMPILED_CASES.get(self.language_id, {})

    def choose_case(self):
        menu = QMenu(self)
        for name in self._cases():
            action = menu.addAction(name)
            action.triggered.connect(lambda _=False, n=name: self.load_case(n))
        menu.exec(self.welcome.example_button.mapToGlobal(self.welcome.example_button.rect().bottomLeft()))

    def load_case(self, name: str) -> None:
        cases = self._cases()
        if name not in cases:
            return
        ext = FILE_EXTENSIONS.get(self.language_id, ".py")
        self.current_file = name.lower().replace(" ", "-") + ext
        self.editor_page.editor.set_language(self.language_id)
        self.editor_page.editor.setPlainText(cases[name])
        self.editor_page.file_label.setText(self.current_file)
        self.show_editor()

    def clear_code(self):
        self.editor_page.editor.clear()
        self.current_file = "main.py"
        self.editor_page.file_label.setText("main.py")
        self.editor_page.meta.setText(tr("Blank document"))

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Import source file"), "",
            tr("Code files") + " (*.py *.js *.jsx *.ts *.tsx *.java *.cpp *.cc *.cxx *.c *.h *.hpp);;"
            "Python (*.py);;JavaScript (*.js *.jsx);;TypeScript (*.ts *.tsx);;"
            "Java (*.java);;C/C++ (*.c *.h *.cpp *.cc *.cxx *.hpp);;" + tr("All files") + " (*)"
        )
        if not path:
            return
        try:
            data = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            QMessageBox.warning(self, tr("Could not read file"), str(error))
            return
        if len(data) > MAX_SOURCE:
            QMessageBox.warning(
                self, tr("File too large"),
                tr("Source files must stay under 60,000 characters."),
            )
            return
        suffix = Path(path).suffix.lower()
        if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
            self.set_language("javascript")
        elif suffix in {".ts", ".tsx"}:
            self.set_language("typescript")
        elif suffix == ".py":
            self.set_language("python")
        elif suffix == ".java":
            self.set_language("java")
        elif suffix in {".cpp", ".cc", ".cxx", ".hpp", ".h"}:
            self.set_language("cpp")
        elif suffix == ".c":
            self.set_language("c")
        self.current_file = Path(path).name
        self.editor_page.file_label.setText(self.current_file)
        self.editor_page.editor.setPlainText(data)
        self.editor_page.meta.setText(f"{self.current_file} · {len(data.splitlines())} lines")
        self.show_editor()

    def analyze(self):
        source = self.editor_page.editor.toPlainText()
        if not source.strip():
            QMessageBox.information(self, "Add some code", "Write or import Python code first.")
            return
        if len(source) > MAX_SOURCE:
            QMessageBox.warning(self, "Too large", "Keep the snippet under 60,000 characters.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if self.language_id == "python":
                result = analyze_python(source)
            elif self.language_id in {"javascript", "typescript"}:
                result = analyze_javascript(source, self.language_id)
            else:
                result = analyze_compiled(source, self.language_id)
        except ValueError as error:
            QMessageBox.warning(self, "Syntax error", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Analysis failed", str(error))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.results.set_result(result, self.current_file, self.language_id)
        self.stack.setCurrentWidget(self.results)
        fade_in(self.results, 220)
        self.statusBar().showMessage(
            f"{self.current_file} · {LANGUAGE_NAMES[self.language_id]} · "
            f"{result['analysis']['metrics']['codeLines']} code lines"
        )

    def _load_ai_settings(self) -> tuple[AISettings, bool, bool]:
        provider = str(self.settings.value("ai/provider", "openai"))
        if provider not in PROVIDERS:
            provider = "openai"
        remember = str(self.settings.value("ai/remember", "false")).lower() == "true"
        saved = str(self.settings.value("ai/saved", "false")).lower() == "true"
        defaults = PROVIDERS[provider]
        return (
            AISettings(
                provider=provider,
                base_url=str(self.settings.value("ai/base", defaults["base"])),
                model=str(self.settings.value("ai/model", defaults["model"])),
                api_key=str(self.settings.value("ai/key", "")) if remember else "",
            ),
            remember,
            saved,
        )

    def _save_ai_settings(self) -> None:
        settings = self.ai_settings
        self.settings.setValue("ai/provider", settings.provider)
        self.settings.setValue("ai/base", settings.base_url)
        self.settings.setValue("ai/model", settings.model)
        self.settings.setValue("ai/saved", "true")
        self.settings.setValue("ai/remember", "true" if self.remember_key else "false")
        if self.remember_key:
            self.settings.setValue("ai/key", settings.api_key)
        else:
            self.settings.remove("ai/key")
        self.settings.sync()

    def _update_ai_button(self) -> None:
        configured = self.ai_saved and self.ai_settings.configured
        self.ai_button.setText("AI ready" if configured else "Connect AI")
        self.ai_button.setToolTip(
            f"{self.ai_settings.provider_name()} · {self.ai_settings.model}"
            if configured else "Configure an optional AI provider"
        )

    def open_ai_settings(self) -> None:
        dialog = AISettingsDialog(self.ai_settings, self.remember_key, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.ai_settings = dialog.settings
        self.remember_key = dialog.remember_value
        self.ai_saved = True
        self._save_ai_settings()
        self._update_ai_button()
        self.statusBar().showMessage(
            f"AI configured · {self.ai_settings.provider_name()} · {self.ai_settings.model}"
        )

    def _ai_prompt(self) -> tuple[str, list[dict[str, str]]]:
        result = self.results
        analysis = result.analysis or {}
        guide = result.guide or {}
        trace = result.trace or {}
        source = analysis.get("source", "")
        guide_summary = guide.get("summary", "")
        concepts = ", ".join(item.get("term", "") for item in guide.get("concepts", []))
        trace_summary = "\n".join(
            f"L{step.get('line')}: {step.get('title')}" for step in trace.get("steps", [])[:18]
        )
        language_name = LANGUAGE_NAMES.get(self.language_id, "programming")
        system = (
            f"You are a patient {language_name} tutor. Explain code for a complete beginner. "
            "Be concrete, refer to line numbers, and do not invent execution values."
        )
        user = (
            f"Explain this {language_name} program in 3-5 short paragraphs for a beginner.\n"
            "Cover: what it does, the key control flow, and one likely mistake.\n\n"
            f"Source:\n```{self.language_id}\n{source}\n```\n\n"
            f"Local summary: {guide_summary}\n"
            f"Concepts: {concepts}\n"
            f"Trace (selected):\n{trace_summary}\n\n"
            "Return plain prose with no code fences."
        )
        return system, [{"role": "user", "content": user}]

    def enhance_guide(self) -> None:
        if not self.results.guide:
            QMessageBox.information(self, "No guide yet", "Run an analysis first.")
            return
        if not self.ai_saved or not self.ai_settings.configured:
            self.open_ai_settings()
            if not self.ai_saved or not self.ai_settings.configured:
                return
        if self.ai_busy:
            return
        self.ai_busy = True
        self.results.ai_button.setEnabled(False)
        self.results.ai_button.setText("Enhancing…")
        system, messages = self._ai_prompt()
        settings = self.ai_settings
        self.ai_worker = AIWorker(lambda: complete(settings, system, messages), self)
        self.ai_worker.succeeded.connect(self._ai_done)
        self.ai_worker.failed.connect(self._ai_failed)
        self.ai_worker.finished.connect(self._ai_finished)
        self.ai_worker.start()
        self.statusBar().showMessage("Asking the configured AI for a second explanation…")

    def _ai_done(self, text: str) -> None:
        self.results.set_ai_text(text)
        self.statusBar().showMessage("AI explanation added to the guide.")

    def _ai_failed(self, error: str) -> None:
        QMessageBox.warning(self, "AI request failed", error)
        self.statusBar().showMessage("AI request failed; the local guide is unchanged.")

    def _ai_finished(self) -> None:
        self.ai_busy = False
        self.results.ai_button.setEnabled(True)
        self.results.ai_button.setText("Enhance guide")

    def save_guide(self):
        if not self.results.guide:
            QMessageBox.information(self, "No guide yet", "Run an analysis first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save guide", "prism-guide.md", "Markdown (*.md)")
        if not path:
            return
        guide = self.results.guide
        lines = [f"# {guide.get('headline', 'Prism guide')}", "", guide.get("summary", ""), "", "## Overview"]
        lines += guide.get("overview", {}).get("paragraphs", [])
        lines += ["", "## Walkthrough"]
        for item in guide.get("walkthrough", []):
            lines += [f"### {item.get('title', '')}", item.get("body", "")]
        lines += ["", "## Line by line"]
        lines += [f"- **Line {n.get('line')}** `{n.get('code', '')}` — {n.get('note', '')}" for n in guide.get("lineNotes", [])]
        if getattr(self.results, "ai_text", ""):
            lines += ["", "## AI explanation", self.results.ai_text]
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self.statusBar().showMessage(f"Guide saved to {path}")

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def about(self):
        QMessageBox.about(
            self, "About Prism",
            "Prism 2.0 — pure Python edition\n\n"
            "A local-first code analysis workspace for Python, JavaScript and TypeScript.\n"
            "Built with PySide6. No HTML, CSS or JavaScript application code is used.",
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    if "--demo" in sys.argv:
        window.load_case("Loop and total")
        window.analyze()
    if "--capture" in sys.argv:
        index = sys.argv.index("--capture")
        target = Path(sys.argv[index + 1]) if len(sys.argv) > index + 1 else Path("prism-native.png")
        def capture() -> None:
            window.grab().save(str(target))
            app.quit()
        QTimer.singleShot(900, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
