# Prism

**A native Python workspace for understanding code.**

Prism turns a source file into a linked set of views—flow, syntax, execution, and data—and explains the program in plain English. It is built for beginners, runs entirely on the local machine, and is implemented with **PySide6** rather than a browser runtime.

![Prism welcome screen](screenshots/native-welcome.png)

## Highlights

- **Six languages** — Python, JavaScript, TypeScript, Java, C++, and C.
- **Four linked views** — Flowchart, Syntax Tree, Live Trace, and Data Flow.
- **Beginner's guide** — overview, mental model, step-by-step walkthrough, line-by-line notes, concepts, common mistakes, and a quick check.
- **Native motion** — page and tab transitions, sequenced flowchart nodes, trace-detail fades, and a drifting welcome illustration.
- **Optional AI** — add a second explanation with OpenAI-compatible, DeepSeek, Grok, Anthropic, or Gemini. Local analysis needs no AI.
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

![Java analysis in Prism](screenshots/native-java.png)

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
  ai.py                  Optional AI provider calls and validation
  launch_native.py       Application entry point
  requirements.txt       PySide6 and tree-sitter grammars
tests_py/
  test_analysis.py
  test_javascript.py
  test_compiled.py
  test_ai.py
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

**15 tests currently pass.** They cover Python, JavaScript, TypeScript, Java, C++, and C analysis; trace output; guide generation; syntax errors; AI settings validation; and empty input.

## Troubleshooting

- **`ModuleNotFoundError: PySide6` or `tree_sitter`** — install the requirements with `python -m pip install -r python_app\requirements.txt`.
- **No source file imports** — use the file dialog or drag support is intentionally not implemented in this native edition; use **Import file**.
- **Trace stops early** — the code uses a construct outside the bounded beginner subset. The structural views and guide remain available.
- **AI connection fails** — verify the base URL, model ID, API key, and network access. The local guide does not depend on AI.

## Limitations

- The compiled-language trace supports a beginner subset. Complex generics, pointer arithmetic, macros, multithreading, and exception-heavy Java are not fully interpreted.
- JavaScript and TypeScript coverage is intentionally conservative; some higher-order and dynamic constructs are outside the trace subset.
- The flow and data views are explanatory diagrams, not compiler-grade control-flow graphs or SSA.
- Source snippets are capped at 60,000 characters.
- AI output depends on the selected provider and model. The local guide remains available if a request fails.
- The app targets Windows 10/11 x64.

## More screenshots

### Beginner's guide

![Prism guide](screenshots/native-guide.png)

### Optional AI settings

![Prism AI settings](screenshots/native-ai-settings.png)

## License

No license file is included in this workspace. Add the license appropriate for your distribution before publishing.
