"""Regression tests for the Flowchart view's viewport fitting."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtTest, QtWidgets

from python_app.analysis import analyze_python
from python_app.native_app import FlowchartView


class FlowchartViewportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.analysis = analyze_python(
            "for price in [12, 8, 25]:\n"
            "    if price >= 10:\n"
            "        print(price)\n"
        )["analysis"]

    def make_view(self):
        window = QtWidgets.QMainWindow()
        stack = QtWidgets.QStackedWidget()
        stack.addWidget(QtWidgets.QWidget())
        view = FlowchartView()
        stack.addWidget(view)
        window.setCentralWidget(stack)
        window.resize(1000, 800)
        window.show()
        self.app.processEvents()
        view.resize(320, 240)
        view.set_analysis(self.analysis)
        return window, stack, view

    def expected_fit_scale(self, view: FlowchartView) -> float:
        bounds = view.scene().itemsBoundingRect().adjusted(-20, -20, 20, 20)
        viewport = view.viewport().size()
        return min(viewport.width() / bounds.width(), viewport.height() / bounds.height())

    def assert_fitted_to_viewport(self, view: FlowchartView) -> None:
        expected = self.expected_fit_scale(view)
        self.assertAlmostEqual(
            view.transform().m11(),
            expected,
            delta=expected * 0.03,
        )

    def test_refits_after_hidden_flowchart_becomes_visible(self) -> None:
        window, stack, view = self.make_view()
        self.addCleanup(window.close)

        old_scale = view.transform().m11()
        stack.setCurrentWidget(view)
        QtTest.QTest.qWait(50)

        self.assertTrue(view.isVisible())
        self.assertNotAlmostEqual(old_scale, self.expected_fit_scale(view), delta=0.05)
        self.assert_fitted_to_viewport(view)

    def test_refits_when_viewport_is_resized(self) -> None:
        window, stack, view = self.make_view()
        self.addCleanup(window.close)
        stack.setCurrentWidget(view)
        QtTest.QTest.qWait(50)
        initial_scale = view.transform().m11()

        window.resize(720, 520)
        QtTest.QTest.qWait(50)

        self.assertNotAlmostEqual(initial_scale, view.transform().m11(), delta=0.05)
        self.assert_fitted_to_viewport(view)

    def test_end_displays_output_and_partial_status(self):
        window, stack, view = self.make_view()
        self.addCleanup(window.close)
        for source, expected in (("print(2 ** 3)", "Output: 8"),
                                 ("print(1)\nprint(missing)", "Partial output: 1")):
            result = analyze_python(source)
            view.set_analysis(result["analysis"], result["trace"])
            texts = [item.text() for item in view.scene().items() if hasattr(item, "text")]
            self.assertIn(expected, texts)


if __name__ == "__main__":
    unittest.main()
