"""Native PySide6 interface for the restricted Function POV simulator."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from python_app.function_pov.analyzer import analyze_source
from python_app.function_pov.models import AnalysisResult, FunctionInfo
from python_app.function_pov.pov.engine import (
    MAX_INTEGER_BITS,
    PovSimulation,
    SimulationError,
    build_program_simulation_from_source,
    build_simulation_from_source,
)
from python_app.function_pov.pov.exercises import (
    ExerciseGenerationError,
    GeneratedExercise,
    PracticeExerciseGenerator,
)
from python_app.i18n import simulation_error_text, tr

MAX_JSON_INPUT_CHARS = 10000


def _parse_json_integer(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > 78:
        raise ValueError("JSON integer is too large.")
    value = int(token)
    if value.bit_length() > MAX_INTEGER_BITS:
        raise ValueError("JSON integer is too large.")
    return value


def _parse_json_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("JSON number is not finite.")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError("Invalid JSON number: {}.".format(token))


def _decode_json_input(raw: str) -> tuple[Any, str | None]:
    if len(raw) > MAX_JSON_INPUT_CHARS:
        return None, "too_long"
    try:
        return json.loads(
            raw,
            parse_int=_parse_json_integer,
            parse_float=_parse_json_float,
            parse_constant=_reject_json_constant,
        ), None
    except json.JSONDecodeError:
        return None, "invalid"
    except (ValueError, RecursionError, OverflowError):
        return None, "unsafe"


class PixelMascot(QWidget):
    def __init__(self, size: int, celebrating: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.celebrating = celebrating
        self._phase = False
        self._timer = QTimer(self)
        self._timer.setInterval(420)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._phase = not self._phase
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        cell = max(2, min(self.width(), self.height()) // 16)
        origin_x = (self.width() - cell * 16) // 2
        origin_y = (self.height() - cell * 16) // 2
        bob = 1 if self._phase else 0

        def pixel(x: int, y: int, width: int, height: int, color: str) -> None:
            painter.fillRect(
                origin_x + x * cell,
                origin_y + (y + bob) * cell,
                width * cell,
                height * cell,
                QColor(color),
            )

        pixel(6, 1, 4, 1, "#2f67cb")
        pixel(4, 2, 8, 2, "#2f67cb")
        pixel(2, 4, 12, 7, "#2f67cb")
        pixel(3, 10, 10, 3, "#2f67cb")
        pixel(5, 13, 2, 2, "#2f67cb")
        pixel(9, 13, 2, 2, "#2f67cb")
        pixel(4, 3, 8, 2, "#a9d5ff")
        pixel(3, 5, 10, 5, "#a9d5ff")
        pixel(4, 10, 8, 2, "#a9d5ff")
        pixel(5, 6, 2, 2, "#ffffff")
        pixel(9, 6, 2, 2, "#ffffff")
        pixel(6, 7, 1, 1, "#173b78")
        pixel(10, 7, 1, 1, "#173b78")
        pixel(7, 9, 2, 1, "#2f67cb")
        pixel(12, 3, 1, 1, "#ff7852")
        pixel(13, 2, 1, 1, "#ff7852")
        pixel(14, 3, 1, 1, "#ff7852")
        if self.celebrating and self._phase:
            pixel(1, 3, 1, 1, "#62d6da")
            pixel(14, 10, 1, 1, "#62d6da")


class FunctionPOVPage(QWidget):
    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FunctionPOVPage")
        self.setStyleSheet(
            """
            QWidget#FunctionPOVPage { background: #1b1d21; }
            QFrame#PovCard { background: #23262b; border: 1px solid #3b4149; border-radius: 10px; }
            QLabel#PovKicker { color: #62d6da; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
            QLabel#PovTitle { color: #f4f5f6; font-size: 22pt; font-weight: 700; }
            QLabel#PovSubtitle { color: #aab2bd; }
            QLabel#PovMuted { color: #aab2bd; }
            QLabel#PovExpression { color: #9ce5e7; background: #171a1e; border: 1px solid #343a42; border-radius: 6px; padding: 8px; font-family: "Cascadia Code", "Consolas", monospace; }
            QLabel#PovFeedback { color: #f3c178; background: #30291f; border: 1px solid #6b5434; border-radius: 6px; padding: 8px; }
            QPlainTextEdit#PovSource, QListWidget#PovList { background: #17191d; border: 1px solid #34383f; border-radius: 7px; color: #dfe4ea; selection-background-color: #51402d; font-family: "Cascadia Code", "Consolas", monospace; }
            QPushButton#PovPrimary { background: #ff7852; border: 1px solid #ff7852; border-radius: 6px; color: #201310; font-weight: 700; padding: 8px 14px; }
            QPushButton#PovPrimary:hover { background: #ff8d6c; }
            QPushButton#PovSecondary { background: #2b2f36; border: 1px solid #41464f; border-radius: 6px; color: #e9ecf0; padding: 7px 12px; }
            QPushButton#PovSecondary:hover { border-color: #62d6da; }
            QPushButton#PovMode { background: #2b2f36; border: 1px solid #41464f; border-radius: 6px; color: #e9ecf0; padding: 7px 14px; font-weight: 600; }
            QPushButton#PovMode:checked { background: #51402d; border-color: #ff7852; color: #fff2df; }
            QPushButton#PovMode:disabled { color: #777f89; }
            QPushButton:disabled { color: #777f89; background: #25282d; border-color: #34383f; }
            QProgressBar#PovProgress { background: #17191d; border: 1px solid #3b4149; border-radius: 4px; color: #cbd3dc; text-align: center; height: 14px; }
            QProgressBar#PovProgress::chunk { background: #ff7852; border: 1px solid #62d6da; }
            QFrame#PovCompletionCard { background: #23262b; border: 1px solid #ff7852; border-radius: 12px; }
            """
        )
        self._source = ""
        self._filename = "main.py"
        self._analysis: AnalysisResult | None = None
        self._functions: dict[str, FunctionInfo] = {}
        self._simulation: PovSimulation | None = None
        self._original_simulation: PovSimulation | None = None
        self._program_simulation: PovSimulation | None = None
        self._program_error: str | None = None
        self._mode = "function"
        self._step_index = 0
        self._passed: set[int] = set()
        self._solved_by_attempt: set[int] = set()
        self._revealed: set[int] = set()
        self._history: dict[int, list[dict[str, Any]]] = {}
        self._drafts: dict[int, str] = {}
        self._parameter_fields: dict[str, QLineEdit] = {}
        self._unsupported_language: str | None = None
        self._completion_metrics: dict[str, Any] | None = None
        self._exercise_generator = PracticeExerciseGenerator()
        self._practice_context: tuple[str, str | None, dict[str, Any]] | None = None
        self._pending_exercise: GeneratedExercise | None = None
        self._active_exercise: GeneratedExercise | None = None
        self._generation_status = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 18)
        root.setSpacing(12)
        nav = QHBoxLayout()
        self.back_button = QPushButton()
        self.back_button.setObjectName("PovSecondary")
        self.back_button.clicked.connect(self.backRequested)
        nav.addWidget(self.back_button)
        self.nav_label = QLabel()
        self.nav_label.setObjectName("PovKicker")
        nav.addWidget(self.nav_label)
        nav.addStretch(1)
        root.addLayout(nav)

        self.screens = QStackedWidget()
        self._build_selection_screen()
        self._build_practice_screen()
        self._build_completion_screen()
        self._build_exercise_screen()
        root.addWidget(self.screens, 1)
        self.retranslate()

    def _build_selection_screen(self) -> None:
        self.selection_screen = QWidget()
        outer = QVBoxLayout(self.selection_screen)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        hero = QHBoxLayout()
        self.entry_mascot = PixelMascot(112)
        hero.addWidget(self.entry_mascot)
        hero_copy = QVBoxLayout()
        self.entry_kicker = QLabel()
        self.entry_kicker.setObjectName("PovKicker")
        hero_copy.addWidget(self.entry_kicker)
        self.entry_title = QLabel()
        self.entry_title.setObjectName("PovTitle")
        hero_copy.addWidget(self.entry_title)
        self.entry_subtitle = QLabel()
        self.entry_subtitle.setObjectName("PovSubtitle")
        self.entry_subtitle.setWordWrap(True)
        hero_copy.addWidget(self.entry_subtitle)
        hero_copy.addStretch(1)
        hero.addLayout(hero_copy, 1)
        outer.addLayout(hero)

        card = QFrame()
        card.setObjectName("PovCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(9)
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.code_mode_button = QPushButton()
        self.code_mode_button.setObjectName("PovMode")
        self.code_mode_button.setCheckable(True)
        self.code_mode_button.clicked.connect(lambda: self._select_mode("code"))
        self.function_mode_button = QPushButton()
        self.function_mode_button.setObjectName("PovMode")
        self.function_mode_button.setCheckable(True)
        self.function_mode_button.clicked.connect(lambda: self._select_mode("function"))
        self.mode_group.addButton(self.code_mode_button)
        self.mode_group.addButton(self.function_mode_button)
        mode_row.addWidget(self.code_mode_button)
        mode_row.addWidget(self.function_mode_button)
        mode_row.addStretch(1)
        card_layout.addLayout(mode_row)
        self.selection_heading = QLabel()
        self.selection_heading.setObjectName("PovKicker")
        card_layout.addWidget(self.selection_heading)

        columns = QSplitter(Qt.Orientation.Horizontal)
        self.function_list = QListWidget()
        self.function_list.setObjectName("PovList")
        self.function_list.setMinimumWidth(220)
        self.function_list.currentItemChanged.connect(self._function_selected)
        columns.addWidget(self.function_list)

        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(8, 0, 0, 0)
        detail_layout.setSpacing(7)
        self.function_heading = QLabel()
        self.function_heading.setObjectName("PovTitle")
        detail_layout.addWidget(self.function_heading)
        self.function_description = QLabel()
        self.function_description.setObjectName("PovMuted")
        self.function_description.setWordWrap(True)
        detail_layout.addWidget(self.function_description)
        self.relationships = QLabel()
        self.relationships.setObjectName("PovMuted")
        self.relationships.setWordWrap(True)
        detail_layout.addWidget(self.relationships)
        self.arguments_heading = QLabel()
        self.arguments_heading.setObjectName("PovKicker")
        detail_layout.addWidget(self.arguments_heading)
        self.parameter_form = QFormLayout()
        self.parameter_form.setContentsMargins(0, 0, 0, 0)
        self.parameter_form.setSpacing(7)
        detail_layout.addLayout(self.parameter_form)
        self.support_note = QLabel()
        self.support_note.setObjectName("PovMuted")
        self.support_note.setWordWrap(True)
        detail_layout.addWidget(self.support_note)
        self.selection_error = QLabel()
        self.selection_error.setObjectName("PovFeedback")
        self.selection_error.setWordWrap(True)
        self.selection_error.hide()
        detail_layout.addWidget(self.selection_error)
        self.start_button = QPushButton()
        self.start_button.setObjectName("PovPrimary")
        self.start_button.clicked.connect(self._start_simulation)
        detail_layout.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignRight)
        detail_layout.addStretch(1)
        columns.addWidget(details)
        columns.setSizes([300, 620])
        card_layout.addWidget(columns, 1)
        outer.addWidget(card, 1)

        self.selection_message = QLabel()
        self.selection_message.setObjectName("PovMuted")
        self.selection_message.setWordWrap(True)
        outer.addWidget(self.selection_message)
        self.screens.addWidget(self.selection_screen)

    def _build_practice_screen(self) -> None:
        self.practice_screen = QWidget()
        outer = QVBoxLayout(self.practice_screen)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(9)
        progress_row = QHBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setObjectName("PovKicker")
        progress_row.addWidget(self.progress_label)
        progress_row.addStretch(1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("PovProgress")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(220)
        progress_row.addWidget(self.progress_bar)
        outer.addLayout(progress_row)

        split = QSplitter(Qt.Orientation.Horizontal)
        source_card = QFrame()
        source_card.setObjectName("PovCard")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(12, 10, 12, 12)
        self.source_heading = QLabel()
        self.source_heading.setObjectName("PovKicker")
        source_layout.addWidget(self.source_heading)
        self.source_view = QPlainTextEdit()
        self.source_view.setObjectName("PovSource")
        self.source_view.setReadOnly(True)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(10)
        self.source_view.setFont(font)
        source_layout.addWidget(self.source_view, 1)
        split.addWidget(source_card)

        action_scroll = QScrollArea()
        action_scroll.setWidgetResizable(True)
        action_scroll.setFrameShape(QFrame.Shape.NoFrame)
        action_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; } "
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        action_panel = QWidget()
        action_layout = QVBoxLayout(action_panel)
        action_layout.setContentsMargins(2, 2, 2, 2)
        action_layout.setSpacing(8)

        top = QFrame()
        top.setObjectName("PovCard")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(10, 8, 10, 8)
        self.game_mascot = PixelMascot(48)
        top_layout.addWidget(self.game_mascot)
        self.step_prompt = QLabel()
        self.step_prompt.setObjectName("PovTitle")
        self.step_prompt.setWordWrap(True)
        top_layout.addWidget(self.step_prompt, 1)
        action_layout.addWidget(top)

        self.expression_label = QLabel()
        self.expression_label.setObjectName("PovExpression")
        self.expression_label.setWordWrap(True)
        action_layout.addWidget(self.expression_label)

        memory_card = QFrame()
        memory_card.setObjectName("PovCard")
        memory_layout = QHBoxLayout(memory_card)
        memory_layout.setContentsMargins(10, 8, 10, 8)
        stack_panel = QWidget()
        stack_layout = QVBoxLayout(stack_panel)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        self.stack_heading = QLabel()
        self.stack_heading.setObjectName("PovKicker")
        stack_layout.addWidget(self.stack_heading)
        self.stack_list = QListWidget()
        self.stack_list.setObjectName("PovList")
        self.stack_list.setMaximumHeight(105)
        stack_layout.addWidget(self.stack_list)
        variables_panel = QWidget()
        variables_layout = QVBoxLayout(variables_panel)
        variables_layout.setContentsMargins(0, 0, 0, 0)
        self.variables_heading = QLabel()
        self.variables_heading.setObjectName("PovKicker")
        variables_layout.addWidget(self.variables_heading)
        self.variables_list = QListWidget()
        self.variables_list.setObjectName("PovList")
        self.variables_list.setMaximumHeight(105)
        variables_layout.addWidget(self.variables_list)
        memory_layout.addWidget(stack_panel)
        memory_layout.addWidget(variables_panel)
        action_layout.addWidget(memory_card)

        challenge_card = QFrame()
        challenge_card.setObjectName("PovCard")
        challenge_layout = QVBoxLayout(challenge_card)
        challenge_layout.setContentsMargins(12, 10, 12, 10)
        challenge_layout.setSpacing(7)
        self.challenge_prompt = QLabel()
        self.challenge_prompt.setWordWrap(True)
        challenge_layout.addWidget(self.challenge_prompt)
        self.answer_row = QWidget()
        answer_layout = QHBoxLayout(self.answer_row)
        answer_layout.setContentsMargins(0, 0, 0, 0)
        self.answer_edit = QLineEdit()
        self.answer_edit.setMaxLength(MAX_JSON_INPUT_CHARS + 1)
        self.answer_edit.returnPressed.connect(self._submit_text_answer)
        answer_layout.addWidget(self.answer_edit, 1)
        self.check_button = QPushButton()
        self.check_button.setObjectName("PovPrimary")
        self.check_button.clicked.connect(self._submit_text_answer)
        answer_layout.addWidget(self.check_button)
        challenge_layout.addWidget(self.answer_row)
        self.choice_row = QWidget()
        self.choice_layout = QHBoxLayout(self.choice_row)
        self.choice_layout.setContentsMargins(0, 0, 0, 0)
        challenge_layout.addWidget(self.choice_row)
        self.feedback_label = QLabel()
        self.feedback_label.setObjectName("PovFeedback")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.hide()
        challenge_layout.addWidget(self.feedback_label)
        self.hint_label = QLabel()
        self.hint_label.setObjectName("PovMuted")
        self.hint_label.setWordWrap(True)
        self.hint_label.hide()
        challenge_layout.addWidget(self.hint_label)
        self.history_heading = QLabel()
        self.history_heading.setObjectName("PovKicker")
        challenge_layout.addWidget(self.history_heading)
        self.history_list = QListWidget()
        self.history_list.setObjectName("PovList")
        self.history_list.setMaximumHeight(92)
        challenge_layout.addWidget(self.history_list)
        action_layout.addWidget(challenge_card)
        action_layout.addStretch(1)
        action_scroll.setWidget(action_panel)
        split.addWidget(action_scroll)
        split.setSizes([570, 430])
        outer.addWidget(split, 1)

        controls = QHBoxLayout()
        self.previous_button = QPushButton()
        self.previous_button.setObjectName("PovSecondary")
        self.previous_button.clicked.connect(self._previous_step)
        self.restart_button = QPushButton()
        self.restart_button.setObjectName("PovSecondary")
        self.restart_button.clicked.connect(self._restart)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.restart_button)
        controls.addStretch(1)
        self.hint_button = QPushButton()
        self.hint_button.setObjectName("PovSecondary")
        self.hint_button.clicked.connect(self._show_hint)
        self.answer_button = QPushButton()
        self.answer_button.setObjectName("PovSecondary")
        self.answer_button.clicked.connect(self._show_answer)
        self.next_button = QPushButton()
        self.next_button.setObjectName("PovPrimary")
        self.next_button.clicked.connect(self._next_step)
        controls.addWidget(self.hint_button)
        controls.addWidget(self.answer_button)
        controls.addWidget(self.next_button)
        outer.addLayout(controls)
        self.screens.addWidget(self.practice_screen)

    def _build_completion_screen(self) -> None:
        self.completion_screen = QWidget()
        outer = QVBoxLayout(self.completion_screen)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.addStretch(1)
        content = QWidget()
        content.setMaximumWidth(800)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        card = QFrame()
        card.setObjectName("PovCompletionCard")
        card.setMinimumWidth(440)
        card.setMaximumWidth(760)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 28, 32, 28)
        card_layout.setSpacing(14)
        self.completion_mascot = PixelMascot(144, celebrating=True)
        card_layout.addWidget(self.completion_mascot, 0, Qt.AlignmentFlag.AlignHCenter)
        self.completion_kicker = QLabel()
        self.completion_kicker.setObjectName("PovKicker")
        card_layout.addWidget(self.completion_kicker, 0, Qt.AlignmentFlag.AlignHCenter)
        self.completion_title = QLabel()
        self.completion_title.setObjectName("PovTitle")
        card_layout.addWidget(self.completion_title, 0, Qt.AlignmentFlag.AlignHCenter)
        self.completion_summary = QLabel()
        self.completion_summary.setObjectName("PovSubtitle")
        self.completion_summary.setWordWrap(True)
        self.completion_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.completion_summary.setMaximumWidth(680)
        card_layout.addWidget(self.completion_summary)
        content_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        actions = QHBoxLayout()
        self.similar_button = QPushButton()
        self.similar_button.setObjectName("PovPrimary")
        self.similar_button.clicked.connect(self._open_exercise_screen)
        actions.addWidget(self.similar_button)
        self.replay_button = QPushButton()
        self.replay_button.setObjectName("PovSecondary")
        self.replay_button.clicked.connect(self._restart)
        actions.addWidget(self.replay_button)
        content_layout.addLayout(actions)
        outer.addWidget(content, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        self.screens.addWidget(self.completion_screen)

    def _build_exercise_screen(self) -> None:
        self.exercise_screen = QWidget()
        outer = QVBoxLayout(self.exercise_screen)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        hero = QHBoxLayout()
        self.exercise_mascot = PixelMascot(76)
        hero.addWidget(self.exercise_mascot)
        hero_copy = QVBoxLayout()
        self.exercise_title = QLabel()
        self.exercise_title.setObjectName("PovTitle")
        hero_copy.addWidget(self.exercise_title)
        self.exercise_subtitle = QLabel()
        self.exercise_subtitle.setObjectName("PovSubtitle")
        self.exercise_subtitle.setWordWrap(True)
        hero_copy.addWidget(self.exercise_subtitle)
        hero.addLayout(hero_copy, 1)
        outer.addLayout(hero)

        level_row = QHBoxLayout()
        self.new_values_button = QPushButton()
        self.new_values_button.setObjectName("PovSecondary")
        self.new_values_button.clicked.connect(
            lambda: self._generate_exercise("new_values")
        )
        self.similar_logic_button = QPushButton()
        self.similar_logic_button.setObjectName("PovPrimary")
        self.similar_logic_button.clicked.connect(
            lambda: self._generate_exercise("similar_logic")
        )
        level_row.addWidget(self.new_values_button)
        level_row.addWidget(self.similar_logic_button)
        level_row.addStretch(1)
        outer.addLayout(level_row)

        self.exercise_status = QLabel()
        self.exercise_status.setObjectName("PovFeedback")
        self.exercise_status.setWordWrap(True)
        outer.addWidget(self.exercise_status)

        comparison = QSplitter(Qt.Orientation.Horizontal)
        original_card = QFrame()
        original_card.setObjectName("PovCard")
        original_layout = QVBoxLayout(original_card)
        original_layout.setContentsMargins(10, 8, 10, 10)
        self.original_code_heading = QLabel()
        self.original_code_heading.setObjectName("PovKicker")
        original_layout.addWidget(self.original_code_heading)
        self.original_inputs_label = QLabel()
        self.original_inputs_label.setObjectName("PovMuted")
        original_layout.addWidget(self.original_inputs_label)
        self.original_code_view = QPlainTextEdit()
        self.original_code_view.setObjectName("PovSource")
        self.original_code_view.setReadOnly(True)
        original_layout.addWidget(self.original_code_view, 1)
        comparison.addWidget(original_card)

        exercise_card = QFrame()
        exercise_card.setObjectName("PovCard")
        exercise_layout = QVBoxLayout(exercise_card)
        exercise_layout.setContentsMargins(10, 8, 10, 10)
        self.generated_code_heading = QLabel()
        self.generated_code_heading.setObjectName("PovKicker")
        exercise_layout.addWidget(self.generated_code_heading)
        self.generated_inputs_label = QLabel()
        self.generated_inputs_label.setObjectName("PovMuted")
        exercise_layout.addWidget(self.generated_inputs_label)
        self.generated_code_view = QPlainTextEdit()
        self.generated_code_view.setObjectName("PovSource")
        self.generated_code_view.setReadOnly(True)
        exercise_layout.addWidget(self.generated_code_view, 1)
        comparison.addWidget(exercise_card)
        comparison.setSizes([1, 1])
        outer.addWidget(comparison, 1)

        actions = QHBoxLayout()
        self.exercise_back_button = QPushButton()
        self.exercise_back_button.setObjectName("PovSecondary")
        self.exercise_back_button.clicked.connect(
            lambda: self.screens.setCurrentWidget(self.completion_screen)
        )
        actions.addWidget(self.exercise_back_button)
        actions.addStretch(1)
        self.start_exercise_button = QPushButton()
        self.start_exercise_button.setObjectName("PovPrimary")
        self.start_exercise_button.clicked.connect(self._start_generated_exercise)
        self.start_exercise_button.setEnabled(False)
        actions.addWidget(self.start_exercise_button)
        outer.addLayout(actions)
        self.screens.addWidget(self.exercise_screen)

    def retranslate(self) -> None:
        self.back_button.setText(tr("← Back to analysis"))
        self.nav_label.setText(
            tr("BE THE CODE · SAFE PRACTICE")
            if self._mode == "code"
            else tr("FUNCTION POV · SAFE PRACTICE")
        )
        self.code_mode_button.setText(tr("Be the Code"))
        self.function_mode_button.setText(tr("Be the Function"))
        self.entry_kicker.setText(
            tr("A PROGRAM IS A JOURNEY")
            if self._mode == "code"
            else tr("A FUNCTION IS A JOURNEY")
        )
        self.entry_title.setText(tr("Be the Code") if self._mode == "code" else tr("Be the Function"))
        self.entry_subtitle.setText(
            tr("Follow top-level statements, changing values, decisions, loops, and output. "
               "Prism uses a bounded simulation; it never runs your Python code.")
            if self._mode == "code"
            else tr("Choose a function, follow its values, and practise each decision. "
                    "Prism uses a bounded simulation; it never runs your Python code.")
        )
        self.selection_heading.setText(tr("CHOOSE A FUNCTION"))
        self.function_heading.setText(tr("Select a function"))
        self.function_description.setText(tr("Function details and arguments will appear here."))
        self.arguments_heading.setText(tr("ARGUMENTS · ENTER JSON VALUES"))
        self.support_note.setText(
            tr("Blank optional arguments use their defaults. Only a safe subset of Python is simulated.")
        )
        self.start_button.setText(tr("Enter function space"))
        self.selection_message.setText(tr("Select a supported function to begin."))
        self.source_heading.setText(tr("YOUR FUNCTION · CURRENT LINE HIGHLIGHTED"))
        self.stack_heading.setText(tr("CALL STACK"))
        self.variables_heading.setText(tr("LOCAL VARIABLES"))
        self.history_heading.setText(tr("ANSWER HISTORY"))
        self.previous_button.setText(tr("← Previous"))
        self.restart_button.setText(tr("↻ Restart"))
        self.hint_button.setText(tr("Hint"))
        self.answer_button.setText(tr("Show answer"))
        self.check_button.setText(tr("Check answer"))
        self.replay_button.setText(
            tr("↻ Replay program") if self._mode == "code" else tr("↻ Replay function")
        )
        self.similar_button.setText(tr("Practice Similar Questions"))
        self.completion_kicker.setText(tr("MISSION COMPLETE"))
        self.completion_title.setText(tr("Stage clear!"))
        self.exercise_title.setText(tr("Practice Similar Questions"))
        self.exercise_subtitle.setText(
            tr("Choose a practice level. The original source stays unchanged, and each new exercise is checked by Prism's safe simulator.")
        )
        self.new_values_button.setText(tr("New Values"))
        self.similar_logic_button.setText(tr("Similar Logic"))
        self.original_code_heading.setText(tr("Original exercise"))
        self.generated_code_heading.setText(tr("New exercise · compare before starting"))
        self.exercise_back_button.setText(tr("← Back to completion"))
        self.start_exercise_button.setText(tr("Start this exercise"))
        self._render_exercise_comparison()
        self._render_exercise_status()
        self._update_progress_labels()
        if self._unsupported_language:
            self.selection_message.setText(
                tr("Function POV currently supports Python only; this analysis uses {language}.",
                   language=self._unsupported_language)
            )
        else:
            self._update_selection_message()
        if self._simulation is not None:
            self._render_step()
        function = self._selected_function()
        if function is not None:
            self.function_description.setText(
                function.docstring or tr("No docstring is available for this function.")
            )
            advanced = False
            parameters = {parameter.name: parameter for parameter in function.parameters}
            for name, field in self._parameter_fields.items():
                parameter = parameters[name]
                field.setPlaceholderText(
                    tr("Leave blank to use default") if parameter.default is not None
                    else tr("Required JSON value")
                )
                advanced = advanced or parameter.kind != "positional_or_keyword"
            if advanced:
                self.support_note.setText(
                    tr("This function uses advanced parameter syntax. "
                       "Phase 1 supports simple positional parameters only.")
                )
            else:
                self.support_note.setText(
                    tr("Blank optional arguments use their defaults. "
                       "The simulation never executes your code.")
                )
            self._update_relationships(function)
        if self._completion_metrics is not None:
            self._render_completion_summary()
        self._apply_mode()

    def _apply_mode(self) -> None:
        code_mode = self._mode == "code"
        self.code_mode_button.setChecked(code_mode)
        self.function_mode_button.setChecked(not code_mode)
        language_supported = self._unsupported_language is None
        self.code_mode_button.setEnabled(language_supported and bool(self._source))
        self.function_mode_button.setEnabled(language_supported and bool(self._functions))
        self.function_list.setVisible(not code_mode)
        self.selection_heading.setText(
            tr("WHOLE PROGRAM") if code_mode else tr("CHOOSE A FUNCTION")
        )
        selected = self._selected_function()
        if code_mode:
            self.function_heading.setText(tr("Program"))
            self.function_description.setText(
                tr("Follow executable top-level statements from start to finish.")
            )
        elif selected is None:
            self.function_heading.setText(tr("Select a function"))
            self.function_description.setText(
                tr("Function details and arguments will appear here.")
            )
        else:
            self.function_heading.setText(selected.name)
            self.function_description.setText(
                selected.docstring or tr("No docstring is available for this function.")
            )
        self.relationships.setVisible(not code_mode)
        self.arguments_heading.setVisible(not code_mode)
        for row in range(self.parameter_form.rowCount()):
            for role in (
                QFormLayout.ItemRole.LabelRole,
                QFormLayout.ItemRole.FieldRole,
            ):
                item = self.parameter_form.itemAt(row, role)
                if item is not None and item.widget() is not None:
                    item.widget().setVisible(not code_mode)
        if code_mode:
            self.support_note.setText(
                tr("Only a bounded Python subset is simulated. Unsupported statements are explained before play.")
            )
            self.start_button.setText(tr("Trace whole program"))
            self.start_button.setEnabled(self._program_simulation is not None)
            self._update_selection_message()
        else:
            advanced = selected is not None and any(
                parameter.kind != "positional_or_keyword"
                for parameter in selected.parameters
            )
            if advanced:
                self.support_note.setText(
                    tr("This function uses advanced parameter syntax. "
                       "Phase 1 supports simple positional parameters only.")
                )
            else:
                self.support_note.setText(
                    tr("Blank optional arguments use their defaults. "
                       "The simulation never executes your code.")
                )
            self.start_button.setText(tr("Enter function space"))
            self.start_button.setEnabled(
                selected is not None and not advanced
            )
            self._update_selection_message()

    def set_source(self, source: str, filename: str) -> None:
        self._unsupported_language = None
        self._source = source
        self._exercise_generator = PracticeExerciseGenerator()
        self._practice_context = None
        self._pending_exercise = None
        self._active_exercise = None
        self._generation_status = ""
        candidate = Path(filename).name
        self._filename = candidate if Path(candidate).suffix.lower() == ".py" else "main.py"
        self._analysis = analyze_source(source, self._filename)
        self._functions = {function.id: function for function in self._analysis.functions}
        self._simulation = None
        self._original_simulation = None
        self._program_simulation = None
        self._program_error = None
        self._completion_metrics = None
        self._mode = "function" if self._functions else "code"
        self._parameter_fields.clear()
        self.function_list.clear()
        self.start_button.setEnabled(False)
        self.selection_error.hide()
        self.relationships.clear()
        self.function_heading.setText(tr("Select a function"))
        self.function_description.setText(tr("Function details and arguments will appear here."))
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)

        for function in self._functions.values():
            signature = ", ".join(
                parameter.name + (f"={parameter.default}" if parameter.default is not None else "")
                for parameter in function.parameters
            )
            item = QListWidgetItem(f"{function.name}({signature}) · L{function.line}")
            item.setData(Qt.ItemDataRole.UserRole, function.id)
            self.function_list.addItem(item)
        self.screens.setCurrentWidget(self.selection_screen)
        if self.function_list.count():
            self.function_list.setCurrentRow(0)

        self._prepare_code_simulation()
        self.retranslate()

    def _prepare_code_simulation(self) -> None:
        self._program_simulation = None
        self._program_error = None
        if self._unsupported_language is not None or not self._source:
            return
        try:
            self._program_simulation = build_program_simulation_from_source(
                self._source,
                self._filename,
            )
        except (SimulationError, ValueError, OSError) as error:
            self._program_error = str(error)

    def _select_mode(self, mode: str) -> None:
        if self._unsupported_language is not None:
            return
        self._mode = mode
        if mode == "code" and self._program_simulation is None and self._program_error is None:
            self._prepare_code_simulation()
        self.retranslate()

    def _update_selection_message(self) -> None:
        if self._analysis is None:
            return
        if self._mode == "code":
            if self._program_error:
                message = tr(
                    "This program is outside the safe simulation subset: {error}",
                    error=simulation_error_text(self._program_error),
                )
            else:
                message = tr(
                    "Ready for Be the Code. The simulator follows bounded steps and never executes your Python code."
                )
            self.selection_message.setText(message)
            return
        errors = [item for item in self._analysis.diagnostics if item.severity == "error"]
        if errors:
            message = tr(
                "Python syntax could not be analysed: {error}",
                error=simulation_error_text(errors[0].message),
            )
        elif not self._functions:
            message = tr("No top-level synchronous functions were found. "
                         "Function POV needs a regular def function to begin.")
        else:
            message = tr("This is a simplified, bounded simulation. "
                         "Unsupported syntax is explained before play.")
        warnings = [item for item in self._analysis.diagnostics if item.severity != "error"]
        if warnings:
            message += "\n" + tr(
                "Other structures may be outside the supported subset: {details}",
                details="; ".join(item.message for item in warnings[:3]),
            )
        self.selection_message.setText(message)

    def set_unsupported_language(self, language: str) -> None:
        self._unsupported_language = language
        self._source = ""
        self._exercise_generator = PracticeExerciseGenerator()
        self._practice_context = None
        self._pending_exercise = None
        self._active_exercise = None
        self._generation_status = ""
        self._filename = "main.py"
        self._analysis = None
        self._functions.clear()
        self._simulation = None
        self._original_simulation = None
        self._program_simulation = None
        self._program_error = None
        self._completion_metrics = None
        self._mode = "code"
        self.function_list.clear()
        self._parameter_fields.clear()
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self.function_heading.setText(tr("Select a function"))
        self.function_description.setText(tr("Function details and arguments will appear here."))
        self.relationships.clear()
        self.start_button.setEnabled(False)
        self.selection_error.hide()
        self.selection_message.setText(
            tr("Function POV currently supports Python only; this analysis uses {language}.",
               language=language)
        )
        self.retranslate()
        self.screens.setCurrentWidget(self.selection_screen)

    def _selected_function(self) -> FunctionInfo | None:
        item = self.function_list.currentItem()
        return self._functions.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _function_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self._parameter_fields.clear()
        self.selection_error.hide()
        if current is None:
            return
        function = self._functions.get(current.data(Qt.ItemDataRole.UserRole))
        if function is None:
            return
        self.function_heading.setText(function.name)
        self.function_description.setText(
            function.docstring or tr("No docstring is available for this function.")
        )
        self._update_relationships(function)

        advanced = False
        for parameter in function.parameters:
            field = QLineEdit()
            field.setMaxLength(MAX_JSON_INPUT_CHARS + 1)
            field.setPlaceholderText(
                tr("Leave blank to use default") if parameter.default is not None
                else tr("Required JSON value")
            )
            self.parameter_form.addRow(parameter.name, field)
            self._parameter_fields[parameter.name] = field
            if parameter.kind != "positional_or_keyword":
                advanced = True
        if not function.parameters:
            self.parameter_form.addRow(QLabel(tr("This function has no parameters.")))

        if advanced:
            self.support_note.setText(
                tr("This function uses advanced parameter syntax. "
                   "Phase 1 supports simple positional parameters only.")
            )
            self.start_button.setEnabled(False)
        else:
            self.support_note.setText(
                tr("Blank optional arguments use their defaults. "
                   "The simulation never executes your code.")
            )
            self.start_button.setEnabled(True)

    def _update_relationships(self, function: FunctionInfo) -> None:
        if len(self._functions) <= 1 or self._analysis is None:
            self.relationships.clear()
            return
        called = sorted({
            call.callee.split(".")[-1]
            for call in self._analysis.calls
            if call.caller == function.id
        })
        callers = sorted({
            call.caller.split(".")[-1]
            for call in self._analysis.calls
            if call.callee == function.id
        })
        self.relationships.setText(
            tr("Calls: {calls} · Called by: {callers}",
               calls=", ".join(called) or tr("none"),
               callers=", ".join(callers) or tr("none"))
        )

    def _start_simulation(self) -> None:
        selected_function_id: str | None = None
        arguments: dict[str, Any] = {}
        if self._mode == "code":
            if self._program_simulation is None:
                self._prepare_code_simulation()
            if self._program_error is not None or self._program_simulation is None:
                self.selection_error.setText(
                    tr(
                        "This program is outside the safe simulation subset: {error}",
                        error=(
                            simulation_error_text(self._program_error)
                            if self._program_error
                            else tr("No executable statements were found.")
                        ),
                    )
                )
                self.selection_error.show()
                self._update_selection_message()
                return
            self._simulation = self._program_simulation
        else:
            function = self._selected_function()
            if function is None:
                return
            selected_function_id = function.id
            for name, field in self._parameter_fields.items():
                entered = field.text()
                if len(entered) > MAX_JSON_INPUT_CHARS:
                    self.selection_error.setText(
                        tr(
                            "JSON input is too long (maximum {limit} characters).",
                            limit=MAX_JSON_INPUT_CHARS,
                        )
                    )
                    self.selection_error.show()
                    return
                raw = entered.strip()
                if not raw:
                    continue
                value, error = _decode_json_input(raw)
                if error == "invalid":
                    self.selection_error.setText(
                        tr("Enter {name} as a JSON value, such as 4, true, or \"hello\".",
                           name=name)
                    )
                    self.selection_error.show()
                    return
                if error == "too_long":
                    self.selection_error.setText(
                        tr(
                            "JSON input is too long (maximum {limit} characters).",
                            limit=MAX_JSON_INPUT_CHARS,
                        )
                    )
                    self.selection_error.show()
                    return
                if error == "unsafe":
                    self.selection_error.setText(
                        tr("This JSON value is too large, too deeply nested, or not finite.")
                    )
                    self.selection_error.show()
                    return
                arguments[name] = value
            try:
                self._simulation = build_simulation_from_source(
                    self._source,
                    function.id,
                    arguments,
                    self._filename,
                )
            except (SimulationError, ValueError, OSError) as error:
                self.selection_error.setText(
                    tr("This function is outside the safe simulation subset: {error}",
                       error=simulation_error_text(str(error)))
                )
                self.selection_error.show()
                return

        self._practice_context = (
            self._mode,
            selected_function_id,
            dict(arguments),
        )
        self._original_simulation = self._simulation
        self._active_exercise = None
        self._reset_practice_state()
        self.screens.setCurrentWidget(self.practice_screen)
        self._render_step()

    def _reset_practice_state(self) -> None:
        self._step_index = 0
        self._completion_metrics = None
        self._passed.clear()
        self._solved_by_attempt.clear()
        self._revealed.clear()
        self._history.clear()
        self._drafts.clear()

    def _open_exercise_screen(self) -> None:
        self._pending_exercise = None
        self._generation_status = ""
        if self._practice_context is None:
            self.similar_logic_button.setEnabled(False)
        else:
            mode, function_id, arguments = self._practice_context
            availability = self._exercise_generator.similar_logic_availability(
                mode,
                self._source,
                self._filename,
                function_id,
                arguments,
            )
            self.similar_logic_button.setEnabled(availability is None)
            self._generation_status = availability or ""
        self.original_code_view.setPlainText(self._source)
        self.generated_code_view.clear()
        self._render_exercise_comparison()
        self.start_exercise_button.setEnabled(False)
        self._render_exercise_status()
        self.screens.setCurrentWidget(self.exercise_screen)

    def _generate_exercise(self, level: str) -> None:
        if self._practice_context is None:
            self._generation_status = "Complete an original practice first to create a similar exercise."
            self._pending_exercise = None
            self.start_exercise_button.setEnabled(False)
            self._render_exercise_status()
            return
        mode, function_id, arguments = self._practice_context
        try:
            exercise = self._exercise_generator.generate(
                level,
                mode,
                self._source,
                self._filename,
                function_id,
                arguments,
            )
        except ExerciseGenerationError as error:
            self._generation_status = str(error)
            self._pending_exercise = None
            self.start_exercise_button.setEnabled(False)
            self.generated_code_view.clear()
            self._render_exercise_comparison()
            if level == "similar_logic" and self._practice_context is not None:
                mode, function_id, arguments = self._practice_context
                availability = self._exercise_generator.similar_logic_availability(
                    mode,
                    self._source,
                    self._filename,
                    function_id,
                    arguments,
                )
                self.similar_logic_button.setEnabled(availability is None)
            self._render_exercise_status()
            return
        self._pending_exercise = exercise
        self._generation_status = ""
        self.generated_code_view.setPlainText(exercise.source)
        self._render_exercise_comparison()
        self.start_exercise_button.setEnabled(True)
        if self._practice_context is not None:
            mode, function_id, arguments = self._practice_context
            availability = self._exercise_generator.similar_logic_availability(
                mode,
                self._source,
                self._filename,
                function_id,
                arguments,
            )
            self.similar_logic_button.setEnabled(availability is None)
        self._render_exercise_status()

    def _render_exercise_comparison(self) -> None:
        function_mode = (
            self._practice_context is not None
            and self._practice_context[0] == "function"
        )
        self.original_inputs_label.setVisible(function_mode)
        self.generated_inputs_label.setVisible(
            function_mode and self._pending_exercise is not None
        )
        if function_mode:
            self.original_inputs_label.setText(
                tr(
                    "Original arguments: {values}",
                    values=self._format_value(
                        self._simulation_input_values(self._original_simulation)
                    ),
                )
            )
        else:
            self.original_inputs_label.clear()
        if function_mode and self._pending_exercise is not None:
            self.generated_inputs_label.setText(
                tr(
                    "New arguments: {values}",
                    values=self._format_value(
                        self._simulation_input_values(
                            self._pending_exercise.simulation
                        )
                    ),
                )
            )
        else:
            self.generated_inputs_label.clear()

    @staticmethod
    def _simulation_input_values(simulation: PovSimulation | None) -> dict[str, Any]:
        if simulation is None:
            return {}
        entry = next(
            (
                step for step in simulation.steps
                if step.kind == "enter"
                and step.function_id == simulation.function_id
            ),
            None,
        )
        return dict(entry.variables) if entry is not None else {}

    def _render_exercise_status(self) -> None:
        if self._pending_exercise is not None:
            level = (
                tr("New Values")
                if self._pending_exercise.level == "new_values"
                else tr("Similar Logic")
            )
            concepts = ", ".join(
                tr(concept) for concept in self._pending_exercise.concepts
            )
            self.exercise_status.setText(
                tr(
                    "Generated {level} exercise. Concepts: {concepts}. "
                    "The candidate passed safe simulation.",
                    level=level,
                    concepts=concepts or tr("related Python concepts"),
                )
            )
            if self._pending_exercise.logic_change:
                self.exercise_status.setText(
                    self.exercise_status.text()
                    + "\n"
                    + tr(
                        "Logic change: {explanation}",
                        explanation=tr(self._pending_exercise.logic_change),
                    )
                )
        elif self._generation_status:
            self.exercise_status.setText(tr(self._generation_status))
        else:
            self.exercise_status.setText(
                tr("Choose a level to generate a verified practice exercise.")
            )

    def _start_generated_exercise(self) -> None:
        if self._pending_exercise is None:
            return
        self._active_exercise = self._pending_exercise
        self._simulation = self._pending_exercise.simulation
        self._mode = self._pending_exercise.mode
        self._reset_practice_state()
        self.screens.setCurrentWidget(self.practice_screen)
        self._render_step()

    def _current_step(self):
        if self._simulation is None:
            return None
        return self._simulation.steps[self._step_index]

    def _render_step(self) -> None:
        step = self._current_step()
        if step is None:
            return
        total = len(self._simulation.steps)
        if self._simulation.mode == "code":
            self.progress_label.setText(
                tr("PROGRAM STEP {current} OF {total}",
                   current=self._step_index + 1, total=total)
            )
        else:
            self.progress_label.setText(
                tr("STEP {current} OF {total} · {function}",
                   current=self._step_index + 1, total=total, function=step.function_name)
            )
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(self._step_index + 1)
        source = self._simulation.sources[step.function_id]
        if self._simulation.mode == "code":
            self.source_heading.setText(
                tr("WHOLE PROGRAM · {file}", file=source["file"])
            )
            self.stack_heading.setText(tr("PROGRAM CALL STACK"))
            self.variables_heading.setText(tr("PROGRAM VARIABLES"))
        else:
            self.source_heading.setText(
                tr("{function} · {file}",
                   function=step.function_name, file=source["file"])
            )
            self.stack_heading.setText(tr("CALL STACK"))
            self.variables_heading.setText(tr("LOCAL VARIABLES"))
        self._set_highlighted_source(source["source"], source["line"], step.line)
        self.step_prompt.setText(
            self._prompt_for(
                step.kind, step.function_name, step.target, step.expression
            )
        )
        self.expression_label.setText(step.expression or tr("Follow the current function state."))
        self.stack_list.clear()
        for frame in step.stack:
            values = ", ".join(
                f"{name}={self._format_value(value)}"
                for name, value in frame.get("variables", {}).items()
            )
            self.stack_list.addItem(
                f"{frame.get('function_name', '')}({values})"
            )
        self.variables_list.clear()
        for name, value in step.variables.items():
            self.variables_list.addItem(f"{name} = {self._format_value(value)}")
        self._render_challenge(step)
        self.previous_button.setEnabled(self._step_index > 0)
        self.restart_button.setEnabled(True)
        can_continue = not step.challenge or self._step_index in self._passed
        self.next_button.setEnabled(can_continue)
        self.next_button.setText(
            tr("Finish ✓") if self._step_index == total - 1 else tr("Next →")
        )
        self.hint_button.setEnabled(step.challenge and self._step_index not in self._passed)
        self.answer_button.setEnabled(step.challenge and self._step_index not in self._passed)

    def _prompt_for(
        self,
        kind: str,
        function: str,
        target: str | None,
        expression: str = "",
    ) -> str:
        if kind == "program_start":
            return tr("Predict the first meaningful operation.")
        if kind == "program_end":
            return tr("The program finished. Review its final output.")
        if kind == "enter":
            return tr("You are now {function}. The caller passed these arguments.", function=function)
        if kind == "arithmetic":
            return tr("Work out the value assigned to {target}.", target=target or "")
        if kind == "assignment":
            return tr("State update: {expression}", expression=expression)
        if kind == "loop_condition" and target:
            return tr("Will the for loop execute another pass?")
        if kind in {"condition", "loop_condition"}:
            return tr("Does this condition evaluate to True or False?")
        if kind == "loop_value":
            return tr("What value is assigned to {target} in the next loop pass?", target=target or "")
        if kind == "iteration":
            return tr("Loop state: {expression}", expression=expression)
        if kind == "output":
            return tr("What text does this print call output?")
        if kind == "next_operation":
            return tr("Predict the first meaningful operation.")
        if kind == "function_call":
            return tr("Which project function is being called here?")
        if kind == "call_return":
            return tr("The called function returned. Its value is back with you.")
        if kind == "return":
            return tr("What value does {function} return to its caller?", function=function)
        return tr("Follow the highlighted line, then continue.")

    def _set_highlighted_source(self, source: str, first_line: int, active_line: int) -> None:
        self.source_view.setPlainText(source)
        block_number = max(0, active_line - first_line)
        cursor = QTextCursor(self.source_view.document())
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for _ in range(block_number):
            if not cursor.movePosition(QTextCursor.MoveOperation.NextBlock):
                break
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        selection.format.setBackground(QColor("#51402d"))
        selection.format.setForeground(QColor("#fff2df"))
        self.source_view.setExtraSelections([selection])

    def _render_challenge(self, step) -> None:
        self.feedback_label.hide()
        self.hint_label.hide()
        self.history_list.clear()
        for record in self._history.get(self._step_index, []):
            if record["kind"] == "attempt":
                status = tr("Correct") if record["correct"] else tr("Try again")
                text = tr("Attempt {number}: {answer} · {status}",
                          number=record["number"], answer=record["answer"], status=status)
            else:
                text = tr("Answer revealed: {answer}", answer=record["answer"])
            self.history_list.addItem(text)
        if not step.challenge:
            note = tr("Follow the highlighted line. Continue when you are ready.")
            if step.kind == "enter":
                note = tr("Review the caller's values and local state, then continue.")
            elif step.kind == "call_return":
                note = tr("The nested call has returned. Continue with the result shown.")
            elif step.kind == "assignment":
                note = tr("State updated: {state}", state=step.expression)
            elif step.kind == "iteration":
                note = tr("Loop pass state: {state}", state=step.expression)
            elif step.kind == "program_end":
                output = self._simulation.output.rstrip("\n") if self._simulation else ""
                note = tr("Program output: {output}", output=output or tr("No output was produced."))
            elif step.kind == "program_start":
                note = tr("Review the source before the first operation.")
            self.challenge_prompt.setText(note)
            self.answer_row.hide()
            self.choice_row.hide()
            return

        prompt = {
            "arithmetic": tr("Calculate the result using the values shown."),
            "condition": tr("Choose the branch that matches this condition."),
            "loop_condition": tr("Choose whether the loop continues or stops."),
            "loop_value": tr("Enter the next loop value as a JSON value."),
            "function_call": tr("Choose the function called at this line."),
            "program_start": tr("Choose the first meaningful operation in the program."),
            "next_operation": tr("Choose the first meaningful operation in the program."),
            "output": tr("Enter the printed text as a JSON string."),
            "return": tr("Enter the value being returned. Use JSON for text or collections."),
        }.get(step.kind, tr("Enter your answer as a JSON value."))
        self.challenge_prompt.setText(prompt)
        passed = self._step_index in self._passed
        self.answer_edit.setText(self._drafts.get(self._step_index, ""))
        self.answer_edit.setEnabled(not passed)
        self.check_button.setEnabled(not passed)

        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if step.kind in {
            "condition", "loop_condition", "function_call", "program_start",
            "next_operation",
        }:
            self.answer_row.hide()
            self.choice_row.show()
            options = (
                ["True", "False"]
                if step.kind in {"condition", "loop_condition"}
                else step.choices
            )
            for option in options:
                button = QPushButton(self._choice_label(step.kind, option))
                button.setObjectName("PovSecondary")
                button.setEnabled(not passed)
                button.clicked.connect(
                    lambda _checked=False, value=option, kind=step.kind:
                    self._submit_answer(
                        value == "True"
                        if kind in {"condition", "loop_condition"}
                        else value,
                        self._choice_label(kind, value),
                    )
                )
                self.choice_layout.addWidget(button)
        else:
            self.choice_row.hide()
            self.answer_row.show()
        if passed:
            self.feedback_label.setText(
                tr("This challenge is complete. You can review your answer history.")
            )
            self.feedback_label.show()

    @staticmethod
    def _choice_label(kind: str, option: str) -> str:
        if kind in {"condition", "loop_condition"}:
            return tr("True") if option == "True" else tr("False")
        if kind in {"program_start", "next_operation"}:
            return {
                "branch": tr("Branch decision"),
                "loop": tr("Loop iteration"),
                "variable update": tr("Variable update"),
                "function call": tr("Function call"),
                "output": tr("Output"),
            }.get(option, option)
        return option

    def _submit_text_answer(self) -> None:
        raw = self.answer_edit.text().strip()
        self._drafts[self._step_index] = raw
        if not raw:
            self._show_feedback(tr("Enter an answer before checking it."), False)
            return
        value, error = _decode_json_input(raw)
        if error == "invalid":
            self._show_feedback(
                tr("Use a JSON value: for example 4, true, or \"hello\"."),
                False,
            )
            return
        if error == "too_long":
            self._show_feedback(
                tr(
                    "JSON input is too long (maximum {limit} characters).",
                    limit=MAX_JSON_INPUT_CHARS,
                ),
                False,
            )
            return
        if error == "unsafe":
            self._show_feedback(
                tr("This JSON value is too large, too deeply nested, or not finite."),
                False,
            )
            return
        self._submit_answer(value, raw)

    def _submit_answer(self, value: Any, display: str) -> None:
        if self._simulation is None:
            return
        step = self._current_step()
        if step is None or not step.challenge or self._step_index in self._passed:
            return
        result = self._simulation.check(self._step_index, value)
        records = self._history.setdefault(self._step_index, [])
        records.append({
            "kind": "attempt",
            "number": sum(record["kind"] == "attempt" for record in records) + 1,
            "answer": display,
            "correct": result["correct"],
        })
        if result["correct"]:
            self._passed.add(self._step_index)
            self._solved_by_attempt.add(self._step_index)
        self._render_step()
        if result["correct"]:
            self._show_feedback(
                tr("Correct. {answer} is the value for this step.",
                   answer=self._format_value(result.get("answer"))),
                True,
            )
        else:
            feedback = {
                "arithmetic": tr(
                    "Not quite. Substitute the current values, then apply the operator. "
                    "For an update, start with the variable's previous value."
                ),
                "condition": tr(
                    "Not quite. Evaluate the comparison with the values shown, then follow "
                    "the matching True or False branch."
                ),
                "loop_value": tr(
                    "Not quite. Read the iterable from left to right; each loop pass uses "
                    "the next value, not the previous one."
                ),
                "loop_condition": tr(
                    "Not quite. Re-evaluate the loop condition with the updated variables "
                    "to decide whether another iteration occurs."
                ),
                "output": tr(
                    "Not quite. Evaluate each print argument in order, convert the values "
                    "to text, and join them with spaces."
                ),
                "return": tr(
                    "Not quite. Evaluate the return expression using this function's local "
                    "variables; that value is passed back to the caller."
                ),
                "function_call": tr(
                    "Not quite. Match the called function name, then trace how its arguments "
                    "become local parameter values."
                ),
                "program_start": tr(
                    "Not quite. Look past simple assignments for the first decision, loop, update, call, or output."
                ),
                "next_operation": tr(
                    "Not quite. Look past simple assignments for the first decision, loop, update, call, or output."
                ),
            }.get(
                step.kind,
                tr("Not quite. Compare your answer with the highlighted expression and current values, then try again."),
            )
            if step.kind == "loop_condition" and step.target:
                feedback = tr(
                    "Not quite. Check whether another value remains in the iterable."
                )
            self._show_feedback(feedback, False)

    def _show_feedback(self, message: str, correct: bool) -> None:
        self.feedback_label.setText(message)
        self.feedback_label.setStyleSheet(
            "color: #a8e8d0; background: #1c302c; border: 1px solid #3b7568; "
            "border-radius: 6px; padding: 8px;"
            if correct else ""
        )
        self.feedback_label.show()

    def _show_hint(self) -> None:
        step = self._current_step()
        if step is None or not step.challenge or self._simulation is None:
            return
        hint = {
            "arithmetic": tr("Substitute the local values into the expression, then follow operator order."),
            "condition": tr("Substitute the local values and compare them to choose the matching branch."),
            "loop_value": tr("Follow the iterable from left to right and find the next value."),
            "output": tr("Evaluate each print argument, convert it to text, then join them with spaces."),
            "next_operation": tr("Skip simple assignments and find the first decision, loop, update, call, or output."),
            "program_start": tr("Skip simple assignments and find the first decision, loop, update, call, or output."),
            "function_call": tr("Look at the function name immediately before the parentheses."),
            "return": tr("Evaluate the return expression using the local variables shown."),
        }.get(step.kind, self._simulation.hint(self._step_index))
        if step.kind == "loop_condition":
            hint = (
                tr("Check whether any values remain in the iterable.")
                if step.target
                else tr("Substitute the current values into the while condition.")
            )
        self.hint_label.setText(hint)
        self.hint_label.show()

    def _show_answer(self) -> None:
        if self._simulation is None:
            return
        step = self._current_step()
        if step is None or not step.challenge or self._step_index in self._passed:
            return
        answer = self._simulation.answer(self._step_index)
        display = self._format_value(answer)
        self._history.setdefault(self._step_index, []).append({
            "kind": "reveal",
            "answer": display,
        })
        self._revealed.add(self._step_index)
        self._passed.add(self._step_index)
        self._render_step()
        self._show_feedback(
            tr("Answer: {answer}. Review the highlighted line before continuing.",
               answer=display),
            True,
        )

    def _previous_step(self) -> None:
        if self._step_index > 0:
            if self.answer_edit.isVisible():
                self._drafts[self._step_index] = self.answer_edit.text()
            self._step_index -= 1
            self._render_step()

    def _next_step(self) -> None:
        step = self._current_step()
        if step is None or (step.challenge and self._step_index not in self._passed):
            return
        if self._step_index == len(self._simulation.steps) - 1:
            self._complete()
            return
        if self.answer_edit.isVisible():
            self._drafts[self._step_index] = self.answer_edit.text()
        self._step_index += 1
        self._render_step()

    def _restart(self) -> None:
        if self._simulation is None:
            return
        self._step_index = 0
        self._completion_metrics = None
        self._passed.clear()
        self._solved_by_attempt.clear()
        self._revealed.clear()
        self._history.clear()
        self._drafts.clear()
        self.screens.setCurrentWidget(self.practice_screen)
        self._render_step()

    def _complete(self) -> None:
        if self._simulation is None:
            return
        challenges = [index for index, step in enumerate(self._simulation.steps) if step.challenge]
        attempts = sum(
            record["kind"] == "attempt"
            for history in self._history.values()
            for record in history
        )
        self._completion_metrics = {
            "entry_name": self._simulation.entry_name,
            "total": len(challenges),
            "solved": len(self._solved_by_attempt),
            "revealed": len(self._revealed),
            "attempts": attempts,
            "value": self._final_return_value(),
            "output": self._simulation.output.rstrip("\n"),
            "variables": self._format_value(self._simulation.final_variables),
            "practice_level": (
                self._active_exercise.level if self._active_exercise else None
            ),
            "concepts": (
                self._active_exercise.concepts if self._active_exercise else ()
            ),
        }
        self._render_completion_summary()
        self.screens.setCurrentWidget(self.completion_screen)

    def _render_completion_summary(self) -> None:
        if self._completion_metrics is None:
            return
        metrics = self._completion_metrics
        practice_summary = ""
        if metrics["practice_level"]:
            level = (
                tr("New Values")
                if metrics["practice_level"] == "new_values"
                else tr("Similar Logic")
            )
            concepts = ", ".join(tr(concept) for concept in metrics["concepts"])
            practice_summary = "\n" + tr(
                "Practice level: {level} · Concepts: {concepts}",
                level=level,
                concepts=concepts,
            )
        if self._simulation is not None and self._simulation.mode == "code":
            output = metrics["output"] or tr("No output was produced.")
            if len(output) > 1600:
                output = output[:1600] + "\n" + tr("Output shortened for display.")
            self.completion_summary.setText(
                tr("Mode: Be the Code\nChallenges: {total} · Solved by you: {solved} · "
                   "Answers revealed: {revealed} · Attempts: {attempts}{practice}\n"
                   "Final output:\n{output}\nFinal variables: {variables}",
                   total=metrics["total"],
                   solved=metrics["solved"],
                   revealed=metrics["revealed"],
                   attempts=metrics["attempts"],
                   practice=practice_summary,
                   output=output,
                   variables=metrics["variables"])
            )
        else:
            function_name = metrics["entry_name"]
            self.completion_summary.setText(
                tr("Function: {function}\nChallenges: {total} · Solved by you: {solved} · "
                   "Answers revealed: {revealed} · Attempts: {attempts}{practice}\nFinal return value: {value}",
                   function=function_name,
                   total=metrics["total"],
                   solved=metrics["solved"],
                   revealed=metrics["revealed"],
                   attempts=metrics["attempts"],
                   practice=practice_summary,
                   value=metrics["value"])
            )

    def _final_return_value(self) -> str:
        if self._simulation is None:
            return tr("No explicit return value.")
        return_steps = [
            index for index, step in enumerate(self._simulation.steps)
            if step.kind == "return" and step.function_id == self._simulation.function_id
        ]
        if not return_steps:
            return tr("No explicit return value.")
        return self._format_value(self._simulation.answer(return_steps[-1]))

    def _update_progress_labels(self) -> None:
        step = self._current_step()
        if step is None:
            self.progress_label.setText(tr("FUNCTION POV"))

    @staticmethod
    def _format_value(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
