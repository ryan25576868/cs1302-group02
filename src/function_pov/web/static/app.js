(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const folderInput = $("#folder-input");
  const filesInput = $("#files-input");
  const graph = $("#function-graph");
  const graphContent = $("#graph-content");
  const svgNS = "http://www.w3.org/2000/svg";
  const state = {
    data: null,
    selectedId: null,
    positions: new Map(),
    scale: 1,
    panX: 0,
    panY: 0,
    pointer: null,
    suppressClick: false,
    sourceFiles: [],
    pov: null,
    toastTimer: null
  };

  $("#open-project-top").addEventListener("click", () => folderInput.click());
  $("#open-project-empty").addEventListener("click", () => folderInput.click());
  $("#open-files-top").addEventListener("click", () => filesInput.click());
  $("#open-files-empty").addEventListener("click", () => filesInput.click());
  folderInput.addEventListener("change", () => {
    analyzeFiles(folderInput.files);
    folderInput.value = "";
  });
  filesInput.addEventListener("change", () => {
    analyzeFiles(filesInput.files);
    filesInput.value = "";
  });
  $("#zoom-in").addEventListener("click", () => zoomAt(1.2, 500, 340));
  $("#zoom-out").addEventListener("click", () => zoomAt(1 / 1.2, 500, 340));
  $("#zoom-label").addEventListener("click", resetView);
  $("#reset-view").addEventListener("click", resetView);
  $("#enter-pov").addEventListener("click", openPovLauncher);
  $("#pov-launch-form").addEventListener("submit", startPov);
  $("#pov-launch-close").addEventListener("click", closePovLauncher);
  $("#pov-launch-cancel").addEventListener("click", closePovLauncher);
  $("#pov-back").addEventListener("click", backToMap);
  $("#pov-restart").addEventListener("click", restartPov);
  $("#pov-restart-top").addEventListener("click", restartPov);
  $("#pov-completion-replay").addEventListener("click", restartPov);
  $("#pov-completion-back").addEventListener("click", backToMap);
  $("#pov-previous").addEventListener("click", previousPovStep);
  $("#pov-next").addEventListener("click", nextPovStep);
  $("#pov-hint").addEventListener("click", showPovHint);
  $("#pov-answer").addEventListener("click", showPovAnswer);
  graph.addEventListener("wheel", handleWheel, { passive: false });
  graph.addEventListener("pointerdown", beginCanvasDrag);
  graph.addEventListener("pointermove", movePointer);
  graph.addEventListener("pointerup", endPointer);
  graph.addEventListener("pointercancel", endPointer);

  async function analyzeFiles(fileList) {
    const files = Array.from(fileList || []).filter((file) => file.name.toLowerCase().endsWith(".py"));
    if (!files.length) {
      showError("No Python files were selected. Choose a folder or one or more .py files.");
      return;
    }
    if (files.length > 400) {
      showError("This preview supports up to 400 Python files at a time.");
      return;
    }
    const totalBytes = files.reduce((total, file) => total + file.size, 0);
    if (totalBytes > 8 * 1024 * 1024) {
      showError("The selected Python files exceed the 8 MB total upload limit.");
      return;
    }

    setLoading(true);
    setStatus("Reading selected Python files…");
    try {
      const sourceFiles = await Promise.all(files.map(async (file) => {
        if (file.size > 2 * 1024 * 1024) {
          throw new Error(file.name + " is larger than the 2 MB per-file limit.");
        }
        const relativePath = file.webkitRelativePath;
        const projectPath = relativePath
          ? relativePath.split("/").slice(1).join("/")
          : file.name;
        return {
          path: projectPath || file.name,
          content: await file.text()
        };
      }));
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: sourceFiles })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "The project could not be analyzed.");
      }
      state.data = result;
      state.sourceFiles = sourceFiles;
      state.selectedId = null;
      state.positions = layoutNodes(result.graph.nodes);
      state.scale = 1;
      state.panX = 0;
      state.panY = 0;
      renderGraph();
      renderDetails(null);
      updateProjectSummary(files, result);
      setStatus("Analysis complete · " + result.functions.length + " function" + (result.functions.length === 1 ? "" : "s"));
      $("#graph-empty").hidden = result.graph.nodes.length > 0;
      $("#graph-legend").hidden = result.graph.nodes.length === 0;
      $("#graph-hint").hidden = result.graph.nodes.length === 0;
      $("#details-empty").hidden = result.graph.nodes.length === 0;
      $("#details-content").hidden = true;
      if (result.diagnostics.length) {
        setStatus("Analysis complete · " + result.diagnostics.length + " note" + (result.diagnostics.length === 1 ? "" : "s"));
      }
    } catch (error) {
      showError(error.message || "An unexpected error occurred while analyzing this project.");
      setStatus("Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  function updateProjectSummary(files, result) {
    const firstPath = files[0].webkitRelativePath || files[0].name;
    const projectName = firstPath.includes("/") ? firstPath.split("/")[0] : firstPath;
    $("#project-label").textContent = projectName + " · " + files.length + " Python file" + (files.length === 1 ? "" : "s");
    $("#graph-count").textContent = result.graph.nodes.length + " functions · " + result.graph.edges.length + " connections";
  }

  function layoutNodes(nodes) {
    const positions = new Map();
    const centerX = 500;
    const centerY = 340;
    if (nodes.length === 1) {
      positions.set(nodes[0].id, { x: centerX, y: centerY });
      return positions;
    }
    const radius = Math.max(100, Math.min(280, 50 + nodes.length * 22));
    nodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / nodes.length;
      positions.set(node.id, {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * 0.64 * Math.sin(angle)
      });
    });
    return positions;
  }

  function renderGraph() {
    graphContent.replaceChildren();
    if (!state.data) {
      applyTransform();
      return;
    }

    const { nodes, edges } = state.data.graph;
    const edgeLayer = createSvg("g", { class: "edge-layer" });
    const nodeLayer = createSvg("g", { class: "node-layer" });
    edges.forEach((edge) => {
      const from = state.positions.get(edge.source);
      const to = state.positions.get(edge.target);
      if (!from || !to) return;
      const deltaX = to.x - from.x;
      const deltaY = to.y - from.y;
      const length = Math.max(1, Math.hypot(deltaX, deltaY));
      const padding = 70;
      const startX = from.x + (deltaX / length) * padding;
      const startY = from.y + (deltaY / length) * 23;
      const endX = to.x - (deltaX / length) * padding;
      const endY = to.y - (deltaY / length) * 23;
      const curve = Math.max(18, Math.min(90, length * 0.18));
      const path = createSvg("path", {
        class: "graph-edge",
        d: "M " + startX + " " + startY + " C " + (startX + curve) + " " + startY + ", " + (endX - curve) + " " + endY + ", " + endX + " " + endY,
        "data-source": edge.source,
        "data-target": edge.target
      });
      edgeLayer.append(path);
    });
    nodes.forEach((node) => {
      const position = state.positions.get(node.id);
      const group = createSvg("g", {
        class: "node-group",
        transform: "translate(" + position.x + " " + position.y + ")",
        "data-id": node.id,
        role: "button",
        tabindex: "0",
        "aria-label": node.id + ", select function"
      });
      group.append(createSvg("rect", {
        class: "node-pill",
        x: "-65",
        y: "-23",
        width: "130",
        height: "46",
        rx: "9"
      }));
      const label = createSvg("text", { class: "node-label", "text-anchor": "middle", y: "0" });
      label.textContent = trimLabel(node.label, 19);
      group.append(label);
      const moduleLabel = createSvg("text", { class: "node-module", "text-anchor": "middle", y: "13" });
      moduleLabel.textContent = trimLabel(node.module, 22);
      group.append(moduleLabel);
      group.addEventListener("pointerdown", (event) => beginNodeDrag(event, node.id));
      group.addEventListener("click", (event) => {
        if (state.suppressClick) {
          state.suppressClick = false;
          return;
        }
        selectNode(node.id);
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectNode(node.id);
        }
      });
      nodeLayer.append(group);
    });
    graphContent.append(edgeLayer, nodeLayer);
    applyTransform();
    updateHighlight();
  }

  function trimLabel(value, maxLength) {
    return value.length > maxLength ? value.slice(0, maxLength - 1) + "…" : value;
  }

  function createSvg(tag, attributes) {
    const element = document.createElementNS(svgNS, tag);
    Object.keys(attributes).forEach((key) => element.setAttribute(key, attributes[key]));
    return element;
  }

  function selectNode(id) {
    if (!state.data) return;
    state.selectedId = id;
    updateHighlight();
    const fn = state.data.functions.find((item) => item.id === id);
    renderDetails(fn);
    $("#details-empty").hidden = true;
    $("#details-content").hidden = false;
    setStatus("Selected " + id);
  }

  function updateHighlight() {
    const selected = state.selectedId;
    const neighbors = new Set();
    if (selected && state.data) {
      state.data.calls.forEach((call) => {
        if (call.caller === selected) neighbors.add(call.callee);
        if (call.callee === selected) neighbors.add(call.caller);
      });
    }
    graphContent.querySelectorAll(".node-group").forEach((element) => {
      const id = element.getAttribute("data-id");
      element.classList.toggle("is-selected", id === selected);
      element.classList.toggle("is-neighbor", neighbors.has(id));
      element.classList.toggle("is-dim", Boolean(selected) && id !== selected && !neighbors.has(id));
    });
    graphContent.querySelectorAll(".graph-edge").forEach((element) => {
      const source = element.getAttribute("data-source");
      const target = element.getAttribute("data-target");
      const active = source === selected || target === selected;
      element.classList.toggle("is-active", active);
      element.classList.toggle("is-dim", Boolean(selected) && !active);
    });
  }

  function renderDetails(fn) {
    if (!fn) return;
    $("#details-heading").textContent = fn.name;
    $("#detail-location").textContent = fn.file + ":" + fn.line;
    $("#code-file").textContent = fn.file;
    $("#source-code").textContent = fn.source || "";

    const parameters = $("#parameter-list");
    parameters.replaceChildren();
    $("#parameter-count").textContent = String(fn.parameters.length);
    if (!fn.parameters.length) {
      parameters.append(emptyNote("No parameters"));
    } else {
      fn.parameters.forEach((parameter) => {
        const chip = document.createElement("span");
        chip.className = "parameter-chip";
        const name = document.createElement("span");
        name.className = "parameter-name";
        name.textContent = parameter.name;
        chip.append(name);
        if (parameter.annotation) {
          const type = document.createElement("span");
          type.className = "parameter-type";
          type.textContent = ": " + parameter.annotation;
          chip.append(type);
        }
        if (parameter.default !== null) {
          const defaultValue = document.createElement("span");
          defaultValue.className = "parameter-default";
          defaultValue.textContent = "= " + parameter.default;
          chip.append(defaultValue);
        }
        parameters.append(chip);
      });
    }

    const returns = $("#return-list");
    returns.replaceChildren();
    if (!fn.return_expressions.length) {
      returns.append(emptyNote("No explicit return expression"));
    } else {
      fn.return_expressions.forEach((expression) => {
        const code = document.createElement("code");
        code.className = "return-expression";
        code.textContent = "return " + expression;
        returns.append(code);
      });
    }
    renderConnections("#calls-list", state.data.calls.filter((call) => call.caller === fn.id).map((call) => call.callee), "↗");
    renderConnections("#called-by-list", state.data.calls.filter((call) => call.callee === fn.id).map((call) => call.caller), "↙");

    const notices = state.data.diagnostics || [];
    const relevant = notices.filter((item) => item.file === fn.file);
    const notice = $("#diagnostics-notice");
    notice.hidden = relevant.length === 0;
    notice.textContent = relevant.map((item) => (item.line ? "Line " + item.line + ": " : "") + item.message).join(" ");
  }

  function openPovLauncher() {
    if (!state.data || !state.selectedId) return;
    const fn = state.data.functions.find((item) => item.id === state.selectedId);
    if (!fn) return;
    $("#pov-launch-title").textContent = "Enter " + fn.name + "()";
    $("#launch-error").hidden = true;
    const container = $("#launch-arguments");
    container.replaceChildren();
    fn.parameters.forEach((parameter) => {
      const wrapper = document.createElement("div");
      wrapper.className = "launch-argument";
      const label = document.createElement("label");
      label.htmlFor = "pov-arg-" + parameter.name;
      label.append(document.createTextNode(parameter.name));
      const meta = document.createElement("span");
      meta.textContent = parameter.default === null
        ? " · required"
        : " · optional, default " + parameter.default;
      label.append(meta);
      const input = document.createElement("input");
      input.id = "pov-arg-" + parameter.name;
      input.name = parameter.name;
      input.type = "text";
      input.autocomplete = "off";
      input.spellcheck = false;
      input.placeholder = parameter.default === null
        ? 'e.g. 4, true, or "hello"'
        : "Leave blank to use the default";
      wrapper.append(label, input);
      container.append(wrapper);
    });
    $("#pov-launcher").hidden = false;
    const firstInput = container.querySelector("input");
    if (firstInput) firstInput.focus();
    else $("#pov-launch-form button[type='submit']").focus();
  }

  function closePovLauncher() {
    $("#pov-launcher").hidden = true;
  }

  async function startPov(event) {
    event.preventDefault();
    if (!state.selectedId || !state.sourceFiles.length) return;
    const argumentsByName = {};
    for (const input of $("#launch-arguments").querySelectorAll("input")) {
      const text = input.value.trim();
      const fn = state.data.functions.find((item) => item.id === state.selectedId);
      const parameter = fn.parameters.find((item) => item.name === input.name);
      if (!text) {
        if (parameter.default === null) {
          showLaunchError("Enter a value for the required parameter " + input.name + ".");
          input.focus();
          return;
        }
        continue;
      }
      try {
        argumentsByName[input.name] = JSON.parse(text);
      } catch (_error) {
        showLaunchError("Use a JSON value for " + input.name + ', such as 4, true, or "hello".');
        input.focus();
        return;
      }
    }

    const submit = $("#pov-launch-form button[type='submit']");
    submit.disabled = true;
    submit.textContent = "Preparing simulation…";
    try {
      const response = await fetch("/api/pov/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          files: state.sourceFiles,
          function_id: state.selectedId,
          arguments: argumentsByName
        })
      });
      const session = await response.json();
      if (!response.ok) throw new Error(session.error || "Could not start this POV simulation.");
      state.pov = {
        session,
        index: 0,
        passed: new Set(),
        responses: new Map(),
        complete: false
      };
      closePovLauncher();
      $("#pov-overlay").hidden = false;
      document.body.classList.add("pov-active");
      renderPovStep();
    } catch (error) {
      showLaunchError(error.message || "Could not start this POV simulation.");
    } finally {
      submit.disabled = false;
      submit.innerHTML = '<span aria-hidden="true">✦</span> Enter POV';
    }
  }

  function showLaunchError(message) {
    const error = $("#launch-error");
    error.textContent = message;
    error.hidden = false;
  }

  function backToMap() {
    $("#pov-overlay").hidden = true;
    $("#pov-launcher").hidden = true;
    document.body.classList.remove("pov-active");
    state.pov = null;
  }

  function restartPov() {
    if (!state.pov) return;
    state.pov.index = 0;
    state.pov.passed.clear();
    state.pov.responses.clear();
    state.pov.complete = false;
    renderPovStep();
  }

  function previousPovStep() {
    if (!state.pov || state.pov.index === 0) return;
    state.pov.complete = false;
    state.pov.index -= 1;
    renderPovStep();
  }

  function nextPovStep() {
    if (!state.pov) return;
    const step = currentPovStep();
    if (step.challenge && !state.pov.passed.has(state.pov.index)) return;
    if (state.pov.index === state.pov.session.steps.length - 1) {
      state.pov.complete = true;
      renderPovStep();
      return;
    }
    state.pov.index += 1;
    state.pov.complete = false;
    renderPovStep();
  }

  function currentPovStep() {
    return state.pov.session.steps[state.pov.index];
  }

  function renderPovStep() {
    if (!state.pov) return;
    const pov = state.pov;
    const steps = pov.session.steps;
    const step = steps[pov.index];
    const source = pov.session.sources[step.function_id];
    $("#pov-progress-label").textContent = pov.complete
      ? "FUNCTION COMPLETE"
      : "STEP " + (pov.index + 1) + " OF " + steps.length;
    $("#pov-progress-function").textContent = step.function_name + "()";
    $("#pov-progress-bar").style.width =
      (pov.complete ? 100 : ((pov.index + 1) / steps.length) * 100) + "%";
    $("#pov-main").hidden = pov.complete;
    $("#pov-completion").hidden = !pov.complete;
    $("#pov-controls").hidden = pov.complete;
    if (pov.complete) {
      renderPovCompletion();
      return;
    }

    $("#pov-code-file").textContent = source.file;
    $("#pov-local-function").textContent = step.function_name + "()";
    renderPovSource(source, step.line);
    renderPovStack(step.stack);
    renderPovLocals(step.variables);

    const iconByKind = {
      enter: "↘",
      arithmetic: "∑",
      condition: "◇",
      function_call: "↗",
      call_return: "↩",
      return: "↗",
      assignment: "＝"
    };
    const labelByKind = {
      enter: "FUNCTION ENTRY",
      arithmetic: "SOLVE THE EXPRESSION",
      condition: "CHOOSE A BRANCH",
      function_call: "FUNCTION CALL",
      call_return: "BACK FROM A FUNCTION",
      return: "RETURN TO CALLER",
      assignment: "LOCAL ASSIGNMENT"
    };
    $("#pov-step-icon").textContent = iconByKind[step.kind] || "✦";
    $("#pov-step-type").textContent = labelByKind[step.kind] || "FUNCTION STEP";
    $("#pov-prompt").textContent = step.prompt;
    $("#pov-expression").textContent = step.expression;
    renderPovTokens(step);
    renderPovChallenge(step);
    renderPovFeedback();

    const passed = !step.challenge || pov.passed.has(pov.index);
    $("#pov-previous").disabled = pov.index === 0;
    $("#pov-next").disabled = !passed || pov.complete;
    $("#pov-next").innerHTML = pov.index === steps.length - 1
      ? 'Finish <span aria-hidden="true">✓</span>'
      : 'Next <span aria-hidden="true">→</span>';
    $("#pov-hint").disabled = !step.challenge || pov.passed.has(pov.index) || pov.complete;
    $("#pov-answer").disabled = !step.challenge || pov.passed.has(pov.index) || pov.complete;
  }

  function renderPovCompletion() {
    const pov = state.pov;
    $("#pov-overlay").scrollTop = 0;
    const steps = pov.session.steps;
    const challengeSteps = steps
      .map((step, index) => ({ step, index }))
      .filter(({ step }) => step.challenge);
    const answeredByLearner = challengeSteps.filter(({ index }) => {
      const response = pov.responses.get(index);
      return response && response.solvedBy === "attempt";
    }).length;
    const revealed = challengeSteps.filter(({ index }) => {
      const response = pov.responses.get(index);
      return response && response.solvedBy === "reveal";
    }).length;
    const finalResponse = [...challengeSteps].reverse()
      .map(({ index }) => pov.responses.get(index))
      .find((response) => response && Object.prototype.hasOwnProperty.call(response, "answer"));
    const journey = Array.from(new Set(steps.map((step) => step.function_name)));

    $("#pov-completion-value").textContent = finalResponse
      ? formatPovValue(finalResponse.answer)
      : "No explicit return value";
    $("#pov-completion-summary").textContent =
      "You traced " + journey.join(" → ") + " across " +
      challengeSteps.length + " interactive challenge" +
      (challengeSteps.length === 1 ? "" : "s") + ".";
    $("#pov-completion-effort").textContent =
      answeredByLearner + " solved by you · " + revealed + " revealed";
  }

  function renderPovSource(source, activeLine) {
    const container = $("#pov-source");
    container.replaceChildren();
    source.source.split("\n").forEach((text, index) => {
      const lineNumber = source.line + index;
      const line = document.createElement("span");
      line.className = "pov-source-line";
      line.classList.toggle("is-active", lineNumber === activeLine);
      line.dataset.line = String(lineNumber);
      const number = document.createElement("span");
      number.className = "pov-source-line-number";
      number.textContent = String(lineNumber);
      line.append(number, document.createTextNode(text));
      container.append(line);
    });
    const active = container.querySelector(".is-active");
    if (active) active.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function renderPovStack(stack) {
    const container = $("#pov-stack");
    container.replaceChildren();
    stack.forEach((frame, index) => {
      const token = document.createElement("div");
      token.className = "stack-frame";
      token.classList.toggle("is-current", index === stack.length - 1);
      const marker = document.createElement("span");
      marker.textContent = index === stack.length - 1 ? "●" : "↳";
      token.append(marker, document.createTextNode(frame.function_name + "()"));
      container.append(token);
    });
  }

  function renderPovLocals(variables) {
    const container = $("#pov-locals");
    container.replaceChildren();
    const entries = Object.entries(variables || {});
    if (!entries.length) {
      const empty = document.createElement("span");
      empty.className = "locals-empty";
      empty.textContent = "No local values yet";
      container.append(empty);
      return;
    }
    entries.forEach(([name, value]) => {
      const token = document.createElement("span");
      token.className = "local-token";
      const key = document.createElement("span");
      key.className = "local-token-name";
      key.textContent = name;
      const val = document.createElement("span");
      val.className = "local-token-value";
      val.textContent = formatPovValue(value);
      token.append(key, val);
      container.append(token);
    });
  }

  function renderPovTokens(step) {
    const container = $("#pov-argument-tokens");
    container.replaceChildren();
    if (step.kind === "enter") {
      Object.entries(step.variables || {}).forEach(([name, value]) => {
        const token = document.createElement("span");
        token.className = "argument-token";
        const key = document.createElement("span");
        key.className = "argument-token-name";
        key.textContent = name + " =";
        const val = document.createElement("span");
        val.className = "argument-token-value";
        val.textContent = formatPovValue(value);
        token.append(key, val);
        container.append(token);
      });
    }
    const response = state.pov.responses.get(state.pov.index);
    if (response && Object.prototype.hasOwnProperty.call(response, "answer")) {
      const token = document.createElement("span");
      token.className = "return-token is-animated";
      token.textContent = "↗ Returned " + formatPovValue(response.answer);
      container.append(token);
    } else if (step.kind === "call_return" && !step.challenge) {
      const token = document.createElement("span");
      token.className = "return-token is-animated";
      token.textContent = step.expression;
      container.append(token);
    }
  }

  function renderPovChallenge(step) {
    const container = $("#pov-challenge");
    container.replaceChildren();
    if (state.pov.complete) return;
    if (!step.challenge) {
      const note = document.createElement("p");
      note.className = "pov-challenge-prompt";
      note.textContent = step.kind === "enter"
        ? "Take a look at the values your caller passed in. Continue when you're ready."
        : "Follow the highlighted line, then continue to the next moment.";
      container.append(note);
      return;
    }
    const prompt = document.createElement("p");
    prompt.className = "pov-challenge-prompt";
    prompt.textContent = step.kind === "return"
      ? "Enter the value you are returning."
      : step.kind === "condition"
        ? "Choose the result of this condition."
        : step.kind === "function_call"
          ? "Select the function name from the code."
          : "Enter your result, then check it.";
    container.append(prompt);
    if (step.kind === "condition" || step.kind === "function_call") {
      const choices = document.createElement("div");
      choices.className = "pov-choice-row";
      const response = state.pov.responses.get(state.pov.index);
      (step.kind === "condition" ? ["True", "False"] : step.choices).forEach((choice) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "pov-choice";
        button.textContent = choice;
        button.disabled = state.pov.passed.has(state.pov.index);
        button.classList.toggle("is-selected", Boolean(response && response.attempt === choice));
        button.setAttribute("aria-pressed", String(Boolean(response && response.attempt === choice)));
        button.addEventListener("click", () => {
          const value = step.kind === "condition" ? choice === "True" : choice;
          checkPovAnswer(value, choice);
        });
        choices.append(button);
      });
      container.append(choices);
      appendPovAnswerReview(container, response);
      return;
    }
    const response = state.pov.responses.get(state.pov.index);
    const row = document.createElement("div");
    row.className = "pov-answer-row";
    const input = document.createElement("input");
    input.className = "pov-answer-input";
    input.id = "pov-answer-input";
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = 'Your answer (e.g. 16 or "hello")';
    input.value = response && response.attempt !== undefined ? response.attempt : "";
    input.disabled = state.pov.passed.has(state.pov.index);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") checkTextAnswer();
    });
    const check = document.createElement("button");
    check.type = "button";
    check.className = "button button-primary pov-check-button";
    check.textContent = "Check answer";
    check.disabled = state.pov.passed.has(state.pov.index);
    check.addEventListener("click", checkTextAnswer);
    row.append(input, check);
    container.append(row);
    appendPovAnswerReview(container, response);
  }

  function appendPovAnswerReview(container, response) {
    if (!response || !response.attempts || !response.attempts.length) return;
    const review = document.createElement("div");
    review.className = "pov-answer-review";
    const attempts = document.createElement("div");
    attempts.className = "pov-review-card";
    const attemptsLabel = document.createElement("span");
    attemptsLabel.className = "pov-review-label";
    attemptsLabel.textContent = "YOUR ATTEMPTS";
    const list = document.createElement("ol");
    list.className = "pov-attempt-list";
    response.attempts.forEach((attempt, index) => {
      const item = document.createElement("li");
      item.className = attempt.correct ? "is-correct" : "is-incorrect";
      item.textContent = "Attempt " + (index + 1) + ": " + attempt.value;
      list.append(item);
    });
    attempts.append(attemptsLabel, list);
    review.append(attempts);

    if (Object.prototype.hasOwnProperty.call(response, "answer")) {
      const answer = document.createElement("div");
      answer.className = "pov-review-card is-answer";
      const label = document.createElement("span");
      label.className = "pov-review-label";
      label.textContent = response.solvedBy === "reveal" ? "REVEALED ANSWER" : "CHECKED RESULT";
      const value = document.createElement("code");
      value.textContent = formatPovValue(response.answer);
      answer.append(label, value);
      review.append(answer);
    }
    container.append(review);
  }

  function checkTextAnswer() {
    const input = $("#pov-answer-input");
    if (!input) return;
    const text = input.value.trim();
    if (!text) {
      showPovFeedback("Enter an answer first.", "wrong");
      input.focus();
      return;
    }
    let value;
    try {
      value = JSON.parse(text);
    } catch (_error) {
      value = text;
    }
    checkPovAnswer(value, text);
  }

  async function checkPovAnswer(answer, attempt) {
    const pov = state.pov;
    if (!pov) return;
    const index = pov.index;
    try {
      const result = await povRequest("/api/pov/check", {
        session_id: pov.session.session_id,
        step: index,
        answer
      });
      const previous = pov.responses.get(index) || { attempts: [] };
      previous.attempts = previous.attempts || [];
      if (result.correct) {
        previous.attempt = String(attempt);
        previous.attempts.push({ value: String(attempt), correct: true });
        previous.answer = result.answer;
        previous.feedback = result.feedback;
        previous.kind = "correct";
        previous.solvedBy = "attempt";
        pov.responses.set(index, previous);
        pov.passed.add(index);
        renderPovStep();
      } else {
        previous.attempt = String(attempt);
        previous.attempts.push({ value: String(attempt), correct: false });
        previous.feedback = result.feedback;
        previous.kind = "wrong";
        pov.responses.set(index, previous);
        renderPovStep();
      }
    } catch (error) {
      showPovFeedback(error.message, "wrong");
    }
  }

  async function showPovHint() {
    if (!state.pov) return;
    try {
      const result = await povRequest("/api/pov/hint", {
        session_id: state.pov.session.session_id,
        step: state.pov.index
      });
      showPovFeedback(result.hint, "hint");
    } catch (error) {
      showPovFeedback(error.message, "wrong");
    }
  }

  async function showPovAnswer() {
    if (!state.pov) return;
    const index = state.pov.index;
    try {
      const result = await povRequest("/api/pov/answer", {
        session_id: state.pov.session.session_id,
        step: index
      });
      state.pov.passed.add(index);
      const previous = state.pov.responses.get(index) || { attempts: [] };
      previous.answer = result.answer;
      previous.feedback = "Answer revealed. Compare it with your attempt to see how this step continues.";
      previous.kind = "hint";
      previous.solvedBy = "reveal";
      state.pov.responses.set(index, previous);
      renderPovStep();
    } catch (error) {
      showPovFeedback(error.message, "wrong");
    }
  }

  async function povRequest(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The POV action could not be completed.");
    return result;
  }

  function renderPovFeedback() {
    const feedback = $("#pov-feedback");
    const response = state.pov.responses.get(state.pov.index);
    feedback.hidden = !response || !response.feedback;
    feedback.className = "pov-feedback" + (response && response.kind ? " is-" + response.kind : "");
    feedback.textContent = response ? response.feedback || "" : "";
  }

  function showPovFeedback(message, kind) {
    const feedback = $("#pov-feedback");
    feedback.hidden = false;
    feedback.className = "pov-feedback" + (kind ? " is-" + kind : "");
    feedback.textContent = message;
    if (state.pov) {
      const previous = state.pov.responses.get(state.pov.index) || {};
      previous.feedback = message;
      previous.kind = kind;
      state.pov.responses.set(state.pov.index, previous);
    }
  }

  function formatPovValue(value) {
    return JSON.stringify(value);
  }

  function renderConnections(selector, ids, arrow) {
    const container = $(selector);
    container.replaceChildren();
    if (!ids.length) {
      container.append(emptyNote("None"));
      return;
    }
    const list = document.createElement("div");
    list.className = "connection-list";
    Array.from(new Set(ids)).forEach((id) => {
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "connection-pill";
      pill.title = id;
      const icon = document.createElement("span");
      icon.className = "connection-arrow";
      icon.textContent = arrow;
      pill.append(icon, document.createTextNode(id.split(".").pop()));
      pill.addEventListener("click", () => selectNode(id));
      list.append(pill);
    });
    container.append(list);
  }

  function emptyNote(text) {
    const note = document.createElement("span");
    note.className = "no-data";
    note.textContent = text;
    return note;
  }

  function beginCanvasDrag(event) {
    if (event.target.closest(".node-group")) return;
    const point = pointerPosition(event);
    state.pointer = { type: "canvas", x: point.x, y: point.y, startX: state.panX, startY: state.panY, moved: false };
    graph.setPointerCapture(event.pointerId);
  }

  function beginNodeDrag(event, id) {
    event.stopPropagation();
    if (event.button !== 0) return;
    const point = pointerPosition(event);
    const position = state.positions.get(id);
    state.pointer = {
      type: "node",
      id,
      captureTarget: event.currentTarget,
      x: point.x,
      y: point.y,
      startX: position.x,
      startY: position.y,
      moved: false
    };
    state.suppressClick = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function movePointer(event) {
    const pointer = state.pointer;
    if (!pointer) return;
    const point = pointerPosition(event);
    if (Math.hypot(point.x - pointer.x, point.y - pointer.y) > 2) pointer.moved = true;
    if (pointer.type === "canvas") {
      state.panX = pointer.startX + (point.x - pointer.x);
      state.panY = pointer.startY + (point.y - pointer.y);
    } else if (pointer.type === "node") {
      const position = {
        x: pointer.startX + (point.x - pointer.x) / state.scale,
        y: pointer.startY + (point.y - pointer.y) / state.scale
      };
      state.positions.set(pointer.id, position);
      const node = graphContent.querySelector('[data-id="' + CSS.escape(pointer.id) + '"]');
      if (node) node.setAttribute("transform", "translate(" + position.x + " " + position.y + ")");
      renderEdges();
    }
    applyTransform();
  }

  function renderEdges() {
    if (!state.data) return;
    const edgeLayer = graphContent.querySelector(".edge-layer");
    if (!edgeLayer) return;
    edgeLayer.replaceChildren();
    state.data.graph.edges.forEach((edge) => {
      const from = state.positions.get(edge.source);
      const to = state.positions.get(edge.target);
      if (!from || !to) return;
      const deltaX = to.x - from.x;
      const deltaY = to.y - from.y;
      const length = Math.max(1, Math.hypot(deltaX, deltaY));
      const startX = from.x + (deltaX / length) * 70;
      const startY = from.y + (deltaY / length) * 23;
      const endX = to.x - (deltaX / length) * 70;
      const endY = to.y - (deltaY / length) * 23;
      const curve = Math.max(18, Math.min(90, length * 0.18));
      edgeLayer.append(createSvg("path", {
        class: "graph-edge",
        d: "M " + startX + " " + startY + " C " + (startX + curve) + " " + startY + ", " + (endX - curve) + " " + endY + ", " + endX + " " + endY,
        "data-source": edge.source,
        "data-target": edge.target
      }));
    });
    updateHighlight();
  }

  function endPointer(event) {
    const pointer = state.pointer;
    if (pointer && pointer.type === "node" && pointer.moved) state.suppressClick = true;
    const captureTarget = pointer && pointer.captureTarget ? pointer.captureTarget : graph;
    if (captureTarget.hasPointerCapture(event.pointerId)) captureTarget.releasePointerCapture(event.pointerId);
    state.pointer = null;
    window.setTimeout(() => { state.suppressClick = false; }, 0);
  }

  function pointerPosition(event) {
    const rect = graph.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * 1000,
      y: ((event.clientY - rect.top) / rect.height) * 680
    };
  }

  function handleWheel(event) {
    event.preventDefault();
    const point = pointerPosition(event);
    zoomAt(event.deltaY < 0 ? 1.1 : 1 / 1.1, point.x, point.y);
  }

  function zoomAt(multiplier, x, y) {
    const previous = state.scale;
    state.scale = Math.max(0.45, Math.min(2.6, state.scale * multiplier));
    state.panX = x - (x - state.panX) * (state.scale / previous);
    state.panY = y - (y - state.panY) * (state.scale / previous);
    applyTransform();
  }

  function applyTransform() {
    graphContent.setAttribute("transform", "translate(" + state.panX + " " + state.panY + ") scale(" + state.scale + ")");
    $("#zoom-label").textContent = Math.round(state.scale * 100) + "%";
  }

  function resetView() {
    state.scale = 1;
    state.panX = 0;
    state.panY = 0;
    if (state.data) state.positions = layoutNodes(state.data.graph.nodes);
    renderGraph();
    setStatus("Graph view reset");
  }

  function setLoading(isLoading) {
    $("#graph-loading").classList.toggle("is-visible", isLoading);
    $("#open-project-top").disabled = isLoading;
    $("#open-project-empty").disabled = isLoading;
    if (isLoading) {
      $("#graph-empty").hidden = true;
      $("#graph-legend").hidden = true;
      $("#graph-hint").hidden = true;
    } else if (!state.data) {
      $("#graph-empty").hidden = false;
    }
  }

  function showError(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 5500);
    setStatus("Could not analyze project");
  }

  function setStatus(message) {
    $("#status-message").textContent = message;
  }
})();
