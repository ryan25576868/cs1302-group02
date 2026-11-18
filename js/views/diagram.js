/**
 * Shared SVG diagram plumbing: safe text, zooming, panning, and the small
 * controls that live in the corner of every visual.
 */

import { icon } from '../icons.js';
import { escapeHTML, clamp } from '../utils.js';

export function svgRoot({ width, height, content, label, className = '' }) {
  return `<svg class="diagram-svg ${className}" xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 ${Math.ceil(width)} ${Math.ceil(height)}"
    width="${Math.ceil(width)}" height="${Math.ceil(height)}"
    role="group" aria-label="${escapeHTML(label ?? 'Code visualization')}">
    ${content}
  </svg>`;
}

export function arrowDefs(id, className = '') {
  return `
    <defs>
      <marker id="${id}" viewBox="0 0 10 10" refX="8.6" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
        <path d="M 1 1.4 L 8.4 5 L 1 8.6 z" class="diagram-arrowhead ${className}"></path>
      </marker>
    </defs>
  `;
}

export function wrapText(text, maxChars, maxLines = 3) {
  const clean = String(text ?? '').replace(/\s+/g, ' ').trim();
  if (!clean) return [''];
  const words = clean.split(' ');
  const lines = [];
  let current = '';
  for (const word of words) {
    if (word.length > maxChars) {
      if (current) {
        lines.push(current);
        current = '';
      }
      let remaining = word;
      while (remaining.length > maxChars && lines.length < maxLines) {
        lines.push(remaining.slice(0, maxChars));
        remaining = remaining.slice(maxChars);
      }
      current = remaining;
      if (lines.length >= maxLines) break;
      continue;
    }
    if (!current) {
      current = word;
    } else if (current.length + 1 + word.length <= maxChars) {
      current += ` ${word}`;
    } else {
      lines.push(current);
      current = word;
      if (lines.length >= maxLines) break;
    }
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (lines.length === maxLines && (words.join(' ').length > lines.join(' ').length)) {
    lines[maxLines - 1] = `${lines[maxLines - 1].replace(/\s+$/, '')}…`;
  }
  return lines;
}

export function textBlock(lines, x, yStart, { lineHeight = 16, className = '', anchor = 'middle' } = {}) {
  return lines
    .map((line, index) => `<text x="${x}" y="${yStart + index * lineHeight}" text-anchor="${anchor}" class="${className}">${escapeHTML(line)}</text>`)
    .join('');
}

export function pathFromPoints(points, { curve = 0, closed = false } = {}) {
  if (!points?.length) return '';
  if (curve && points.length >= 2) {
    let path = `M ${points[0][0]} ${points[0][1]}`;
    for (let i = 1; i < points.length; i += 1) {
      const [x0, y0] = points[i - 1];
      const [x1, y1] = points[i];
      const midY = (y0 + y1) / 2;
      path += ` C ${x0} ${midY}, ${x1} ${midY}, ${x1} ${y1}`;
    }
    return path;
  }
  const [first, ...rest] = points;
  return `M ${first[0]} ${first[1]} ${rest.map(([x, y]) => `L ${x} ${y}`).join(' ')}${closed ? ' Z' : ''}`;
}

export function edgeLabel(text, x, y, className = '') {
  if (!text) return '';
  const width = Math.max(24, String(text).length * 6.4 + 14);
  return `<g class="diagram-edge-label ${className}" transform="translate(${x}, ${y})">
    <rect x="${-width / 2}" y="-10" width="${width}" height="20" rx="7"></rect>
    <text x="0" y="3.5" text-anchor="middle">${escapeHTML(text)}</text>
  </g>`;
}

/**
 * Mount an SVG inside a scrollable stage with zoom controls and drag-to-pan.
 */
export function mountDiagram(stage, {
  width,
  height,
  svg,
  label = 'Code diagram',
  minScale = 0.35,
  maxScale = 1.6,
  initialScale = 1,
  fitOnMount = false,
  showControls = true
}) {
  const baseWidth = Math.max(1, width);
  const baseHeight = Math.max(1, height);
  stage.innerHTML = `
    <div class="diagram-scroll" tabindex="0" aria-label="${escapeHTML(label)}. Use the zoom controls to adjust the view.">
      <div class="diagram-scaler">
        <div class="diagram-natural">${svg}</div>
      </div>
    </div>
    ${showControls ? `
      <div class="diagram-zoom" role="group" aria-label="Diagram zoom">
        <button type="button" class="zoom-button" data-zoom="out" aria-label="Zoom out" title="Zoom out">${icon('zoomOut', 16)}</button>
        <button type="button" class="zoom-level" data-zoom="fit" aria-label="Fit diagram to view" title="Fit to view"><span>100%</span></button>
        <button type="button" class="zoom-button" data-zoom="in" aria-label="Zoom in" title="Zoom in">${icon('zoomIn', 16)}</button>
      </div>
    ` : ''}
  `;
  const scroll = stage.querySelector('.diagram-scroll');
  const scaler = stage.querySelector('.diagram-scaler');
  const natural = stage.querySelector('.diagram-natural');
  const levelLabel = stage.querySelector('.zoom-level span');
  let scale = initialScale;
  let destroyed = false;

  const apply = (next, { scrollTo = null } = {}) => {
    scale = clamp(next, minScale, maxScale);
    scaler.style.width = `${baseWidth * scale}px`;
    scaler.style.height = `${baseHeight * scale}px`;
    natural.style.transform = `scale(${scale})`;
    if (levelLabel) levelLabel.textContent = `${Math.round(scale * 100)}%`;
    scaler.dataset.scale = String(scale);
    if (scrollTo) {
      requestAnimationFrame(() => {
        scroll.scrollLeft = Math.max(0, scrollTo.x ?? scroll.scrollLeft);
        scroll.scrollTop = Math.max(0, scrollTo.y ?? scroll.scrollTop);
      });
    }
  };

  const fit = () => {
    const availableWidth = Math.max(200, stage.clientWidth - 64);
    const availableHeight = Math.max(200, stage.clientHeight - 64);
    const next = Math.min(1.1, availableWidth / baseWidth, availableHeight / baseHeight);
    apply(Math.max(minScale, next));
    requestAnimationFrame(() => {
      scroll.scrollLeft = 0;
      scroll.scrollTop = 0;
    });
  };

  const controls = stage.querySelectorAll('[data-zoom]');
  controls.forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.zoom;
      if (action === 'in') apply(scale + 0.1);
      else if (action === 'out') apply(scale - 0.1);
      else fit();
    });
  });

  let dragging = false;
  let startX = 0;
  let startY = 0;
  let startLeft = 0;
  let startTop = 0;
  const canStartDrag = (target) => {
    if (target.closest('button, a, input, textarea, [data-no-pan]')) return false;
    return true;
  };
  const onPointerDown = (event) => {
    if (event.button !== 0 || !canStartDrag(event.target)) return;
    dragging = true;
    startX = event.clientX;
    startY = event.clientY;
    startLeft = scroll.scrollLeft;
    startTop = scroll.scrollTop;
    scroll.classList.add('is-dragging');
    scroll.setPointerCapture?.(event.pointerId);
  };
  const onPointerMove = (event) => {
    if (!dragging) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (Math.abs(dx) + Math.abs(dy) > 3) event.preventDefault();
    scroll.scrollLeft = startLeft - dx;
    scroll.scrollTop = startTop - dy;
  };
  const onPointerUp = (event) => {
    dragging = false;
    scroll.classList.remove('is-dragging');
    scroll.releasePointerCapture?.(event.pointerId);
  };
  scroll.addEventListener('pointerdown', onPointerDown);
  scroll.addEventListener('pointermove', onPointerMove);
  scroll.addEventListener('pointerup', onPointerUp);
  scroll.addEventListener('pointercancel', onPointerUp);

  const observer = new ResizeObserver(() => {
    if (fitOnMount && !destroyed && !userAdjusted) fit();
  });
  observer.observe(stage);

  let userAdjusted = false;
  controls.forEach((button) => button.addEventListener('click', () => { userAdjusted = true; }));

  apply(initialScale);
  if (fitOnMount) requestAnimationFrame(fit);

  return {
    stage,
    fit,
    setScale(next) {
      userAdjusted = true;
      apply(next);
    },
    destroy() {
      destroyed = true;
      observer.disconnect();
      scroll.removeEventListener('pointerdown', onPointerDown);
      scroll.removeEventListener('pointermove', onPointerMove);
      scroll.removeEventListener('pointerup', onPointerUp);
      scroll.removeEventListener('pointercancel', onPointerUp);
    }
  };
}

/** Attach delegated selection handling to nodes in a stage. */
export function bindNodeSelection(stage, onSelect) {
  const activate = (target) => {
    const node = target.closest('[data-node-id]');
    if (!node || node.closest('[data-no-select]')) return;
    if (!node.dataset.line) return;
    const line = Number(node.dataset.line);
    const endLine = Number(node.dataset.endLine || node.dataset.line);
    if (!Number.isFinite(line)) return;
    const label = node.dataset.label || node.getAttribute('aria-label') || '';
    onSelect?.({
      line,
      endLine: Number.isFinite(endLine) ? endLine : line,
      label,
      nodeId: node.dataset.nodeId
    });
  };
  stage.addEventListener('click', (event) => {
    if (event.target.closest('[data-tree-toggle]')) return;
    activate(event.target);
  });
  stage.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const node = event.target.closest('[data-node-id]');
    if (!node) return;
    event.preventDefault();
    activate(node);
  });
}

export function statusBarMarkup({ legend = [], hint = '', className = '' } = {}) {
  const items = legend
    .map((item) => `<span class="legend-item"><span class="legend-swatch ${item.className ?? ''}" aria-hidden="true"></span>${escapeHTML(item.label)}</span>`)
    .join('');
  return `<div class="diagram-footer ${className}">
    <div class="diagram-legend">${items}</div>
    ${hint ? `<span class="diagram-hint">${escapeHTML(hint)}</span>` : ''}
  </div>`;
}
