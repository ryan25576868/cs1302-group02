"""Compare page: two versions of one file, side by side, structure by structure.

This is the UI half; the diff itself lives in :mod:`python_app.compare_engine`,
which adapts Prism's analysis trees into the ``structscope`` symbol model.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QVariantAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from python_app.compare_engine import (
        ENGINE_ERROR,
        FILE_EXTENSIONS,
        LANGUAGE_LABELS,
        STATUS_COLORS,
        STATUS_FILL,
        aligned_rows,
        compare_sources,
        describe,
    )
    from python_app.i18n import tr
except ImportError:  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from python_app.compare_engine import (
        ENGINE_ERROR,
        FILE_EXTENSIONS,
        LANGUAGE_LABELS,
        STATUS_COLORS,
        STATUS_FILL,
        aligned_rows,
        compare_sources,
        describe,
    )
    from python_app.i18n import tr

DIM_OPACITY = 0.22
HOVER_DIM_OPACITY = 0.42
ENGINE_HINT = (
    "structscope is not installed \u2014 see README, section \u201cCompare two versions\u201d"
)
FILTERS = [
    ("all", "All symbols"),
    ("added", "Added"),
    ("removed", "Removed"),
    ("modified", "Modified"),
    ("moved", "Moved"),
    ("unchanged", "Unchanged"),
]


class NodeCard(QGraphicsPathItem):
    """One symbol card. Hovering lifts it and gives it a coloured glow.

    QGraphicsPathItem is not a QObject, so it cannot declare Qt signals; the
    view installs plain callables instead.
    """

    HOVER_SCALE = 1.08

    def __init__(
        self, width: float, height: float, fill: QColor, border: QColor, pair_id: str
    ):
        super().__init__()
        self.pair_id = pair_id
        self.on_enter: Optional[Callable[["NodeCard"], None]] = None
        self.on_leave: Optional[Callable[["NodeCard"], None]] = None
        self._fill = QColor(fill)
        self._border = QColor(border)
        self._glow: Optional[QGraphicsDropShadowEffect] = None
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, width, height), 5, 5)
        self.setPath(path)
        self.setBrush(QColor(fill))
        self.setPen(QPen(QColor(border), 1.0))
        self.setTransformOriginPoint(width / 2, height / 2)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setData(0, pair_id)
        # QGraphicsItem is not a QObject, so the animation cannot be parented to
        # the card; the card holds the only reference and stops it when dropped.
        self._animation = QVariantAnimation()
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
        self._animation.valueChanged.connect(self._animate_scale)

    def hoverEnterEvent(self, event) -> None:
        self._zoom(self.HOVER_SCALE)
        if self.on_enter is not None:
            self.on_enter(self)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._zoom(1.0)
        if self.on_leave is not None:
            self.on_leave(self)
        super().hoverLeaveEvent(event)

    def _zoom(self, target: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self.scale())
        self._animation.setEndValue(target)
        self._animation.start()

    def stop_animation(self) -> None:
        self._animation.stop()
        self._animation.deleteLater()

    def _animate_scale(self, value) -> None:
        try:
            self.setScale(float(value))
        except RuntimeError:  # the card was deleted while the tick was queued
            self._animation.stop()

    def apply_glow(self, enabled: bool) -> None:
        border = QColor(self._border)
        if enabled:
            border.setAlpha(255)
            self.setPen(QPen(border, 2.0))
            self.setBrush(self._fill.lighter(128))
            self.setZValue(4)
            halo = QGraphicsDropShadowEffect()
            halo.setBlurRadius(28)
            glow = QColor(self._border)
            glow.setAlpha(210)
            halo.setColor(glow)
            halo.setOffset(0, 0)
            self.setGraphicsEffect(halo)
            self._glow = halo
        else:
            self.setPen(QPen(border, 1.0))
            self.setBrush(QColor(self._fill))
            self.setZValue(0)
            if self._glow is not None:
                self.setGraphicsEffect(None)
                self._glow = None

    def child(self, item):
        """Parent a label to the card so it scales and fades with it."""
        item.setParentItem(self)
        item.setData(0, self.pair_id)
        return item


class CompareView(QGraphicsView):
    """Two columns of cards, one per symbol, joined wherever a symbol matched."""

    pairSelected = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        self.setBackgroundBrush(QColor("#1c1f24"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMouseTracking(True)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._cards: Dict[str, List[NodeCard]] = {}
        self._links: Dict[str, QGraphicsPathItem] = {}
        self._hovered: Optional[NodeCard] = None
        self._result = None
        self._geometry: Dict[str, Any] = {}
        self._filter = "all"
        self.show_placeholder()

    # -- content -----------------------------------------------------------

    def _release_cards(self) -> None:
        """Stop hover animations before their cards are deleted with the scene."""
        for cards in self._cards.values():
            for card in cards:
                card.stop_animation()
        self._cards = {}
        self._links = {}
        self._hovered = None

    def show_placeholder(self) -> None:
        self._release_cards()
        self._scene.clear()
        self._result = None
        self._geometry = {}
        self._scene.setSceneRect(QRectF(0, 0, 980, 460))
        hint = self._scene.addSimpleText(
            "Choose a language, then a before file and an after file."
        )
        hint.setBrush(QColor("#6f7885"))
        hint.setFont(QFont("Segoe UI", 12))
        hint.setPos(44, 200)
        sub = self._scene.addSimpleText(
            "Prism compares the symbols it finds \u2014 classes, functions and methods."
        )
        sub.setBrush(QColor("#59606b"))
        sub.setFont(QFont("Segoe UI", 9))
        sub.setPos(44, 238)

    def set_result(self, result: Any) -> None:
        self._result = result
        self._release_cards()
        self._scene.clear()
        # Imported lazily: the layout engine is part of structscope.
        from structscope.layout import compute as layout_diff

        geometry = layout_diff(result)
        self._geometry = geometry
        self._scene.setSceneRect(QRectF(0, 0, geometry["width"], geometry["height"]))

        for node in geometry["old_nodes"]:
            self._draw_node(node, "left")
        for node in geometry["new_nodes"]:
            self._draw_node(node, "right")

        for pair in result.pairs:
            box = geometry["boxes"].get(pair.id or "")
            if not box or "old" not in box or "new" not in box:
                continue
            self._draw_link(box["old"], box["new"], pair)

        self._label(6, "BEFORE")
        self._label(geometry["new_x"] + 6, "AFTER")
        self.fitInView(
            self._scene.itemsBoundingRect().adjusted(-20, -20, 24, 24),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._apply_visuals()

    def apply_filter(self, mode: str) -> None:
        self._filter = mode
        self._apply_visuals()

    def _apply_visuals(self) -> None:
        """Dim what the filter or the hover hides; glow the pair under the cursor."""
        if self._result is None:
            return
        hover_id = self._hovered.pair_id if self._hovered is not None else None
        for pair in self._result.pairs:
            pair_id = pair.id or ""
            matched = self._filter == "all" or pair.status.value == self._filter
            related = hover_id is None or pair_id == hover_id
            opacity = 1.0
            if not matched:
                opacity = DIM_OPACITY
            elif not related:
                opacity = HOVER_DIM_OPACITY
            for card in self._cards.get(pair_id, []):
                card.setOpacity(opacity)
                card.apply_glow(matched and hover_id is not None and pair_id == hover_id)
            link = self._links.get(pair_id)
            if link is not None:
                strong = matched and hover_id is not None and pair_id == hover_id
                link.setPen(self._link_pen(pair, strong))
                link.setOpacity(1.0 if matched and related else HOVER_DIM_OPACITY)

    @staticmethod
    def _link_pen(pair: Any, strong: bool = False) -> QPen:
        color = QColor(STATUS_COLORS[pair.status.value])
        color.setAlpha(255 if strong else 150)
        pen = QPen(color, 2.2 if strong else 1.2)
        if pair.status.value == "modified":
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def _card_hover_entered(self, card: NodeCard) -> None:
        self._hovered = card
        self._apply_visuals()

    def _card_hover_left(self, card: NodeCard) -> None:
        if self._hovered is card:
            self._hovered = None
            self._apply_visuals()

    # -- painting ----------------------------------------------------------

    def _label(self, x: float, text: str) -> None:
        label = self._scene.addSimpleText(text)
        label.setBrush(QColor("#8d96a1"))
        label.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        label.setPos(x, 36)

    def _draw_node(self, node: Dict[str, Any], side: str) -> None:
        symbol = node["sym"]
        status = symbol.status.value
        color = QColor(STATUS_COLORS[status])
        x, y, width, height = node["x"], node["y"], node["w"], node["h"]

        border = QColor(color)
        border.setAlpha(130)
        card = NodeCard(
            width, height, QColor(STATUS_FILL[status]), border, symbol.pair_id or ""
        )
        card.setPos(x, y)
        card.setToolTip(
            f"{symbol.qualname}\n{status}  \u00b7  lines {symbol.lineno}-{symbol.end_lineno}"
            f"\ncomplexity {symbol.complexity}  \u00b7  {symbol.loc} code lines"
        )
        card.on_enter = self._card_hover_entered
        card.on_leave = self._card_hover_left
        self._scene.addItem(card)

        accent = QGraphicsPathItem()
        accent_path = QPainterPath()
        accent_path.addRoundedRect(QRectF(0, 0, 3, height), 1.5, 1.5)
        accent.setPath(accent_path)
        accent.setBrush(color)
        accent.setPen(QPen(Qt.PenStyle.NoPen))
        card.child(accent)

        name = card.child(QGraphicsSimpleTextItem(symbol.display))
        name.setBrush(QColor("#e9edf2"))
        name.setFont(QFont("Cascadia Code", 8))
        name.setPos(11, 4)

        span = card.child(QGraphicsSimpleTextItem(str(symbol.lineno)))
        span.setBrush(QColor("#7d8794"))
        span.setFont(QFont("Cascadia Code", 7))
        span.setPos(width - 30, 5)

        box = self._geometry["boxes"].get(symbol.pair_id or "", {})
        other = box.get("new" if side == "left" else "old")
        if other is not None and other["sym"].complexity != symbol.complexity:
            badge = card.child(QGraphicsSimpleTextItem(str(symbol.complexity)))
            badge.setBrush(QColor(STATUS_COLORS["modified"]))
            badge.setFont(QFont("Cascadia Code", 7))
            badge.setPos(width - 54, 5)

        self._cards.setdefault(symbol.pair_id or "", []).append(card)

    def _draw_link(self, old_node: Dict[str, Any], new_node: Dict[str, Any], pair: Any) -> None:
        start = QPointF(old_node["x"] + old_node["w"], old_node["y"] + old_node["h"] / 2)
        end = QPointF(new_node["x"], new_node["y"] + new_node["h"] / 2)
        path = QPainterPath(start)
        reach = max(40.0, (end.x() - start.x()) * 0.45)
        path.cubicTo(
            QPointF(start.x() + reach, start.y()),
            QPointF(end.x() - reach, end.y()),
            end,
        )
        link = QGraphicsPathItem(path)
        link.setPen(self._link_pen(pair))
        link.setZValue(-1)
        link.setData(0, pair.id)
        self._scene.addItem(link)
        self._links[pair.id or ""] = link

    # -- interaction -------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        pair_id = None
        while item is not None and pair_id is None:
            pair_id = item.data(0)
            item = item.parentItem()
        if pair_id and self._result is not None:
            for pair in self._result.pairs:
                if pair.id == pair_id:
                    self.pairSelected.emit(pair)
                    break
        super().mousePressEvent(event)


class ComparePage(QWidget):
    """Pick two versions of a file; see what changed in the code's structure."""

    back = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.language = "python"
        self.old_source = ""
        self.new_source = ""
        self.old_label = ""
        self.new_label = ""
        self.result = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        self.back_button = QPushButton(tr("\u2190 Welcome"))
        self.back_button.setObjectName("Ghost")
        head.addWidget(self.back_button)
        self.title_label = QLabel(tr("Compare versions"))
        self.title_label.setObjectName("CardTitle")
        head.addWidget(self.title_label)

        self.language_box = QComboBox()
        for language_id, label in LANGUAGE_LABELS:
            self.language_box.addItem(label, language_id)
        head.addWidget(self.language_box)

        self.filter_box = QComboBox()
        for key, label in FILTERS:
            self.filter_box.addItem(tr(label), key)
        head.addWidget(self.filter_box)
        head.addStretch(1)

        self.old_button = QPushButton(tr("Before file\u2026"))
        self.new_button = QPushButton(tr("After file\u2026"))
        self.sample_button = QPushButton(tr("Sample pair"))
        self.sample_button.setObjectName("Chip")
        self.swap_button = QPushButton(tr("Swap"))
        self.swap_button.setObjectName("Chip")
        self.compare_button = QPushButton(tr("Compare"))
        self.compare_button.setObjectName("Primary")
        head.addWidget(self.old_button)
        head.addWidget(self.new_button)
        head.addWidget(self.sample_button)
        head.addWidget(self.swap_button)
        head.addWidget(self.compare_button)
        layout.addLayout(head)

        self.status = QLabel(
            tr("Pick two versions of the same file to see the structural diff.")
        )
        self.status.setObjectName("Tiny")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.view = CompareView()
        split.addWidget(self.view)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)
        self.detail_title = QLabel(tr("Select a symbol"))
        self.detail_title.setObjectName("Tiny")
        detail_layout.addWidget(self.detail_title)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", tr("Before"), "#", tr("After")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        detail_layout.addWidget(self.table, 1)
        split.addWidget(detail)
        split.setSizes([780, 460])
        layout.addWidget(split, 1)

        if ENGINE_ERROR:
            self.status.setText(
                tr(ENGINE_HINT)
            )

        self.back_button.clicked.connect(self.back.emit)
        self.language_box.currentIndexChanged.connect(self._language_changed)
        self.filter_box.currentIndexChanged.connect(
            lambda _index: self.view.apply_filter(self.filter_box.currentData())
        )
        self.old_button.clicked.connect(lambda: self._load("old"))
        self.new_button.clicked.connect(lambda: self._load("new"))
        self.sample_button.clicked.connect(self._load_sample)
        self.swap_button.clicked.connect(self._swap)
        self.compare_button.clicked.connect(self.run_compare)
        self.view.pairSelected.connect(self.show_pair)

    def retranslate(self) -> None:
        """Re-apply interface strings after the UI language changed."""
        self.back_button.setText(tr("\u2190 Welcome"))
        self.title_label.setText(tr("Compare versions"))
        for index, (_key, label) in enumerate(FILTERS):
            self.filter_box.setItemText(index, tr(label))
        if not self.old_label:
            self.old_button.setText(tr("Before file\u2026"))
        if not self.new_label:
            self.new_button.setText(tr("After file\u2026"))
        self.sample_button.setText(tr("Sample pair"))
        self.swap_button.setText(tr("Swap"))
        self.compare_button.setText(tr("Compare"))
        self.table.setHorizontalHeaderLabels(["#", tr("Before"), "#", tr("After")])
        if self.detail_title.text() in ("Select a symbol", ""):
            self.detail_title.setText(tr("Select a symbol"))
        if ENGINE_ERROR:
            self.status.setText(tr(ENGINE_HINT))
        elif self.result is None:
            self.status.setText(
                tr("Pick two versions of the same file to see the structural diff.")
            )

    # -- files -------------------------------------------------------------

    def _language_changed(self, _index: int) -> None:
        self.language = self.language_box.currentData()
        name = self.language_box.currentText()
        self.status.setText(tr("{name}: pick a before file and an after file.", name=name))

    def _patterns(self) -> str:
        extensions = FILE_EXTENSIONS.get(self.language, [])
        if not extensions:
            return "*"
        return " ".join(f"*.{extension}" for extension in extensions)

    def _load(self, side: str) -> None:
        title = tr("Choose the before file") if side == "old" else tr("Choose the after file")
        path, _filter = QFileDialog.getOpenFileName(
            self, title, "", f"{tr('Source files')} ({self._patterns()});;{tr('All files')} (*)"
        )
        if not path:
            return
        try:
            text = self._read(path)
        except OSError as error:
            self.status.setText(
                tr("Could not read {name}: {error}", name=Path(path).name, error=error)
            )
            return
        name = Path(path).name
        if side == "old":
            self.old_source, self.old_label = text, name
        else:
            self.new_source, self.new_label = text, name
        self.old_button.setText(self.old_label or tr("Before file\u2026"))
        self.new_button.setText(self.new_label or tr("After file\u2026"))
        self.status.setText(
            f"{self.old_label or tr('(no before file)')}  \u2192  "
            f"{self.new_label or tr('(no after file)')}"
        )

    @staticmethod
    def _read(path: str) -> str:
        data = Path(path).read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "cp1252", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _load_sample(self) -> None:
        """Fill both sides from the bundled samples so the page can be tried at once."""
        bundled = {
            "python": ("report_before.py", "report_after.py"),
            "java": ("Shape.java", "ShapeRefactored.java"),
        }
        pair = bundled.get(self.language)
        if pair is None:
            self.status.setText(
                tr("No bundled sample for {name} yet \u2014 pick two files.",
                   name=self.language_box.currentText())
            )
            return
        folder = Path(__file__).resolve().parent.parent / "samples"
        try:
            self.old_source = self._read(str(folder / pair[0]))
            self.new_source = self._read(str(folder / pair[1]))
        except OSError as error:
            self.status.setText(tr("Sample files are missing: {error}", error=error))
            return
        self.old_label, self.new_label = pair
        self.old_button.setText(self.old_label)
        self.new_button.setText(self.new_label)
        self.status.setText(tr("Sample: {old}  \u2192  {new}", old=pair[0], new=pair[1]))
        self.run_compare()

    def _swap(self) -> None:
        self.old_source, self.new_source = self.new_source, self.old_source
        self.old_label, self.new_label = self.new_label, self.old_label
        self.old_button.setText(self.old_label or tr("Before file\u2026"))
        self.new_button.setText(self.new_label or tr("After file\u2026"))

    # -- diff --------------------------------------------------------------

    def run_compare(self) -> None:
        if ENGINE_ERROR:
            self.status.setText(
                tr(ENGINE_HINT)
            )
            return
        if not self.old_source or not self.new_source:
            self.status.setText(tr("Choose both files first."))
            return
        self.status.setText(tr("Comparing\u2026"))
        self.repaint()
        try:
            result = compare_sources(
                self.language,
                self.old_source,
                self.new_source,
                self.old_label or "before",
                self.new_label or "after",
            )
        except Exception as error:  # parse errors carry a readable message
            self.view.show_placeholder()
            self.table.setRowCount(0)
            self.detail_title.setText(tr("Select a symbol"))
            self.status.setText(tr("Could not compare: {error}", error=error))
            return

        self.result = result
        summary = result.summary()
        self.status.setText(describe(summary))
        if not result.pairs:
            self.view.show_placeholder()
            self.status.setText(tr("No classes or functions found in either file."))
            return
        self.view.set_result(result)
        first_changed = next(
            (pair for pair in result.pairs if pair.status.value != "unchanged"), None
        )
        self.show_pair(first_changed or result.pairs[0])

    # -- detail table ------------------------------------------------------

    def show_pair(self, pair: Any) -> None:
        if pair is None or self.result is None:
            return
        symbol = pair.symbol
        self.detail_title.setText(
            f"{symbol.qualname}  \u00b7  {symbol.kind}  \u00b7  {pair.status.value.upper()}"
        )
        old_symbol, new_symbol = pair.old, pair.new
        old_lines: List[str] = []
        new_lines: List[str] = []
        old_start = new_start = 1
        if old_symbol is not None:
            old_lines = self.result.old.lines[old_symbol.lineno - 1:old_symbol.end_lineno]
            old_start = old_symbol.lineno
        if new_symbol is not None:
            new_lines = self.result.new.lines[new_symbol.lineno - 1:new_symbol.end_lineno]
            new_start = new_symbol.lineno

        rows = aligned_rows(old_lines, new_lines, old_start, new_start)
        self.table.setRowCount(len(rows))
        tones = {
            "eq": ("#1d2025", "#1d2025"),
            "del": ("#331f1e", "#1d2025"),
            "ins": ("#1d2025", "#1c2b23"),
            "rep": ("#332a1c", "#332a1c"),
        }
        for row_index, (tag, old_no, old_text, new_no, new_text) in enumerate(rows):
            left_tone, right_tone = tones[tag]
            self._cell(row_index, 0, str(old_no or ""), "#6f7885", left_tone)
            self._cell(row_index, 1, old_text, "#dfe4ea", left_tone)
            self._cell(row_index, 2, str(new_no or ""), "#6f7885", right_tone)
            self._cell(row_index, 3, new_text, "#dfe4ea", right_tone)

    def _cell(self, row: int, column: int, text: str, ink: str, background: str) -> None:
        item = QTableWidgetItem(text)
        item.setForeground(QColor(ink))
        item.setBackground(QColor(background))
        if column in (0, 2):
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self.table.setItem(row, column, item)
