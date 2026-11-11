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
        return {
          path: file.webkitRelativePath || file.name,
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
