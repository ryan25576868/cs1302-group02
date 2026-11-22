# Prism

**A native Python workspace for understanding code.**

Prism turns a source file into a linked set of views—flow, syntax, execution, and data—and explains the program in plain English. It is built for beginners, runs entirely on the local machine, and is implemented with **PySide6** rather than a browser runtime.

![Prism welcome screen](screenshots/native-welcome.png)

## Highlights

- **Six languages** — Python, JavaScript, TypeScript, Java, C++, and C.
- **Four linked views** — Flowchart, Syntax Tree, Live Trace, and Data Flow.
- **Structural compare** — diff two versions of one file by classes and functions instead of by lines, powered by [structscope](https://pypi.org/project/structscope/).
- **Beginner's guide** — overview, mental model, step-by-step walkthrough, line-by-line notes, concepts, common mistakes, and a quick check.
- **Function POV** — practise whole-program or function execution with a bounded, non-executing simulator, interactive challenges, and verified similar exercises.
- **Native motion** — page and tab transitions, sequenced flowchart nodes, trace-detail fades, and a drifting welcome illustration.
- **Optional AI** — add a second explanation with OpenAI-compatible, DeepSeek, Grok, Anthropic, or Gemini. Local analysis needs no AI.
- **Bilingual interface** — switch between English and 简体中文 from the top bar; the window re-labels itself without a restart.
- **Local-first** — source code is parsed and simulated in-process. No account, telemetry, or browser tab required.
- **Source-only** — the project is a Python application, not a web wrapper.

## Supported languages

| Language | Parser | Analysis module |
| --- | --- | --- |
| Python | Python `ast` | `python_app/analysis.py` |
| JavaScript | tree-sitter | `python_app/js_analysis.py` |
| TypeScript | tree-sitter | `python_app/js_analysis.py` |
| Java | tree-sitter | `python_app/compiled_analysis.py` |
| C++ | tree-sitter | `python_app/compiled_analysis.py` |
| C | tree-sitter | `python_app/compiled_analysis.py` |

The trace is a safe, bounded interpreter—not an execution of the original program. It covers common beginner constructs such as variables, arithmetic, conditions, loops, functions, returns, and print output. See [Limitations](#limitations) for the deliberately excluded surface.

## Quick start

Requires **Python 3.11 or newer** on Windows.

```powershell
python -m pip install -r python_app\requirements.txt
python python_app\launch_native.py
```

No installer is included; this is the source-only distribution.

The app opens with a blank document. Choose a language, then:

- **Open editor** to write code.
- **Import file** to load a source file.
- **Try a case** to start from a small example.
- **Compare versions** to diff two versions of one file by structure.

## Usage

1. Select a language from the welcome screen.
2. Open the editor, import a file, or load an example.
3. Press **Visualize & explain**.
4. Explore the results:

   - **Flowchart** — follow decisions, loops, and the order of statements.
   - **Syntax Tree** — inspect the structural tree of the parsed program.
   - **Live Trace** — step through values, variables, output, and loop iterations.
   - **Data Flow** — see assignments and the names they depend on.
   - **Guide** — read the generated explanation from top to bottom.

5. Use **Enhance guide** to request an optional AI explanation.
6. Use **Save guide** to export the generated guide as Markdown.

For Python analyses, choose **Function POV** beside the result actions to open
the **Be the Code** and **Be the Function** modes. Be the Code follows
top-level statements even when there are no functions; Be the Function lets you
select a function and enter JSON arguments, with blank optional values using
their defaults. Both modes reuse the same challenges, hints, answer history,
source highlighting, variable and call-stack views, and completion summary.
Prism validates a restricted AST subset before play and simulates it without
executing the source. After completing a practice, choose **Practice Similar
Questions** for **New Values** or **Similar Logic**. New Values changes
supported literal inputs or function arguments while keeping the original AST
structure and source intact. It prefers coordinated numeric changes and, for
simple comparisons, values near branch boundaries. Similar Logic uses a small
catalog of beginner-friendly, predefined patterns and requires an AST logic
change beyond renamed variables or changed literals. It also explains the
concept being practised. Generated code is parsed and simulated before it is
shown; each session avoids repeating the same variant. The side-by-side preview
keeps the original exercise available for comparison.

![Java analysis in Prism](screenshots/native-java.png)

## Interface language

The language box in the top-left of the window switches the interface between
English and 简体中文. The choice applies immediately — menus, buttons, status
lines and dialogs are re-labelled in place, with no restart — and is remembered
for the next launch.

Strings live in `python_app/i18n.py` as one dictionary per language, keyed by the
English text. Adding a language means adding one dictionary; a test walks the UI
modules and fails when a `tr(...)` string has no translation, so the table cannot
silently drift behind the interface. Code-level names (Python, Java, C++) stay
untranslated on purpose, and the explanation text Prism generates for a program
remains in English.

## Compare two versions

Prism can diff two versions of the same file by **structure** instead of by
lines. Open **Compare versions** on the welcome screen, or use
**Tools → Compare two versions…** (`Ctrl+D`).

1. Pick the language, then choose a *before* file and an *after* file — or
   press **Sample pair** to load the bundled example for Python or Java.
2. Press **Compare**.
3. Read the map: every class, function and method appears twice — once per
   version — joined by a curve when the two sides matched.

| Colour | Meaning |
| --- | --- |
| green | added in the after version |
| red | removed from the before version |
| amber | same symbol, changed body or signature |
| blue | same body, different name (moved) |
| grey | unchanged |

Card width tracks the number of code lines, and the complexity badge appears
when a symbol got more or less branching. Hover a card to lift it, light up its
partner on the other side and dim everything else — the pair you are looking at
stays readable however crowded the map gets. Click any card to see the two
excerpts aligned line by line, with added, removed and replaced lines toned
differently. The filter next to the language box dims everything except one
status, which makes "what actually changed" readable at a glance.

The diff itself comes from [structscope](https://pypi.org/project/structscope/),
a small library that matches symbols across two parses. Prism already builds
the trees, so no second parser is involved: `compare_engine.py` adapts Prism's
analysis trees into structscope's symbol model.

If `structscope` is not installed the Compare page explains what to run:

```console
pip install structscope
```

While working on both projects side by side, install the checkout instead:

```console
pip install -e ..\structdiff
```

## Optional AI

Open **Connect AI** in the top bar, or **Tools → Connect AI**.

| Provider | Base URL | Default model |
| --- | --- | --- |
| OpenAI / compatible | `https://api.openai.com/v1` | `gpt-6.1-terra` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-flash` |
| Grok (xAI) | `https://api.x.ai/v1` | `grok-4.7` |
| Anthropic | `https://api.anthropic.com` | `claude-fable-5-2` |
| Google Gemini | `https://generativelanguage.googleapis.com` | `gemini-4-hydrogen` |

Model IDs change frequently. The model field is editable, so use the identifier published by your provider.

1. Choose a provider.
2. Confirm the base URL and model.
3. Enter an API key when the provider requires one.
4. Use **Test connection**.
5. Press **Save**, then **Enhance guide** from the results header.

The request is sent only when you explicitly test a connection or enhance a guide. The key is used for that request and is not written to logs. **Remember the key on this device** stores it in the local Qt settings store.

## Architecture

```text
python_app/
  native_app.py          PySide6 window, editor, views, guide, dialogs
  analysis.py            Python AST analysis, safe trace, guide generator
  js_analysis.py         tree-sitter JavaScript/TypeScript analysis and trace
  compiled_analysis.py   tree-sitter Java/C++/C analysis and trace
  compare.py             Compare page: two-version map and aligned excerpts
  compare_engine.py      Prism trees -> structscope symbol model, structural diff
  function_pov/          Restricted Python analyzer, simulator, and exercise generator
  function_pov_ui.py     Native Function POV selection and practice screens
  i18n.py                Interface strings: English source text + translations
  ai.py                  Optional AI provider calls and validation
  launch_native.py       Application entry point
  requirements.txt       PySide6 and tree-sitter grammars
tests_py/
  test_analysis.py
  test_javascript.py
  test_compiled.py
  test_ai.py
  test_compare.py
  test_i18n.py
samples/                 before/after pairs used by the Compare page
assets/                  Application icon
screenshots/             Native app screenshots
```

### Design principles

- **One process, one language.** The UI, parser adapters, trace engines, guide generator, and AI calls are all Python.
- **Native rendering.** Diagrams are drawn with `QGraphicsScene`; the editor, trees, tables, and guide are native Qt widgets.
- **Bounded execution.** Traces have step, loop, and source-size limits. Unsupported constructs stop the trace rather than producing invented values.
- **No browser runtime.** There is no HTML/CSS/JS application layer, no Electron, and no Node dependency.
- **Local by default.** AI is an optional outbound request, never a background process.

## Tests

```powershell
python -m unittest discover -s tests_py -v
```

**85 tests discovered: 78 passed, 7 skipped, 0 failed.** The 7 structural-compare tests are skipped when the optional `structscope` package is unavailable. Coverage includes Python, JavaScript, TypeScript, Java, C++, and C analysis; trace output; guide generation; syntax errors; AI settings validation; empty input; Be the Code and Be the Function's bounded simulations and native UI flow; deterministic and duplicate-safe similar exercises; Flowchart viewport fitting; and translated interface strings. The structural-compare tests cover model mapping, statuses, renames, and line alignment when `structscope` is installed.

## Troubleshooting

- **`ModuleNotFoundError: PySide6` or `tree_sitter`** — install the requirements with `python -m pip install -r python_app\requirements.txt`.
- **No source file imports** — use the file dialog or drag support is intentionally not implemented in this native edition; use **Import file**.
- **Trace stops early** — the code uses a construct outside the bounded beginner subset. The structural views and guide remain available.
- **AI connection fails** — verify the base URL, model ID, API key, and network access. The local guide does not depend on AI.

## Limitations

- The compiled-language trace supports a beginner subset. Complex generics, pointer arithmetic, macros, multithreading, and exception-heavy Java are not fully interpreted.
- JavaScript and TypeScript coverage is intentionally conservative; some higher-order and dynamic constructs are outside the trace subset.
- Function POV is Python-only. Be the Code supports simple top-level assignments and updates, expressions, nested `if/else`, bounded `for`/`while`, safe built-ins, direct project-function calls, and `print` output. Be the Function supports simple positional parameters, assignments, conditions, bounded loops, direct calls, and returns. Imports, classes, async/nested functions, decorated functions, advanced parameters, arbitrary attributes, file/network access, and other side effects are not simulated. Simulations cap source size, AST nodes, steps, call depth, values, output, and total loop iterations; unsupported behavior is rejected before play.
- Practice Similar Questions is limited to safe literal input changes for top-level scalar/list/tuple assignments, simple JSON scalar/list/tuple function arguments, and integer `range` bounds. New Values preserves the AST structure; branch-focused candidates are currently limited to simple numeric comparisons against literals or known inputs, including loop variables over numeric lists/tuples. Similar Logic requires a normalized AST difference in an operator, expression, or control-flow structure; renaming identifiers or changing literals alone is rejected. Its supported patterns are Be the Code list-accumulation loops (with or without one condition), bounded counter `while` loops, and simple conditional output; Be the Function list-accumulation loops with returns, one- or two-parameter branch/return functions, simple arithmetic returns, and a direct helper call followed by arithmetic. Multi-function Be the Code programs remain unsupported for Similar Logic. Other structures, multiple interacting patterns, unsupported defaults, or exhausted variants are explained rather than approximated. Every candidate must pass the same restricted AST simulator before display.
- The flow and data views are explanatory diagrams, not compiler-grade control-flow graphs or SSA.
- Source snippets are capped at 60,000 characters.
- AI output depends on the selected provider and model. The local guide remains available if a request fails.
- The app targets Windows 10/11 x64.

## More screenshots

### Beginner's guide

![Prism guide](screenshots/native-guide.png)

### Optional AI settings

![Prism AI settings](screenshots/native-ai-settings.png)
## Motivation

Beginners learning programming often struggle to understand how source code translates into control flow, runtime state changes, and structural design. Existing tools—such as Python's built-in `ast` module, `difflib`, or static diagram generators—typically output raw syntax trees, line-by-line text diffs, or isolated static graphs without execution context, and rarely support consistent analysis across multiple languages. **Prism** was created to bridge this gap by offering a unified, beginner-friendly workspace that turns static code into interactive flowcharts, safe step-by-step traces, plain-language explanations, and actionable structural feedback.

## Innovation

Unlike single-purpose linters or cloud-dependent educational sandboxes, **Prism** combines five capabilities into one cohesive, local-first package:
* **Multi-Language Unified Analysis**: Parses and traces Python (via standard `ast`) alongside JavaScript, TypeScript, Java, C++, and C (via `tree-sitter`) under a consistent analytical model.
* **Bounded Safe Execution Tracing**: Simulates step-by-step variable states and control-flow paths safely without executing arbitrary or unsafe system operations.
* **Symbol-Level Structural Diffing**: Integrates AST-aware comparison (`structscope`) to identify added, removed, modified, and renamed/moved functions and classes rather than noisy line-level diffs.
* **Automated Complexity & Readability Advisor**: Evaluates cyclomatic complexity, nesting depth, and readability grades (`metrics_advisor`) with concrete refactoring tips and Markdown/JSON export.
* **Headless & Desktop Flexibility**: Isolates optional desktop GUI dependencies (`PySide6`) so the core analysis engine installs and runs cleanly in both local workstations and headless environments like JupyterHub.

## Team Members & Division of Work

## Team Members & Division of Work

| Member Name | GitHub Account | Key Contributions |
| :--- | :--- | :--- |
| **ZHANG Chenrui** | `ZHANGChenrui-alt` | Spearheaded the early project architecture, conceptual design, and rapid prototyping through agentic coding workflows. Transformed the initial idea into a working local-first codebase, establishing the core multi-language analysis pipeline, interactive workspace foundation, and functional prototype demos that guided subsequent team modules. |
| **Wang Yuzhe** | `wyzzz12548` | Designed and implemented the **Compare Versions** page and structural diff engine (`compare.py` & `compare_engine.py`)[cite: 3, 4]. Built AST-based symbol-level comparison workflows that automatically detect unchanged, modified, renamed/moved, added, and removed classes and functions in a unified visual diff view rather than noisy line-by-line text diffs. |
| **Cheng Siying** | `ChengSiying21` | Developed the **Function POV** module using Python AST analysis to safely simulate function execution without running untrusted user code. Implemented step-by-step execution visualization, real-time variable state tracking, dynamic call-stack inspection, and interactive beginner coding challenges complete with automated hints and answer verification. |
| **YU Tonghao** | `ZenTao66` | Led end-to-end project testing, debugging, and quality assurance across core workflows. Identified and resolved critical edge cases in Python execution simulation, loop state rendering, result display formatting, and version comparison; refined UI/UX layouts for clarity and planned, recorded, and produced the final project demonstration video. |
| **Tao Chenlin** | `ryan25576868` | Architected and configured the standard PyPI packaging specification (`pyproject.toml` with `hatchling`)[cite: 2], isolating heavy desktop GUI dependencies (`PySide6`) as optional `[gui]` extras so the core engine installs cleanly in headless environments like JupyterHub[cite: 2]. Implemented the cross-language code complexity and readability advisor (`python_app/metrics_advisor.py`) with Markdown/JSON export and verified it with automated unit tests (`tests_py/test_metrics_advisor.py`)[cite: 3, 4]. |

## License

This project is distributed under the MIT License; see [LICENSE](./LICENSE).
