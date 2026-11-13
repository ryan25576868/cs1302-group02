/**
 * Live Trace view.
 *
 * Plays back the interpreter's recorded steps. The trace is already bounded and
 * safe by the time it reaches this view; playback only changes which snapshot
 * is visible.
 */

import { escapeHTML } from '../utils.js';
import { icon } from '../icons.js';
import { statusBarMarkup } from './diagram.js';

const SPEEDS = [
  { value: '0.5', label: '0.5×' },
  { value: '1', label: '1×' },
  { value: '1.5', label: '1.5×' },
  { value: '2', label: '2×' }
];

export function renderTrace(container, analysis, trace, options = {}) {
  if (!trace?.steps?.length) {
    container.innerHTML = `<div class="view-empty">
      <div class="view-empty-icon">${icon('trace', 26)}</div>
      <h3>No trace available</h3>
      <p>The interpreter could not record any steps for this snippet. Flowchart and Syntax Tree still show its structure.</p>
    </div>`;
    return {
      footer: statusBarMarkup({ hint: 'Live Trace uses a safe local interpreter' }),
      highlightLine() {},
      destroy() {
        container.innerHTML = '';
      }
    };
  }

  const steps = trace.steps;
  let index = 0;
  let playing = false;
  let timer = null;
  let speed = 1;
  let lastHighlighted = null;

  container.innerHTML = `
    <div class="trace-shell" tabindex="0" aria-label="Interactive execution trace">
      <div class="trace-statusbar">
        <div class="trace-run-label"><span class="trace-live-dot"></span> Safe simulated run</div>
        <div class="trace-progress-wrap">
          <span class="trace-step-label" data-step-label>Step 1 of ${steps.length}</span>
          <div class="trace-progress-track"><span class="trace-progress-fill" data-progress></span></div>
        </div>
        <span class="trace-completion ${trace.complete ? 'is-complete' : 'is-partial'}">
          ${trace.complete ? 'Complete run' : 'Partial trace'}
        </span>
      </div>
      ${!trace.complete ? `<div class="trace-warning">
        <span class="trace-warning-icon">${icon('warning', 16)}</span>
        <p><strong>The trace stopped early.</strong> ${escapeHTML(trace.stoppedReason || trace.warnings?.[0]?.message || 'This snippet uses syntax outside the interpreter’s safe subset.')} The other views still show the full structure.</p>
      </div>` : ''}
      <div class="trace-content">
        <div class="trace-story">
          <article class="trace-event-card" data-event-card>
            <div class="trace-event-top">
              <span class="trace-event-icon" data-event-icon>${icon('play', 17)}</span>
              <span class="trace-event-kind" data-event-kind>START</span>
              <span class="trace-event-line" data-event-line>L1</span>
            </div>
            <h3 class="trace-event-title" data-event-title></h3>
            <p class="trace-event-detail" data-event-detail></p>
          </article>
          <section class="trace-code-box" aria-label="Current source line">
            <div class="trace-code-head"><span>What is running</span><span class="trace-code-line" data-code-line>L1</span></div>
            <pre class="trace-code" data-code></pre>
          </section>
          <section class="trace-callstack">
            <div class="trace-section-head"><h3>Call stack</h3><span data-callstack-count>Global</span></div>
            <div class="trace-callstack-list" data-callstack></div>
          </section>
          <div class="trace-preview-grid" data-trace-preview>
            <button type="button" class="trace-preview" data-trace="prev">
              <span class="trace-preview-label">← Before</span>
              <span class="trace-preview-title">This is the beginning</span>
            </button>
            <button type="button" class="trace-preview" data-trace="next">
              <span class="trace-preview-label">Next →</span>
              <span class="trace-preview-title">The first step is next</span>
            </button>
          </div>
        </div>
        <div class="trace-side">
          <section class="trace-vars-panel">
            <div class="trace-section-head"><h3>Variables</h3><span data-vars-count>0 values</span></div>
            <div class="trace-vars" data-vars></div>
          </section>
          <section class="trace-output-panel">
            <div class="trace-section-head"><h3>Terminal</h3><span class="trace-output-state">stdout</span></div>
            <pre class="trace-output" data-output></pre>
          </section>
        </div>
      </div>
      <div class="trace-controls">
        <div class="trace-controls-buttons">
          <button type="button" class="trace-btn" data-trace="reset" aria-label="Reset trace" title="Reset">${icon('reset', 17)}</button>
          <button type="button" class="trace-btn" data-trace="prev" aria-label="Previous step" title="Previous step">${icon('stepBack', 17)}</button>
          <button type="button" class="trace-play" data-trace="play" aria-label="Play trace" title="Play / pause">${icon('play', 17)}</button>
          <button type="button" class="trace-btn" data-trace="next" aria-label="Next step" title="Next step">${icon('stepForward', 17)}</button>
        </div>
        <div class="trace-slider-wrap">
          <input type="range" min="0" max="${steps.length - 1}" step="1" value="0" class="trace-slider" data-trace="slider" aria-label="Trace position">
        </div>
        <label class="trace-speed">
          <span>Speed</span>
          <select data-trace="speed" aria-label="Playback speed">
            ${SPEEDS.map((item) => `<option value="${item.value}" ${item.value === '1' ? 'selected' : ''}>${item.label}</option>`).join('')}
          </select>
        </label>
      </div>
      <p class="trace-keyboard-hint">
        ${icon('keyboard', 14)}
        <span>← / → to step · Space to play or pause</span>
        <span class="trace-legend-key"><span class="trace-change-dot"></span> changed value</span>
      </p>
    </div>
  `;

  const refs = {
    shell: container.querySelector('.trace-shell'),
    eventCard: container.querySelector('[data-event-card]'),
    eventIcon: container.querySelector('[data-event-icon]'),
    eventKind: container.querySelector('[data-event-kind]'),
    eventLine: container.querySelector('[data-event-line]'),
    eventTitle: container.querySelector('[data-event-title]'),
    eventDetail: container.querySelector('[data-event-detail]'),
    codeLine: container.querySelector('[data-code-line]'),
    code: container.querySelector('[data-code]'),
    callstack: container.querySelector('[data-callstack]'),
    callstackCount: container.querySelector('[data-callstack-count]'),
    vars: container.querySelector('[data-vars]'),
    varsCount: container.querySelector('[data-vars-count]'),
    output: container.querySelector('[data-output]'),
    stepLabel: container.querySelector('[data-step-label]'),
    progress: container.querySelector('[data-progress]'),
    slider: container.querySelector('[data-trace="slider"]'),
    play: container.querySelector('[data-trace="play"]'),
    prev: container.querySelector('[data-trace="prev"]'),
    next: container.querySelector('[data-trace="next"]'),
    reset: container.querySelector('[data-trace="reset"]'),
    speed: container.querySelector('[data-trace="speed"]'),
    preview: container.querySelector('[data-trace-preview]')
  };

  function renderStep(nextIndex, { preserveScroll = false } = {}) {
    index = Math.max(0, Math.min(nextIndex, steps.length - 1));
    const step = steps[index];
    refs.shell.classList.remove('kind-start', 'kind-end', 'kind-assign', 'kind-condition', 'kind-loop-check', 'kind-call', 'kind-return', 'kind-print', 'kind-stopped', 'kind-function-entry', 'kind-iteration', 'kind-break', 'kind-continue', 'kind-update');
    refs.shell.classList.add(`kind-${step.kind}`);
    refs.eventKind.textContent = kindLabel(step.kind);
    refs.eventIcon.innerHTML = icon(kindIcon(step.kind), 17);
    refs.eventLine.textContent = step.line ? `L${step.line}` : '';
    refs.eventTitle.textContent = step.title;
    refs.eventDetail.textContent = step.detail;
    refs.eventCard.classList.remove('is-stepping');
    void refs.eventCard.offsetWidth;
    refs.eventCard.classList.add('is-stepping');
    refs.codeLine.textContent = step.line ? `Line ${step.line}` : '';
    refs.code.innerHTML = renderCode(analysis, step);

    refs.stepLabel.textContent = `Step ${index + 1} of ${steps.length}`;
    refs.progress.style.width = `${((index + 1) / steps.length) * 100}%`;
    refs.slider.value = String(index);
    refs.prev.disabled = index === 0;
    refs.next.disabled = index === steps.length - 1;
    refs.play.disabled = steps.length <= 1;
    refs.play.innerHTML = icon(playing ? 'pause' : 'play', 17);
    refs.play.setAttribute('aria-label', playing ? 'Pause trace' : 'Play trace');
    refs.slider.disabled = steps.length <= 1;

    renderCallstack(step);
    renderVars(step, preserveScroll);
    renderOutput(step);
    renderPreviews();

    if (step.line && lastHighlighted !== step.line) {
      lastHighlighted = step.line;
      options.onActiveLine?.({ line: step.line, endLine: step.endLine ?? step.line, source: 'trace' });
    }
    if (step.output) {
      refs.output.scrollTop = refs.output.scrollHeight;
    }
  }

  function renderVars(step) {
    const vars = step.vars ?? [];
    refs.varsCount.textContent = `${vars.length} value${vars.length === 1 ? '' : 's'}`;
    if (!vars.length) {
      refs.vars.innerHTML = `<div class="trace-vars-empty">
        <span class="empty-box-icon">${icon('code', 17)}</span>
        <p>No named values yet. The program has not stored anything at this point.</p>
      </div>`;
      return;
    }
    refs.vars.innerHTML = vars.map((variable) => `
      <div class="trace-var ${variable.changed && index > 0 ? 'is-changed' : ''}">
        <div class="trace-var-top">
          <span class="trace-var-name">${escapeHTML(variable.name)}</span>
          <span class="trace-var-type">${escapeHTML(typeLabel(variable.type))}</span>
        </div>
        <div class="trace-var-value">${escapeHTML(variable.display)}</div>
        ${variable.scope && variable.scope !== 'Global' ? `<span class="trace-var-scope">${escapeHTML(variable.scope)}</span>` : ''}
      </div>
    `).join('');
  }

  function renderCallstack(step) {
    const frames = step.callStack ?? [];
    refs.callstackCount.textContent = frames.length ? `${frames.length} frame${frames.length === 1 ? '' : 's'}` : 'Global';
    if (!frames.length) {
      refs.callstack.innerHTML = '<span class="callstack-global">Global scope</span>';
      return;
    }
    refs.callstack.innerHTML = `<span class="callstack-global">Global</span>${frames.map((frame) => `<span class="callstack-arrow">→</span><span class="callstack-frame">${escapeHTML(frame.name)}()</span>`).join('')}`;
  }

  function renderOutput(step) {
    const output = step.output ?? '';
    refs.output.textContent = output || 'No output yet.';
    refs.output.classList.toggle('is-empty', !output);
    if (step.kind === 'print' && output) {
      refs.output.classList.remove('is-printing');
      void refs.output.offsetWidth;
      refs.output.classList.add('is-printing');
    }
  }

  function renderPreviews() {
    const previous = steps[index - 1];
    const next = steps[index + 1];
    const prevTitle = previous ? previous.title : 'This is the beginning of the run';
    const nextTitle = next ? next.title : 'This is the final recorded step';
    refs.preview.innerHTML = `
      <button type="button" class="trace-preview" data-trace="prev" ${previous ? '' : 'disabled'}>
        <span class="trace-preview-label">← Before</span>
        <span class="trace-preview-title">${escapeHTML(prevTitle)}</span>
      </button>
      <button type="button" class="trace-preview" data-trace="next" ${next ? '' : 'disabled'}>
        <span class="trace-preview-label">Next →</span>
        <span class="trace-preview-title">${escapeHTML(nextTitle)}</span>
      </button>
    `;
  }

  function togglePlay() {
    if (steps.length <= 1) return;
    if (playing) {
      stopPlayback();
      return;
    }
    if (index >= steps.length - 1) renderStep(0);
    playing = true;
    updatePlayButton();
    scheduleNext();
  }

  function scheduleNext() {
    clearTimeout(timer);
    if (!playing) return;
    timer = setTimeout(() => {
      if (!playing) return;
      if (index >= steps.length - 1) {
        stopPlayback();
        return;
      }
      renderStep(index + 1);
      scheduleNext();
    }, Math.round(1250 / speed));
  }

  function stopPlayback() {
    playing = false;
    clearTimeout(timer);
    timer = null;
    updatePlayButton();
  }

  function updatePlayButton() {
    refs.play.innerHTML = icon(playing ? 'pause' : 'play', 17);
    refs.play.setAttribute('aria-label', playing ? 'Pause trace' : 'Play trace');
    refs.play.classList.toggle('is-playing', playing);
    refs.shell.classList.toggle('is-playing', playing);
  }

  function onClick(event) {
    const action = event.target.closest('[data-trace]')?.dataset.trace;
    if (!action) return;
    if (action === 'play') {
      togglePlay();
    } else if (action === 'prev') {
      stopPlayback();
      renderStep(index - 1);
    } else if (action === 'next') {
      stopPlayback();
      renderStep(index + 1);
    } else if (action === 'reset') {
      stopPlayback();
      renderStep(0);
    }
  }

  const onInput = (event) => {
    if (event.target.matches('[data-trace="slider"]')) {
      stopPlayback();
      renderStep(Number(event.target.value));
    }
  };
  const onChange = (event) => {
    if (event.target.matches('[data-trace="speed"]')) {
      speed = Number(event.target.value) || 1;
      if (playing) scheduleNext();
    }
  };
  const onKeyDown = (event) => {
    if (event.target.matches('input, select, textarea')) return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      stopPlayback();
      renderStep(index - 1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      stopPlayback();
      renderStep(index + 1);
    } else if (event.code === 'Space') {
      event.preventDefault();
      togglePlay();
    }
  };

  container.addEventListener('click', onClick);
  container.addEventListener('input', onInput);
  container.addEventListener('change', onChange);
  container.addEventListener('keydown', onKeyDown);

  renderStep(0);

  const footer = statusBarMarkup({
    legend: [
      { label: 'Assignment', className: 'swatch--action' },
      { label: 'Condition', className: 'swatch--decision' },
      { label: 'Function call', className: 'swatch--function' },
      { label: 'Output', className: 'swatch--output' }
    ],
    hint: 'Click a line in the guide to jump to its first execution step'
  });

  return {
    footer,
    stepCount: steps.length,
    complete: trace.complete,
    highlightLine(line) {
      const found = steps.findIndex((step) => line >= step.line && line <= (step.endLine ?? step.line));
      if (found === -1) return false;
      stopPlayback();
      renderStep(found);
      return true;
    },
    destroy() {
      stopPlayback();
      container.removeEventListener('click', onClick);
      container.removeEventListener('input', onInput);
      container.removeEventListener('change', onChange);
      container.removeEventListener('keydown', onKeyDown);
      container.innerHTML = '';
    }
  };
}

function renderCode(analysis, step) {
  const lines = analysis.highlightedLines ?? [];
  const start = Math.max(1, step.line ?? 1);
  const end = Math.min(analysis.lineCount, Math.max(start, step.endLine ?? start));
  const html = [];
  for (let line = start; line <= Math.min(end, start + 5); line += 1) {
    html.push(`<span class="trace-code-row"><span class="trace-code-number">${line}</span><span class="trace-code-content">${lines[line - 1] || ' '}</span></span>`);
  }
  if (end > start + 5) {
    html.push('<span class="trace-code-row trace-code-more">…</span>');
  }
  return html.join('');
}

function kindLabel(kind) {
  const labels = {
    start: 'START',
    end: 'END',
    assign: 'ASSIGNMENT',
    condition: 'DECISION',
    'loop-check': 'LOOP CHECK',
    iteration: 'ITERATION',
    call: 'FUNCTION CALL',
    'function-entry': 'FUNCTION ENTERS',
    return: 'RETURN',
    print: 'OUTPUT',
    break: 'BREAK',
    continue: 'CONTINUE',
    update: 'UPDATE',
    stopped: 'PAUSED'
  };
  return labels[kind] ?? 'STEP';
}

function kindIcon(kind) {
  const icons = {
    start: 'play',
    end: 'flag',

    assign: 'code',
    condition: 'flow',
    'loop-check': 'refresh',
    iteration: 'refresh',
    call: 'arrowRight',
    'function-entry': 'layers',
    return: 'arrowLeft',
    print: 'terminal',
    break: 'stepForward',
    continue: 'stepForward',
    update: 'refresh',
    stopped: 'warning'
  };
  return icons[kind] ?? 'code';
}

function typeLabel(type) {
  const labels = {
    number: 'number',
    string: 'text',
    boolean: 'boolean',
    array: 'array',
    object: 'object',
    null: 'null',
    undefined: 'empty',
    uninitialized: 'not set',
    unknown: 'unknown',
    function: 'function'
  };
  return labels[type] ?? type ?? 'value';
}
