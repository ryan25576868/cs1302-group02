/**
 * Syntax tree view.
 *
 * A collapsible, indented tree keeps a potentially wide AST readable inside the
 * workbench. Structural nodes start expanded; expression detail starts folded
 * so a beginner is not hit with every leaf at once.
 */

import { buildSyntaxTree } from '../core/syntax-tree.js';
import { escapeHTML } from '../utils.js';
import { icon } from '../icons.js';
import { statusBarMarkup } from './diagram.js';

export function renderSyntaxTree(container, analysis, options = {}) {
  const tree = buildSyntaxTree(analysis);
  const model = inheritLines(tree.root, null);
  const defaultCollapsed = new Set();
  collectDefaultCollapsed(model, defaultCollapsed, 0);
  const collapsed = new Set(defaultCollapsed);
  let selectedLine = null;
  let scrollTop = 0;
  let scrollLeft = 0;
  let rendered = null;

  const setCollapsedAndRender = (nextCollapsed) => {
    const scroll = container.querySelector('.tree-scroll');
    scrollTop = scroll?.scrollTop ?? scrollTop;
    scrollLeft = scroll?.scrollLeft ?? scrollLeft;
    collapsed.clear();
    nextCollapsed.forEach((id) => collapsed.add(id));
    render();
  };

  const render = (animate = false) => {
    container.innerHTML = `
      <div class="tree-scroll">
        <div class="tree-toolbar">
          <div class="tree-count">
            <span class="tree-count-dot" aria-hidden="true"></span>
            <span>${tree.count} nodes${tree.truncated ? ' · shortened for readability' : ''}</span>
          </div>
          <div class="tree-actions">
            <button type="button" class="mini-button" data-tree-action="expand">${icon('layers', 14)} Expand all</button>
            <button type="button" class="mini-button" data-tree-action="fold">${icon('chevronRight', 14)} Fold details</button>
          </div>
        </div>
        <div class="syntax-tree ${animate ? 'is-entering' : ''}" role="tree" aria-label="Syntax tree">
          ${renderNode(model, collapsed, 0)}
        </div>
      </div>
    `;
    rendered = container.querySelector('.syntax-tree');
    const scroll = container.querySelector('.tree-scroll');
    scroll.scrollTop = scrollTop;
    scroll.scrollLeft = scrollLeft;
    if (selectedLine) applyLinked(selectedLine);
  };

  const onClick = (event) => {
    const toggle = event.target.closest('[data-tree-toggle]');
    if (toggle) {
      event.preventDefault();
      event.stopPropagation();
      const id = toggle.dataset.treeToggle;
      if (collapsed.has(id)) collapsed.delete(id);
      else collapsed.add(id);
      const scroll = container.querySelector('.tree-scroll');
      scrollTop = scroll?.scrollTop ?? 0;
      scrollLeft = scroll?.scrollLeft ?? 0;
      render();
      return;
    }
    const action = event.target.closest('[data-tree-action]');
    if (action) {
      if (action.dataset.treeAction === 'expand') setCollapsedAndRender(new Set());
      else setCollapsedAndRender(defaultCollapsed);
      return;
    }
    const node = event.target.closest('[data-node-id]');
    if (!node) return;
    const line = Number(node.dataset.line);
    if (!Number.isFinite(line) || !line) return;
    selectedLine = line;
    applyLinked(line);
    options.onSelectLine?.({ line, endLine: line, label: node.dataset.label, source: 'tree' });
  };

  const onKeyDown = (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const node = event.target.closest('[data-node-id]');
    if (!node || event.target.closest('[data-tree-toggle]')) return;
    event.preventDefault();
    const line = Number(node.dataset.line);
    if (!Number.isFinite(line) || !line) return;
    selectedLine = line;
    applyLinked(line);
    options.onSelectLine?.({ line, endLine: line, label: node.dataset.label, source: 'tree' });
  };

  const applyLinked = (line) => {
    const nodes = container.querySelectorAll('[data-node-id]');
    nodes.forEach((node) => {
      node.classList.toggle('is-linked', Number(node.dataset.line) === line);
    });
  };

  render(true);
  container.addEventListener('click', onClick);
  container.addEventListener('keydown', onKeyDown);

  const footer = statusBarMarkup({
    legend: [
      { label: 'Structure', className: 'swatch--structure' },
      { label: 'Declaration', className: 'swatch--declaration' },
      { label: 'Control', className: 'swatch--decision' },
      { label: 'Function', className: 'swatch--function' },
      { label: 'Expression', className: 'swatch--expression' }
    ],
    hint: 'Click a card to reveal its code · Use + / − to fold branches'
  });

  return {
    footer,
    highlightLine(line) {
      selectedLine = line;
      applyLinked(line);
      const first = [...container.querySelectorAll('[data-node-id]')].find((node) => Number(node.dataset.line) === line);
      const scroller = container.querySelector('.tree-scroll');
      if (first && scroller) {
        const nodeRect = first.getBoundingClientRect();
        const scrollRect = scroller.getBoundingClientRect();
        const top = nodeRect.top - scrollRect.top + scroller.scrollTop;
        scroller.scrollTo({
          top: Math.max(0, top - scroller.clientHeight / 2 + nodeRect.height / 2),
          behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
        });
      }
    },
    destroy() {
      container.removeEventListener('click', onClick);
      container.removeEventListener('keydown', onKeyDown);
      container.innerHTML = '';
    },
    getRenderedNodeCount() {
      return rendered?.querySelectorAll('[data-node-id]').length ?? 0;
    }
  };
}

function inheritLines(node, parentLine) {
  const line = node.line ?? parentLine ?? null;
  return {
    ...node,
    line,
    children: node.children.map((child) => inheritLines(child, line))
  };
}

function collectDefaultCollapsed(node, set, depth) {
  if (!node) return;
  const foldable = node.children.length > 0;
  if (foldable && depth > 0) {
    const category = node.category;
    if (['expression', 'call', 'literal'].includes(category)) {
      set.add(node.id);
    }
    if (node.type === 'Parameters' && node.children.length > 4) {
      set.add(node.id);
    }
  }
  node.children.forEach((child) => collectDefaultCollapsed(child, set, depth + 1));
}

const KIND_LABELS = {
  Program: 'Program',
  FunctionDeclaration: 'Function',
  ClassDeclaration: 'Class',
  InterfaceDeclaration: 'Interface',
  Parameters: 'Parameters',
  Parameter: 'Parameter',
  Block: 'Block',
  IfStatement: 'If statement',
  ElifStatement: 'Else if',
  ForStatement: 'For loop',
  ForOfStatement: 'For…of loop',
  ForInStatement: 'For…in loop',
  WhileStatement: 'While loop',
  DoWhileStatement: 'Do…while',
  SwitchStatement: 'Switch',
  TryStatement: 'Try',
  CatchClause: 'Catch',
  VariableDeclaration: 'Variable',
  Assignment: 'Assignment',
  PrintStatement: 'Output',
  ReturnStatement: 'Return',
  BreakStatement: 'Break',
  ContinueStatement: 'Continue',
  ExpressionStatement: 'Expression',
  CallExpression: 'Call',
  MemberExpression: 'Member access',
  BinaryExpression: 'Binary operation',
  LogicalExpression: 'Logic',
  UnaryExpression: 'Unary operation',
  UpdateExpression: 'Update',
  AssignmentExpression: 'Assignment',
  ConditionalExpression: 'Conditional',
  ArrayExpression: 'Array',
  ObjectExpression: 'Object',
  Literal: 'Literal',
  Identifier: 'Name',
  ImportDeclaration: 'Import',
  MoreStatements: 'More',
  RawExpression: 'Raw expression'
};

function kindLabel(type) {
  if (KIND_LABELS[type]) return KIND_LABELS[type];
  return String(type ?? 'Node')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/Statement$/, ' statement')
    .replace(/Expression$/, ' expression');
}

function renderNode(node, collapsed, depth, counter = { value: 0 }) {
  if (!node) return '';
  const motionIndex = counter.value++;
  const isCollapsed = collapsed.has(node.id);
  const hasChildren = node.children.length > 0;
  const kind = kindLabel(node.type);
  const toggle = hasChildren
    ? `<button type="button" class="syntax-toggle ${isCollapsed ? 'is-collapsed' : ''}"
        data-tree-toggle="${node.id}" aria-expanded="${!isCollapsed}"
        aria-label="${isCollapsed ? 'Expand' : 'Fold'} ${escapeHTML(kind)}">${icon(isCollapsed ? 'chevronRight' : 'chevronDown', 13)}</button>`
    : '<span class="syntax-toggle-spacer" aria-hidden="true"></span>';
  const meta = node.meta ? `<span class="syntax-node-meta">${escapeHTML(node.meta)}</span>` : '';
  const line = node.line ? `<span class="syntax-node-line">L${node.line}</span>` : '';
  const label = escapeHTML(node.label || kind);
  const children = hasChildren && !isCollapsed
    ? `<div class="syntax-children" role="group">${node.children.map((child) => renderNode(child, collapsed, depth + 1, counter)).join('')}</div>`
    : '';
  const collapsedBadge = isCollapsed && node.descendantCount > 0
    ? `<span class="syntax-fold-badge">+${node.descendantCount}</span>`
    : '';
  return `<div class="syntax-row" role="treeitem" aria-level="${depth + 1}" ${hasChildren ? `aria-expanded="${!isCollapsed}"` : ''}>
    <div class="syntax-node syntax-node--${node.category} ${node.category === 'root' ? 'syntax-node--root' : ''}"
      style="--i:${motionIndex}"
      data-node-id="${node.id}" data-line="${node.line ?? ''}" tabindex="0" role="button"
      data-label="${escapeHTML(kind)}" aria-label="${escapeHTML(`${kind}: ${node.label || ''}${node.line ? `, line ${node.line}` : ''}`)}">
      <span class="syntax-branch-dot" aria-hidden="true"></span>
      ${toggle}
      <span class="syntax-kind">${escapeHTML(kind)}</span>
      <span class="syntax-label">${label}</span>
      ${collapsedBadge}
      ${meta}
      ${line}
    </div>
    ${children}
  </div>`;
}
