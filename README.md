# Function POV

A Python package for statically inspecting simple Python functions and building
function call graph data. The package includes a local interactive web interface
for exploring function relationships and source details. The Function POV
walkthrough is planned for a later stage.

## Install locally

```bash
python -m pip install .
```

## Analyze a project

```bash
function-pov analyze examples/basic_project
```

The command prints JSON containing discovered functions, parameters, source
locations, return expressions, resolvable local calls, and graph nodes/edges.
You can also run it without installing the console script:

```bash
python -m function_pov analyze examples/basic_project
```

The analyzer parses Python source with the standard-library `ast` module. It
does not import or execute the analyzed project. The initial version supports
top-level synchronous functions; async functions, classes, and nested
definitions are reported as unsupported. Calls are included when they can be
resolved to a function in the analyzed project.

## Interactive web interface

Start the local UI with:

```bash
function-pov ui
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765). Choose a project
folder or individual `.py` files in the browser. The interface displays an
interactive call graph and details for the selected function. You can drag
function nodes, pan and zoom the graph, and open connected functions from the
details panel. The UI assets are included in the Python package and work without
external JavaScript or font services.

Selected source text is sent to the local server for AST parsing. The server
stores it temporarily and does not import or execute it. The default server
binds only to `127.0.0.1`; uploaded source is limited to 400 files, 2 MB per
file, and 8 MB total.

## Tests

```bash
python -m unittest discover -s tests -v
```

The real-browser interaction regression uses Playwright. Install its optional
test dependency and Chromium once before running the browser test:

```bash
python -m pip install -e ".[test]"
python -m playwright install chromium
python -m unittest tests.test_ui_playwright -v
```

## Reference and licensing

The project takes functional inspiration from
[CodeMap](https://github.com/kirito-chen/CodeMap), an MIT-licensed Python code
visualizer. Its source code and image assets have not been copied into this
stage. This repository's existing MIT license remains in effect.