/**
 * Flowchart view.
 *
 * The layout is built recursively from the structural tree, not forced through
 * a generic graph engine. That lets branches, loop rails, and the merge points
 * line up in the way a beginner would draw them by hand.
 */

import { escapeHTML } from '../utils.js';
import {
  svgRoot,
  arrowDefs,
  wrapText,
  pathFromPoints,
  edgeLabel,
  mountDiagram,
  bindNodeSelection,
  statusBarMarkup
} from './diagram.js';

const PAD = 30;
const VGAP = 22;
const NODE_WIDTH = 286;
const DECISION_WIDTH = 300;
const LOOP_WIDTH = 318;
const RAIL = 40;
const BRANCH_GAP = 26;

export function renderFlowchart(container, analysis, options = {}) {
  const focus = options.focus ?? {
    kind: analysis.entry?.kind ?? 'program',
    node: analysis.entry?.kind === 'function' ? analysis.entry.node : analysis.root,
    name: analysis.entry?.name ?? 'Program'
  };
  const builder = new FlowBuilder(analysis);
  const model = builder.build(focus);
  const svg = renderFlowModel(model);
  const stageWidth = Math.max(320, container.clientWidth || 700);
  const stageHeight = Math.max(260, container.clientHeight || 640);
  const widthFit = (stageWidth - 52) / model.width;
  const heightFit = (stageHeight - 52) / model.height;
  const initialScale = Math.min(1, Math.max(0.78, widthFit), Math.max(0.72, heightFit));
  const view = mountDiagram(container, {
    width: model.width,
    height: model.height,
    svg,
    label: `Flowchart of ${focus.name ?? 'the program'}`,
    initialScale,
    fitOnMount: false,
    minScale: 0.3,
    maxScale: 1.7
  });

  const activeLine = { value: null };
  bindNodeSelection(container, (selection) => {
    if (!Number.isFinite(selection.line)) return;
    options.onSelectLine?.({ line: selection.line, endLine: selection.endLine, label: selection.label, source: 'flow' });
    setLinked(container, selection.line, selection.endLine);
  });

  const footer = statusBarMarkup({
    legend: [
      { label: 'Step', className: 'swatch--action' },
      { label: 'Decision', className: 'swatch--decision' },
      { label: 'Loop', className: 'swatch--loop' },
      { label: 'Helper', className: 'swatch--function' },
      { label: 'Output / return', className: 'swatch--output' }
    ],
    hint: focus.kind === 'program' && analysis.functions.length
      ? 'Click a shape to reveal its code · Use the focus menu for function bodies'
      : 'Click a shape to reveal its code · Drag to pan'
  });

  return {
    footer,
    focusName: focus.name,
    highlightLine(line) {
      activeLine.value = line;
      setLinked(container, line, line);
    },
    onFocusRequest: options.onFocusRequest,
    destroy() {
      view.destroy();
    },
    fit: view.fit
  };
}

function setLinked(container, line, endLine = line) {
  const nodes = container.querySelectorAll('[data-node-id]');
  nodes.forEach((node) => {
    const start = Number(node.dataset.line);
    const end = Number(node.dataset.endLine || node.dataset.line);
    node.classList.toggle('is-linked', line >= start && line <= end);
  });
}

class FlowBuilder {
  constructor(analysis) {
    this.analysis = analysis;
    this.language = analysis.language;
    this.id = 0;
    this.nodeCount = 0;
    this.maxNodes = 140;
    this.truncated = false;
  }

  build(focus) {
    this.nodes = [];
    this.containers = [];
    this.edges = [];
    this.focusKind = focus.kind;
    const bodyBlock = focus.kind === 'function' ? focus.node.body : this.analysis.root.body;
    const body = this.buildSequence(bodyBlock);
    const start = this.terminalUnit(
      'start',
      'Start',
      focus.kind === 'function' ? (focus.isEntry ? 'ENTRY' : 'FUNCTION') : 'PROGRAM',
      focus.kind === 'function' ? focus.node.startLine : this.analysis.entry?.kind === 'function' ? this.analysis.entry.node.startLine : 1
    );
    const units = [start];
    if (body) units.push(body);
    if (body?.exit || !body) {
      const endLine = this.analysis.lineCount;
      const endLabel = focus.kind === 'function' && !focus.isEntry ? 'End function' : 'End program';
      const endTag = focus.kind === 'function' && !focus.isEntry ? 'RETURN' : 'PROGRAM END';
      const end = this.terminalUnit('end', endLabel, endTag, endLine, true);
      units.push(end);
    }

    const stack = this.stackUnits(units, VGAP, true);
    if (!stack) {
      const fallback = this.terminalUnit('end', 'Nothing to draw yet', 'EMPTY', 1, true);
      return this.finalise(fallback);
    }
    if (!body) {
      // A single vertical connector between start and end looks unfinished;
      // render the terminal units stacked with a normal gap instead.
    }
    return this.finalise(stack);
  }

  finalise(unit) {
    const shifted = translateUnit(unit, PAD, PAD);
    return {
      width: shifted.width + PAD * 2,
      height: shifted.height + PAD * 2,
      nodes: shifted.nodes,
      containers: shifted.containers,
      edges: shifted.edges,
      truncated: this.truncated
    };
  }

  buildSequence(block) {
    if (!block?.children?.length) return null;
    const units = [];
    let previousTerminal = false;
    for (const node of block.children) {
      if (this.nodeCount >= this.maxNodes) {
        this.truncated = true;
        break;
      }
      const unit = this.unitForNode(node);
      if (!unit) continue;
      if (previousTerminal) {
        unit.nodes = unit.nodes.map((nodeItem) => ({ ...nodeItem, unreachable: true }));
      }
      units.push(unit);
      if (!unit.exit) previousTerminal = true;
    }
    return this.stackUnits(units, VGAP, false);
  }

  stackUnits(units, gap, includeEntry) {
    if (!units.length) return null;
    const valid = units.filter(Boolean);
    if (!valid.length) return null;
    const width = Math.max(...valid.map((unit) => unit.width));
    let y = 0;
    let previousExit = null;
    const nodes = [];
    const containers = [];
    const edges = [];
    let firstEntry = null;
    valid.forEach((unit, index) => {
      const dx = (width - unit.width) / 2;
      const shifted = translateUnit(unit, dx, y);
      nodes.push(...shifted.nodes);
      containers.push(...shifted.containers);
      edges.push(...shifted.edges);
      if (index === 0) {
        firstEntry = shifted.entry;
      } else if (previousExit && shifted.entry) {
        edges.push({
          points: [previousExit, shifted.entry],
          kind: 'sequence',
          arrow: true
        });
      }
      previousExit = shifted.exit;
      y += unit.height;
      if (index < valid.length - 1) y += gap;
    });
    return {
      width,
      height: Math.max(0, y),
      nodes,
      containers,
      edges,
      entry: firstEntry,
      exit: valid.at(-1)?.exit ? previousExit : null
    };
  }

  unitForNode(node) {
    switch (node.type) {
      case 'if':
        return this.buildIf(node);
      case 'for':
      case 'while':
      case 'do':
        return this.buildLoop(node);
      case 'function':
        // A definition is not an execution step. In program flow it would add a
        // tall detour for no runtime reason; the focus menu can show its body.
        if (this.focusKind === 'program') return null;
        return this.buildFunctionNode(node);
      case 'class':
        if (this.focusKind === 'program') return null;
        return this.buildClassNode(node);
      case 'switch':
        return this.buildStructureNode(node, 'SWITCH');
      case 'try':
        return this.buildStructureNode(node, 'TRY / CATCH');
      case 'action':
        return this.buildActionNode(node);
      default:
        return this.buildStructureNode(node, 'STRUCTURE');
    }
  }

  buildFunctionNode(node) {
    const params = node.params.map((param) => param.name).join(', ');
    const flowNode = this.makeNode({
      kind: 'function',
      tag: 'HELPER',
      label: `${node.name}(${params})`,
      sublabel: node.actionCount ? '' : 'defined here · runs when called',
      line: node.startLine,
      endLine: node.startLine
    });
    return this.nodeUnit(flowNode, { line: node.startLine, endLine: node.startLine });
  }

  buildClassNode(node) {
    const flowNode = this.makeNode({
      kind: 'class',
      tag: node.keyword?.toUpperCase?.() ?? 'CLASS',
      label: `${node.keyword ?? 'class'} ${node.name}`,
      sublabel: 'container for related methods',
      line: node.startLine
    });
    return this.nodeUnit(flowNode, { line: node.startLine, endLine: node.startLine });
  }

  buildStructureNode(node, tag) {
    const flowNode = this.makeNode({
      kind: 'structure',
      tag,
      label: node.header ?? node.type,
      sublabel: 'details in Syntax Tree',
      line: node.startLine
    });
    return this.nodeUnit(flowNode, { line: node.startLine, endLine: node.endLine });
  }

  buildActionNode(node) {
    const action = node.action;
    if (!action) return null;
    if (['import', 'comment', 'empty', 'pass'].includes(action.subtype)) return null;
    const terminal = ['return', 'throw', 'break', 'continue'].includes(action.subtype);
    let tag = 'STEP';
    let kind = 'action';
    if (action.subtype === 'declaration') { tag = 'SET'; kind = 'action'; }
    else if (action.subtype === 'assignment') { tag = action.operator && action.operator !== '=' ? 'UPDATE' : 'SET'; kind = 'action'; }
    else if (action.subtype === 'print') { tag = 'OUTPUT'; kind = 'output'; }
    else if (action.subtype === 'return') { tag = 'RETURN'; kind = 'return'; }
    else if (action.subtype === 'break' || action.subtype === 'continue') { tag = 'JUMP'; kind = 'jump'; }
    else if (action.subtype === 'call') { tag = 'CALL'; kind = 'call'; }
    else if (action.subtype === 'update') { tag = 'UPDATE'; kind = 'action'; }
    const label = shortenCode(node.text || node.header || action.raw || 'Statement', 150);
    const flowNode = this.makeNode({
      kind,
      tag,
      label,
      line: node.startLine,
      endLine: node.endLine
    });
    const unit = this.nodeUnit(flowNode, { line: node.startLine, endLine: node.endLine, terminal });
    return unit;
  }

  buildIf(node) {
    const decision = this.makeNode({
      kind: 'decision',
      tag: node.keyword === 'elif' ? 'ELSE IF' : 'IF',
      label: node.condition,
      line: node.startLine,
      endLine: node.startLine,
      width: DECISION_WIDTH
    });
    const thenContent = this.buildSequence(node.consequent) ?? this.placeholderUnit('No statements in this branch');
    const elseContent = node.alternate
      ? this.buildSequence(node.alternate) ?? this.placeholderUnit('No statements in this branch')
      : this.placeholderUnit('Skip the if body');
    const thenBranch = this.branchUnit(thenContent, 'YES', 'yes');
    const elseBranch = this.branchUnit(elseContent, 'NO', 'no');

    const branchesWidth = thenBranch.width + BRANCH_GAP + elseBranch.width;
    const width = Math.max(decision.w, branchesWidth);
    const decisionX = (width - decision.w) / 2;
    const branchTop = decision.h + 38;
    const thenX = (width - branchesWidth) / 2;
    const elseX = thenX + thenBranch.width + BRANCH_GAP;

    const thenShifted = translateUnit(thenBranch, thenX, branchTop);
    const elseShifted = translateUnit(elseBranch, elseX, branchTop);
    const decisionNode = { ...decision, x: decisionX, y: 0 };
    const nodes = [decisionNode, ...thenShifted.nodes, ...elseShifted.nodes];
    const containers = [...thenShifted.containers, ...elseShifted.containers];
    const edges = [...thenShifted.edges, ...elseShifted.edges];
    this.nodeCount += 1;

    const decisionCenter = decisionX + decision.w / 2;
    const yesPort = thenShifted.entry;
    const noPort = elseShifted.entry;
    if (yesPort) {
      edges.push({
        points: [
          [decisionCenter - 32, decision.h],
          [decisionCenter - 32, decision.h + 22],
          [yesPort.x, decision.h + 22],
          [yesPort.x, yesPort.y]
        ],
        kind: 'branch-yes',
        arrow: true
      });
    }
    if (noPort) {
      edges.push({
        points: [
          [decisionCenter + 32, decision.h],
          [decisionCenter + 32, decision.h + 22],
          [noPort.x, decision.h + 22],
          [noPort.x, noPort.y]
        ],
        kind: 'branch-no',
        arrow: true
      });
    }

    const maxBranchHeight = Math.max(thenShifted.height, elseShifted.height);
    const hasExit = !!thenShifted.exit || !!elseShifted.exit;
    const mergeY = branchTop + maxBranchHeight + (hasExit ? 26 : 0);
    if (thenShifted.exit) {
      edges.push({
        points: [
          thenShifted.exit,
          [thenShifted.exit.x, mergeY],
          [width / 2, mergeY]
        ],
        kind: 'merge',
        arrow: false
      });
    }
    if (elseShifted.exit) {
      edges.push({
        points: [
          elseShifted.exit,
          [elseShifted.exit.x, mergeY],
          [width / 2, mergeY]
        ],
        kind: 'merge',
        arrow: false
      });
    }

    return {
      width,
      height: hasExit ? mergeY : branchTop + maxBranchHeight,
      nodes,
      containers,
      edges,
      entry: { x: decisionCenter, y: 0 },
      exit: hasExit ? { x: width / 2, y: mergeY } : null
    };
  }

  buildLoop(node) {
    const style = node.loopMeta?.style ?? (node.type === 'for' ? 'forUnsupported' : 'while');
    let tag = 'LOOP';
    if (node.type === 'for') {
      tag = style === 'forOf' ? 'FOR EACH' : style === 'forIn' ? 'FOR IN' : 'FOR';
    } else if (node.type === 'while') {
      tag = 'WHILE';
    } else if (node.type === 'do') {
      tag = 'DO / WHILE';
    }
    const headerNode = this.makeNode({
      kind: 'loop',
      tag,
      label: node.header ?? node.condition ?? 'Loop',
      sublabel: node.type === 'for' ? 'repeat this block' : '',
      line: node.startLine,
      width: LOOP_WIDTH
    });
    const bodyContent = this.buildSequence(node.body) ?? this.placeholderUnit('Empty loop body');
    const body = this.loopBodyUnit(bodyContent);
    const contentWidth = Math.max(headerNode.w, body.width);
    const width = contentWidth + RAIL * 2;
    const headerX = (width - headerNode.w) / 2;
    const bodyX = (width - body.width) / 2;
    const bodyTop = headerNode.h + 32;
    const shiftedBody = translateUnit(body, bodyX, bodyTop);
    const headerMid = headerNode.h / 2;
    const height = bodyTop + shiftedBody.height + 40;
    const nodes = [{ ...headerNode, x: headerX, y: 0 }, ...shiftedBody.nodes];
    const containers = [...shiftedBody.containers];
    const edges = [...shiftedBody.edges];
    this.nodeCount += 1;

    const centerX = width / 2;
    if (shiftedBody.entry) {
      edges.push({
        points: [[centerX, headerNode.h], [centerX, shiftedBody.entry.y]],
        kind: 'loop-forward',
        arrow: true
      });
    }
    if (shiftedBody.exit) {
      const exitY = shiftedBody.exit.y;
      edges.push({
        points: [
          [centerX, exitY],
          [centerX, exitY + 18],
          [14, exitY + 18],
          [14, headerMid],
          [headerX, headerMid]
        ],
        kind: 'loop-back',
        arrow: true,
        label: 'repeat',
        labelPos: [14, (exitY + 18 + headerMid) / 2]
      });
    }
    const rightRail = width - 14;
    edges.push({
      points: [
        [headerX + headerNode.w, headerMid],
        [rightRail, headerMid],
        [rightRail, height - 12],
        [centerX, height - 12],
        [centerX, height]
      ],
      kind: 'loop-exit',
      arrow: false,
      label: 'exit',
      labelPos: [rightRail, (headerMid + height - 12) / 2]
    });

    return {
      width,
      height,
      nodes,
      containers,
      edges,
      entry: { x: centerX, y: 0 },
      exit: { x: centerX, y: height }
    };
  }

  buildBranchSequenceForIf(block, label) {
    return this.buildSequence(block) ?? this.placeholderUnit(label);
  }

  branchUnit(content, label, tone) {
    const padX = 14;
    const header = 31;
    const padBottom = 12;
    const width = content.width + padX * 2;
    const height = header + content.height + padBottom;
    const shifted = translateUnit(content, padX, header);
    const nodes = shifted.nodes;
    const edges = [...shifted.edges];
    const containers = [
      { x: 0, y: 0, w: width, h: height, tone, label, kind: 'branch' },
      ...shifted.containers
    ];
    let exit = null;
    if (shifted.exit) {
      exit = { x: width / 2, y: height };
      edges.push({
        points: [shifted.exit, [width / 2, height]],
        kind: 'branch-internal',
        arrow: false
      });
    }
    return {
      width,
      height,
      nodes,
      containers,
      edges,
      entry: shifted.entry,
      exit
    };
  }

  loopBodyUnit(content) {
    const pad = 12;
    const width = content.width + pad * 2;
    const height = content.height + pad * 2;
    const shifted = translateUnit(content, pad, pad);
    const containers = [
      { x: 0, y: 0, w: width, h: height, tone: 'loop', label: '', kind: 'loop-body' },
      ...shifted.containers
    ];
    const edges = [...shifted.edges];
    let exit = null;
    if (shifted.exit) {
      exit = { x: width / 2, y: height };
      edges.push({
        points: [shifted.exit, [width / 2, height]],
        kind: 'branch-internal',
        arrow: false
      });
    }
    return {
      width,
      height,
      nodes: shifted.nodes,
      containers,
      edges,
      entry: shifted.entry,
      exit
    };
  }

  placeholderUnit(label) {
    const flowNode = this.makeNode({
      kind: 'note',
      tag: 'PATH',
      label,
      width: 196
    });
    return this.nodeUnit(flowNode, { line: null, endLine: null, terminal: false });
  }

  nodeUnit(flowNode, { line, endLine, terminal = false }) {
    this.nodeCount += 1;
    return {
      width: flowNode.w,
      height: flowNode.h,
      nodes: [{ ...flowNode, line, endLine }],
      containers: [],
      edges: [],
      entry: { x: flowNode.w / 2, y: 0 },
      exit: terminal ? null : { x: flowNode.w / 2, y: flowNode.h }
    };
  }

  terminalUnit(kind, label, tag, line, isEnd = false) {
    const width = 190;
    const height = 54;
    const node = {
      id: `flow-node-${++this.id}`,
      kind,
      tag,
      label,
      sublabel: '',
      line,
      endLine: line,
      x: 0,
      y: 0,
      w: width,
      h: height
    };
    this.nodeCount += 1;
    return {
      width,
      height,
      nodes: [node],
      containers: [],
      edges: [],
      entry: { x: width / 2, y: 0 },
      exit: isEnd ? null : { x: width / 2, y: height }
    };
  }

  makeNode({ kind, tag, label, sublabel = '', line, endLine = line, width }) {
    const defaultWidths = {
      action: NODE_WIDTH,
      output: NODE_WIDTH,
      return: 258,
      jump: 248,
      call: NODE_WIDTH,
      decision: DECISION_WIDTH,
      loop: LOOP_WIDTH,
      function: 300,
      class: 288,
      structure: 282,
      note: 210
    };
    const w = width ?? defaultWidths[kind] ?? NODE_WIDTH;
    const maxChars = Math.max(16, Math.floor((w - 42) / 7.05));
    const lines = wrapText(label, maxChars, kind === 'decision' || kind === 'loop' ? 4 : 3);
    const subLines = sublabel ? wrapText(sublabel, Math.floor((w - 42) / 6.2), 1) : [];
    const lineHeight = 17;
    const h = 12 + 10 + 6 + lines.length * lineHeight + (subLines.length ? 4 + 13 : 0) + 12;
    return {
      id: `flow-node-${++this.id}`,
      kind,
      tag,
      label,
      sublabel,
      line,
      endLine,
      x: 0,
      y: 0,
      w,
      h,
      lines,
      subLines,
      maxChars
    };
  }
}

/* -------------------------------------------------------------------------- */
/* SVG rendering                                                              */
/* -------------------------------------------------------------------------- */

function renderFlowModel(model) {
  const markerId = 'flow-arrowhead';
  const content = `
    ${arrowDefs(markerId)}
    <g class="flow-containers">${model.containers.map(renderContainer).join('')}</g>
    <g class="flow-edges">${model.edges.map((edge, index) => renderEdge(edge, markerId, index)).join('')}</g>
    <g class="flow-nodes">${model.nodes.map((node, index) => renderNode(node, index)).join('')}</g>
  `;
  return svgRoot({
    width: model.width,
    height: model.height,
    content,
    label: 'Interactive program flowchart',
    className: 'flow-svg'
  });
}

function renderContainer(container) {
  const label = container.label
    ? `<g class="branch-label branch-label--${container.tone}" transform="translate(${container.x + 16}, ${container.y + 12})">
        <rect x="0" y="0" width="${Math.max(44, container.label.length * 7 + 20)}" height="20" rx="7"></rect>
        <text x="${Math.max(44, container.label.length * 7 + 20) / 2}" y="13.8" text-anchor="middle">${escapeHTML(container.label)}</text>
      </g>`
    : '';
  return `<g class="flow-container flow-container--${container.tone} ${container.kind === 'loop-body' ? 'flow-container--loop-body' : ''}">
    <rect x="${container.x}" y="${container.y}" width="${container.w}" height="${container.h}" rx="16"></rect>
    ${label}
  </g>`;
}

function renderEdge(edge, markerId, index = 0) {
  const points = edge.points ?? [];
  if (points.length < 2) return '';
  const d = pathWithRoundedCorners(points, 9);
  const isLoopBack = edge.kind === 'loop-back';
  const dash = isLoopBack ? 'stroke-dasharray="5 6"' : '';
  const animation = isLoopBack ? 'flow-edge--fade' : 'flow-edge--draw';
  const pathLength = isLoopBack ? '' : 'pathLength="1"';
  const marker = edge.arrow ? `marker-end="url(#${markerId})"` : '';
  const colorClass = edge.kind === 'branch-yes'
    ? 'flow-edge--yes'
    : edge.kind === 'branch-no'
      ? 'flow-edge--no'
      : isLoopBack || edge.kind === 'loop-exit'
        ? 'flow-edge--loop'
        : '';
  const label = edge.label && edge.labelPos
    ? edgeLabel(edge.label, edge.labelPos[0], edge.labelPos[1], 'flow-edge-label')
    : '';
  return `<path class="flow-edge ${colorClass} ${animation}" style="--i:${index}" d="${d}" ${dash} ${pathLength} ${marker}></path>${label}`;
}

function renderNode(node, index = 0) {
  if (!node) return '';
  if (node.kind === 'start' || node.kind === 'end') {
    return renderTerminalNode(node, index);
  }
  const isDecision = node.kind === 'decision';
  const nodeClass = [
    'diagram-node',
    'flow-node',
    `flow-node--${node.kind}`,
    node.unreachable ? 'is-unreachable' : ''
  ].filter(Boolean).join(' ');
  const tagX = 18;
  const tagY = 21;
  const codeTop = 39;
  const lineBadge = node.line
    ? `<g class="node-line-pill" transform="translate(${node.w - 48}, 14)">
        <rect width="34" height="20" rx="7"></rect>
        <text x="17" y="13.8" text-anchor="middle">L${node.line}</text>
      </g>`
    : '';
  const labelText = node.lines.map((line, index) => (
    `<tspan x="${tagX}" dy="${index === 0 ? 0 : 17}">${escapeHTML(line)}</tspan>`
  )).join('');
  const subTop = codeTop + node.lines.length * 17 + 4;
  const subText = node.subLines?.length
    ? `<text x="${tagX}" y="${subTop}" class="flow-node-sub">${escapeHTML(node.subLines[0])}</text>`
    : '';
  const shape = isDecision
    ? `<path class="flow-node-bg" d="${cutCornerPath(node.w, node.h, 16)}"></path>`
    : `<rect class="flow-node-bg" x="0" y="0" width="${node.w}" height="${node.h}" rx="14"></rect>`;
  const accentClass = `node-dot node-dot--${node.kind}`;
  return `<g class="${nodeClass}" transform="translate(${node.x}, ${node.y})" style="--i:${index}"
      data-node-id="${node.id}" data-line="${node.line ?? ''}" data-end-line="${node.endLine ?? node.line ?? ''}"
      data-label="${escapeHTML(node.tag)}" tabindex="0" role="button"
      aria-label="${escapeHTML(`${node.tag} at line ${node.line ?? '?'}: ${node.label}`)}">
    <title>${escapeHTML(`${node.tag}${node.line ? ` · line ${node.line}` : ''}: ${node.label}`)}</title>
    ${shape}
    <circle class="${accentClass}" cx="14" cy="19" r="3"></circle>
    <text x="${tagX + 10}" y="${tagY}" class="flow-node-tag">${escapeHTML(node.tag)}</text>
    ${lineBadge}
    <text x="${tagX}" y="${codeTop}" class="flow-node-code">${labelText}</text>
    ${subText}
  </g>`;
}

function renderTerminalNode(node, index = 0) {
  const isStart = node.kind === 'start';
  return `<g class="diagram-node flow-node flow-node--${node.kind}" transform="translate(${node.x ?? 0}, ${node.y ?? 0})" style="--i:${index}"
      data-node-id="${node.id}" data-line="${node.line ?? ''}" data-end-line="${node.endLine ?? node.line ?? ''}"
      data-label="${escapeHTML(node.tag)}" tabindex="0" role="button"
      aria-label="${escapeHTML(`${node.tag}: ${node.label}`)}">
    <title>${escapeHTML(`${node.tag}: ${node.label}`)}</title>
    <rect class="flow-node-bg" x="0" y="0" width="${node.w}" height="${node.h}" rx="${node.h / 2}"></rect>
    <circle cx="19" cy="${node.h / 2}" r="4" class="${isStart ? 'terminal-dot terminal-dot--start' : 'terminal-dot terminal-dot--end'}"></circle>
    <text x="31" y="${node.h / 2 + 4.5}" class="terminal-label">${escapeHTML(node.label)}</text>
    <text x="${node.w - 18}" y="${node.h / 2 + 3.5}" text-anchor="end" class="flow-node-tag">${escapeHTML(node.tag)}</text>
  </g>`;
}

function cutCornerPath(w, h, cut) {
  return `M ${cut} 0 H ${w - cut} L ${w} ${cut} V ${h - cut} L ${w - cut} ${h} H ${cut} L 0 ${h - cut} V ${cut} Z`;
}

function pathWithRoundedCorners(rawPoints, radius) {
  const points = rawPoints.map((point) => Array.isArray(point) ? point : [point?.x ?? 0, point?.y ?? 0]);
  if (points.length === 2) {
    return pathFromPoints(points);
  }
  const d = [`M ${points[0][0]} ${points[0][1]}`];
  for (let i = 1; i < points.length - 1; i += 1) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const [x2, y2] = points[i + 1];
    const inLen = Math.hypot(x1 - x0, y1 - y0);
    const outLen = Math.hypot(x2 - x1, y2 - y1);
    if (inLen < 0.001 || outLen < 0.001) {
      d.push(`L ${x1} ${y1}`);
      continue;
    }
    const r = Math.min(radius, inLen / 2, outLen / 2);
    if (!r) {
      d.push(`L ${x1} ${y1}`);
      continue;
    }
    const inX = x1 - ((x1 - x0) / inLen) * r;
    const inY = y1 - ((y1 - y0) / inLen) * r;
    const outX = x1 + ((x2 - x1) / outLen) * r;
    const outY = y1 + ((y2 - y1) / outLen) * r;
    d.push(`L ${inX} ${inY}`);
    d.push(`Q ${x1} ${y1} ${outX} ${outY}`);
  }
  const last = points.at(-1);
  d.push(`L ${last[0]} ${last[1]}`);
  return d.join(' ');
}

function shortenCode(value, limit) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function translateUnit(unit, dx, dy) {
  if (!unit) return null;
  const pointArray = (point) => Array.isArray(point) ? point : [point?.x ?? 0, point?.y ?? 0];
  const shiftPoint = (point) => (point ? { x: point.x + dx, y: point.y + dy } : null);
  return {
    width: unit.width,
    height: unit.height,
    nodes: (unit.nodes ?? []).map((node) => ({ ...node, x: (node.x ?? 0) + dx, y: (node.y ?? 0) + dy, lines: node.lines, subLines: node.subLines })),
    containers: (unit.containers ?? []).map((container) => ({ ...container, x: (container.x ?? 0) + dx, y: (container.y ?? 0) + dy })),
    edges: (unit.edges ?? []).map((edge) => ({
      ...edge,
      points: (edge.points ?? []).map(pointArray).map(([x, y]) => [x + dx, y + dy]),
      labelPos: edge.labelPos ? [edge.labelPos[0] + dx, edge.labelPos[1] + dy] : null
    })),
    entry: shiftPoint(unit.entry),
    exit: shiftPoint(unit.exit)
  };
}
