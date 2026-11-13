/**
 * Data Flow view.
 *
 * Assignments are grouped by source location, so a line that runs many times in
 * a loop becomes one card showing its value history. Cards are arranged in
 * dependency layers and joined by arrows that reveal where values came from.
 */

import { escapeHTML } from '../utils.js';
import {
  svgRoot,
  arrowDefs,
  mountDiagram,
  bindNodeSelection,
  statusBarMarkup
} from './diagram.js';

const CARD_W = 236;
const CARD_H = 126;
const H_GAP = 22;
const V_GAP = 76;
const TOP = 42;
const LEFT_GUTTER = 96;
const RIGHT_MARGIN = 24;

export function renderDataFlow(container, analysis, trace, options = {}) {
  const model = buildDataModel(analysis, trace);
  if (!model.groups.length) {
    container.innerHTML = `<div class="view-empty">
      <div class="view-empty-icon">${iconFallback()}</div>
      <h3>No stored values to map yet</h3>
      <p>Data Flow appears when the program assigns values. Add a declaration or an assignment and try again.</p>
    </div>`;
    const footer = statusBarMarkup({ hint: 'Arrows reveal which values feed each assignment' });
    return {
      footer,
      highlightLine() {},
      destroy() {
        container.innerHTML = '';
      }
    };
  }

  const svg = renderDataSvg(model);
  const stageWidth = Math.max(320, container.clientWidth || 700);
  const initialScale = Math.min(1, Math.max(0.72, (stageWidth - 58) / model.width));
  const view = mountDiagram(container, {
    width: model.width,
    height: model.height,
    svg,
    label: 'Data flow graph showing values and dependencies',
    initialScale,
    fitOnMount: false,
    minScale: 0.35,
    maxScale: 1.8
  });

  let activeLine = null;
  bindNodeSelection(container, (selection) => {
    if (!Number.isFinite(selection.line)) return;
    activeLine = selection.line;
    setLinked(container, selection.line);
    options.onSelectLine?.({ line: selection.line, endLine: selection.line, label: selection.label, source: 'data' });
  });

  const footer = statusBarMarkup({
    legend: [
      { label: 'Value', className: 'swatch--data-values' },
      { label: 'Dependency', className: 'swatch--data-link' },
      { label: 'Repeated update', className: 'swatch--decision' }
    ],
    hint: trace?.complete
      ? 'Cards show value history from the sample run · Click a card to see its line'
      : 'Some values may be unavailable because the trace stopped early'
  });

  return {
    footer,
    highlightLine(line) {
      activeLine = line;
      setLinked(container, line);
    },
    destroy() {
      view.destroy();
    },
    groupCount: model.groups.length,
    truncated: model.truncated
  };
}

function setLinked(container, line) {
  container.querySelectorAll('[data-node-id]').forEach((node) => {
    node.classList.toggle('is-linked', Number(node.dataset.line) === Number(line));
  });
}

function buildDataModel(analysis, trace) {
  const useTrace = !!trace?.events?.length;
  const groups = [];
  const map = new Map();
  let order = 0;
  const sourceEvents = useTrace
    ? trace.events.filter((event) => ['assignment', 'loop-target'].includes(event.kind))
    : [];

  if (sourceEvents.length) {
    for (const event of sourceEvents) {
      if (!event.target) continue;
      const key = `${event.scope}|${event.line}|${event.target}`;
      let group = map.get(key);
      if (!group) {
        group = {
          key,
          name: event.target,
          scope: event.scope,
          line: event.line,
          expressionText: event.expressionText ?? '',
          expressions: [],
          operator: event.operator ?? null,
          values: [],
          valueTypes: [],
          dependencies: new Set(),
          events: [],
          firstOrder: order++,
          kind: event.kind,
          repeated: false
        };
        map.set(key, group);
        groups.push(group);
      }
      group.events.push(event);
      if (event.expressionText) group.expressions.push(event.expressionText);
      group.expressionText = event.expressionText ?? group.expressionText;
      for (const dependency of event.dependencies ?? []) group.dependencies.add(dependency);
      const last = group.values[group.values.length - 1];
      if (last !== event.value) group.values.push(event.value);
      group.valueTypes.push(event.valueType);
      if (group.events.length > 1) group.repeated = true;
    }
  } else {
    for (const assignment of analysis.assignments) {
      if (!assignment.target) continue;
      const key = `${assignment.scope}|${assignment.line}|${assignment.target}`;
      if (map.has(key)) continue;
      const group = {
        key,
        name: assignment.target,
        scope: assignment.scope,
        line: assignment.line,
        expressionText: assignment.expressionText ?? '',
        expressions: assignment.expressionText ? [assignment.expressionText] : [],
        operator: assignment.operator ?? null,
        values: [assignment.expressionText ? compactExpression(assignment.expressionText) : '—'],
        valueTypes: ['unknown'],
        dependencies: new Set(assignment.dependencies ?? []),
        events: [],
        firstOrder: order++,
        kind: 'assignment',
        repeated: false
      };
      map.set(key, group);
      groups.push(group);
    }
  }

  // Remove fields that are not helpful as visible edges.
  const knownNames = new Set(groups.map((group) => group.name));
  const truncated = groups.length > 18;
  const visibleGroups = groups.slice(0, 18);
  for (const group of visibleGroups) {
    group.dependencies = new Set(
      [...group.dependencies].filter((name) => knownNames.has(name))
    );
    group.layer = 0;
    group.inputs = [];
  }
  for (const group of visibleGroups) {
    for (const dependency of group.dependencies) {
      const candidates = visibleGroups
        .filter((candidate) => candidate !== group && candidate.name === dependency && candidate.firstOrder < group.firstOrder)
        .sort((a, b) => b.firstOrder - a.firstOrder);
      if (candidates[0] && !group.inputs.includes(candidates[0])) {
        group.inputs.push(candidates[0]);
        group.layer = Math.max(group.layer, candidates[0].layer + 1);
      }
    }
  }

  // Guard against pathological depth in huge snippets.
  const maxLayer = Math.max(0, ...visibleGroups.map((group) => group.layer));
  for (const group of visibleGroups) {
    if (group.layer > maxLayer) group.layer = maxLayer;
  }

  const layers = [];
  for (const group of visibleGroups) {
    if (!layers[group.layer]) layers[group.layer] = [];
    layers[group.layer].push(group);
  }

  const rows = layers
    .map((column, layer) => ({ column: column ?? [], layer }))
    .filter((row) => row.column.length > 0);
  const rowWidths = rows.map((row) => row.column.length * CARD_W + Math.max(0, row.column.length - 1) * H_GAP);
  const maxRowWidth = Math.max(CARD_W, ...rowWidths);
  const width = LEFT_GUTTER + maxRowWidth + RIGHT_MARGIN;
  const labels = ['SOURCE', 'DERIVED', 'DEPENDENT', 'FURTHER', 'LATER'];
  rows.forEach((row, rowIndex) => {
    row.y = TOP + rowIndex * (CARD_H + V_GAP);
    row.centerY = row.y + CARD_H / 2;
    row.label = labels[Math.min(rowIndex, labels.length - 1)];
    row.width = row.column.length * CARD_W + Math.max(0, row.column.length - 1) * H_GAP;
    const startX = LEFT_GUTTER + (maxRowWidth - row.width) / 2;
    row.column.forEach((group, cardIndex) => {
      group.x = startX + cardIndex * (CARD_W + H_GAP);
      group.y = row.y;
      group.w = CARD_W;
      group.h = CARD_H;
      group.rowIndex = rowIndex;
    });
  });
  const lastRow = rows.at(-1);
  const height = lastRow ? lastRow.y + CARD_H + 42 : 220;

  return {
    groups: visibleGroups,
    layers,
    rows,
    width,
    height,
    truncated,
    traceBacked: useTrace && !!trace?.complete
  };
}

function renderDataSvg(model) {
  const markerId = 'data-arrowhead';
  const edges = [];
  for (const group of model.groups) {
    for (const input of group.inputs) {
      const startX = input.x + input.w / 2;
      const startY = input.y + input.h;
      const endX = group.x + group.w / 2;
      const endY = group.y;
      const midY = startY + (endY - startY) * 0.48;
      edges.push({
        d: `M ${startX} ${startY} C ${startX} ${midY}, ${endX} ${midY}, ${endX} ${endY}`,
        kind: group.kind === 'loop-target' ? 'loop' : 'data',
        label: input.name === group.name ? 'previous value' : input.name
      });
    }
  }

  const railX = 74;
  const rows = model.rows ?? [];
  const firstRow = rows[0];
  const lastRow = rows.at(-1);
  const rowsMarkup = firstRow && lastRow
    ? `<g class="data-rows">
        <line class="data-rail" x1="${railX}" y1="${firstRow.centerY}" x2="${railX}" y2="${lastRow.centerY}"></line>
        ${rows.map((row) => `
          <g class="data-row">
            <text x="${railX - 13}" y="${row.centerY + 3.5}" text-anchor="end" class="data-row-label">${row.label}</text>
            <circle cx="${railX}" cy="${row.centerY}" r="3.5" class="data-rail-dot"></circle>
            <line x1="${railX}" y1="${row.centerY}" x2="${railX + 11}" y2="${row.centerY}" class="data-rail-tick"></line>
          </g>
        `).join('')}
      </g>`
    : '';

  const content = `
    ${arrowDefs(markerId)}
    <g class="data-rows">${rowsMarkup}</g>
    <g class="data-edges">
      ${edges.map((edge, index) => {
        const draw = edge.kind !== 'loop';
        return `<path class="data-edge data-edge--${edge.kind} ${draw ? 'data-edge--draw' : 'data-edge--fade'}"
          style="--i:${index}" ${draw ? 'pathLength="1"' : ''} d="${edge.d}" marker-end="url(#${markerId})"></path>`;
      }).join('')}
    </g>
    <g class="data-nodes">${model.groups.map((group, index) => renderDataCard(group, index)).join('')}</g>
    <g class="data-depth-note">
      <text x="${LEFT_GUTTER}" y="${model.height - 12}" class="data-axis-label">Values flow downward from the values they depend on.</text>
    </g>
  `;

  return svgRoot({
    width: model.width,
    height: model.height,
    content,
    label: 'Value dependency graph',
    className: 'data-svg'
  });
}

function renderDataCard(group, index = 0) {
  const values = group.values.length ? group.values : ['—'];
  const displayValues = values.slice(0, 5);
  let valueLine = displayValues.join('  →  ');
  let extra = values.length > 5 ? `  +${values.length - 5}` : '';
  if (valueLine.length > 30) {
    const first = shorten(displayValues[0], 10);
    const last = shorten(displayValues.at(-1), 12);
    valueLine = `${first} → … → ${last}`;
    if (values.length > displayValues.length) extra = `  +${values.length - 2}`;
  }
  const type = pickType(group.valueTypes);
  const scope = group.scope && group.scope !== 'Global' ? group.scope : '';
  const count = group.events.length;
  const expression = group.expressionText ? shorten(group.expressionText, 46) : '';
  const op = group.operator && group.operator !== '=' ? group.operator : '=';
  const label = `${group.name}${group.operator ?? '='}${group.expressionText ?? ''}`;
  const pillWidth = Math.min(CARD_W - 36, Math.max(80, valueLine.length * 7.1 + extra.length * 7 + 22));
  const exprText = expression ? `${op} ${expression}` : '';
  const inputNames = [...new Set((group.inputs ?? []).map((input) => input.name))].slice(0, 3);
  const detailText = `${group.repeated ? `${count} updates` : 'one value'}${inputNames.length ? ` · reads ${inputNames.join(', ')}` : ''}${scope ? ` · ${scope}` : ''}`;
  return `<g class="diagram-node data-node data-node--${type} ${group.repeated ? 'is-repeated' : ''}" transform="translate(${group.x}, ${group.y})" style="--i:${index}"
      data-node-id="data-${escapeHTML(group.key)}" data-line="${group.line}" data-end-line="${group.line}"
      data-label="${escapeHTML(group.name)}" tabindex="0" role="button"
      aria-label="${escapeHTML(`Line ${group.line}: ${group.name} values ${valueLine}`)}">
    <title>${escapeHTML(`Line ${group.line}: ${label}\nValues: ${valueLine}`)}</title>
    <rect class="data-card-bg" x="0" y="0" width="${CARD_W}" height="${CARD_H}" rx="14"></rect>
    <rect class="data-card-accent" x="0" y="16" width="3" height="${CARD_H - 32}" rx="1.5"></rect>
    <text x="18" y="25" class="data-var-name">${escapeHTML(group.name)}</text>
    <text x="${CARD_W - 16}" y="24" text-anchor="end" class="data-line-label">L${group.line}</text>
    <g class="data-value-pill">
      <rect x="18" y="37" width="${pillWidth}" height="28" rx="8"></rect>
      <text x="29" y="55" class="data-value-text">${escapeHTML(valueLine)}${escapeHTML(extra)}</text>
    </g>
    <text x="18" y="86" class="data-expression">${escapeHTML(exprText || 'value recorded')}</text>
    <g class="data-node-footer">
      <text x="18" y="109" class="data-detail">${escapeHTML(shorten(detailText, 37))}</text>
      ${group.kind === 'loop-target' ? `<text x="${CARD_W - 16}" y="109" text-anchor="end" class="data-type-label">loop value</text>` : `<text x="${CARD_W - 16}" y="109" text-anchor="end" class="data-type-label">${escapeHTML(type)}</text>`}
    </g>
  </g>`;
}

function pickType(types) {
  const important = types.filter((type) => type && !['undefined', 'uninitialized', 'unknown'].includes(type));
  if (important.includes('array')) return 'array';
  if (important.includes('string')) return 'text';
  if (important.includes('boolean')) return 'boolean';
  if (important.includes('number')) return 'number';
  return 'unknown';
}

function compactExpression(value) {
  return shorten(String(value ?? '').replace(/\s+/g, ' ').trim(), 34) || '—';
}

function shorten(value, limit) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function iconFallback() {
  return '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="5.5" cy="6" r="2.5"/><circle cx="18.5" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8 6h8M7 8l4 7.5M17 8l-4 7.5"/></svg>';
}
