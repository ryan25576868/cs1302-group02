/**
 * Renders the four guide tabs from the local or AI-enhanced guide object.
 * All prose goes through richText(), which escapes HTML before applying the
 * tiny inline Markdown subset.
 */

import { escapeHTML, richText } from '../utils.js';
import { icon } from '../icons.js';

export function renderGuideContent(container, guide, analysis, tab = 'overview') {
  if (!guide) {
    container.innerHTML = '<div class="view-empty"><h3>No guide yet</h3></div>';
    return;
  }
  switch (tab) {
    case 'walkthrough':
      container.innerHTML = renderWalkthrough(guide);
      break;
    case 'lines':
      container.innerHTML = renderLineNotes(guide, analysis);
      break;
    case 'concepts':
      container.innerHTML = renderConcepts(guide);
      break;
    case 'overview':
    default:
      container.innerHTML = renderOverview(guide);
      break;
  }
}

function renderOverview(guide) {
  const overview = guide.overview ?? {};
  const glance = overview.glance ?? [];
  const paragraphs = overview.paragraphs ?? [];
  const mental = overview.mentalModel ?? {};
  const notes = [];
  if (guide.traceNote && !guide.traceNote.complete) {
    notes.push(`<div class="trace-note-inline">${icon('info', 14)}<span>The local trace stopped early, so value-specific claims are limited. The structural explanation is still complete.</span></div>`);
  }
  return `
    <p class="guide-summary">${richText(guide.summary ?? '')}</p>
    <div class="guide-prose">${paragraphs.map((paragraph) => `<p>${richText(paragraph)}</p>`).join('')}</div>
    ${mental.title || mental.body ? `
      <section class="guide-section">
        <div class="guide-section-label">Mental model</div>
        <div class="mental-model">
          <h3>${icon('sparkles', 13)}${richText(mental.title ?? 'A way to think about it')}</h3>
          <p>${richText(mental.body ?? '')}</p>
        </div>
      </section>
    ` : ''}
    ${glance.length ? `
      <section class="guide-section">
        <div class="guide-section-label">At a glance</div>
        <div class="glance-grid">
          ${glance.map((item) => `
            <div class="glance-card">
              <span class="glance-label">${escapeHTML(item.label)}</span>
              <span class="glance-value ${item.mono ? 'is-mono' : ''}" title="${escapeHTML(item.value)}">${escapeHTML(item.value)}</span>
              ${item.hint ? `<span class="glance-hint">${escapeHTML(item.hint)}</span>` : ''}
            </div>
          `).join('')}
        </div>
      </section>
    ` : ''}
    <div class="guide-tip">${icon('book', 13)}<span>Read the Walkthrough for the program’s story, or the Line by line tab for a close reading of each meaningful statement.</span></div>
    ${notes.join('')}
  `;
}

function renderWalkthrough(guide) {
  const steps = guide.walkthrough ?? [];
  return `
    <div class="walkthrough-list">
      ${steps.map((step, index) => {
        const badgeClass = step.badge ? `walkthrough-badge--${badgeClassFor(step.badge)}` : '';
        const lines = (step.lines ?? []).filter((line) => Number.isInteger(line));
        return `
          <article class="walkthrough-step" data-walkthrough-step="${index}">
            <span class="walkthrough-index">${String(index + 1).padStart(2, '0')}</span>
            <div class="walkthrough-body">
              ${step.badge ? `<span class="walkthrough-badge ${badgeClass}">${escapeHTML(step.badge)}</span>` : ''}
              <h3 class="walkthrough-title">${richText(step.title)}</h3>
              <p class="walkthrough-copy">${richText(step.body)}</p>
              ${Array.isArray(step.points) && step.points.length ? `<ul class="walkthrough-points">${step.points.map((point) => `<li>${richText(point)}</li>`).join('')}</ul>` : ''}
              ${step.output ? `<pre class="walkthrough-output">${escapeHTML(step.output)}</pre>` : ''}
              ${lines.length ? `<div class="walkthrough-lines">${lines.map((line) => `<button type="button" class="line-ref" data-line="${line}" title="Highlight line ${line}">L${line}</button>`).join('')}</div>` : ''}
            </div>
          </article>
        `;
      }).join('')}
    </div>
    ${renderQuiz(guide.quiz)}
  `;
}

function renderLineNotes(guide, analysis) {
  const notes = guide.lineNotes ?? [];
  if (!notes.length) {
    return `<div class="view-empty"><h3>No line notes yet</h3><p>This snippet did not contain lines the guide could annotate.</p></div>`;
  }
  return `
    <div class="line-notes" role="list">
      ${notes.map((note) => {
        const code = note.code || analysis.lines?.[note.line - 1]?.text?.trim() || '';
        const tone = note.tone ?? 'structure';
        return `<button type="button" class="line-note line-note--${escapeHTML(tone)}" data-line="${note.line}" data-end-line="${note.endLine ?? note.line}" role="listitem" title="Highlight line ${note.line}">
          <span class="line-note-number">L${note.line}</span>
          <span class="line-note-body">
            <span class="line-note-tone">${escapeHTML(toneLabel(tone))}${note.author === 'ai' ? ' · AI' : ''}</span>
            ${code ? `<code class="line-note-snippet">${escapeHTML(code)}</code>` : ''}
            <span class="line-note-copy">${richText(note.note)}</span>
          </span>
        </button>`;
      }).join('')}
    </div>
  `;
}

function renderConcepts(guide) {
  const concepts = guide.concepts ?? [];
  const watchOuts = guide.watchOuts ?? [];
  return `
    ${concepts.length ? `
      <section>
        <div class="guide-section-label">Ideas in this program</div>
        <div class="concept-grid">
          ${concepts.map((concept) => `
            <article class="concept-card">
              <div class="concept-card-head">
                <h3 class="concept-term">${escapeHTML(concept.term)}</h3>
                ${concept.line ? `<button type="button" class="concept-link" data-line="${concept.line}">L${concept.line}</button>` : ''}
              </div>
              <p class="concept-definition">${richText(concept.definition)}</p>
              <p class="concept-here"><strong>In this code:</strong> ${richText(concept.inThisCode)}</p>
            </article>
          `).join('')}
        </div>
      </section>
    ` : ''}
    ${watchOuts.length ? `
      <section class="guide-section">
        <div class="guide-section-label">Things to watch</div>
        <div class="watchout-list">
          ${watchOuts.map((item) => `
            <div class="watchout">
              <span class="watchout-icon">${icon('warning', 13)}</span>
              <div>
                <strong>${richText(item.title)}</strong>
                <p>${richText(item.body)}</p>
              </div>
            </div>
          `).join('')}
        </div>
      </section>
    ` : ''}
    ${renderQuiz(guide.quiz)}
  `;
}

function renderQuiz(quiz) {
  if (!Array.isArray(quiz) || !quiz.length) return '';
  return `
    <section class="guide-section">
      <div class="guide-section-label">Check yourself</div>
      <div class="quiz-list">
        ${quiz.map((item) => `
          <details class="quiz-card">
            <summary>${richText(item.question)}</summary>
            <div class="quiz-answer">${richText(item.answer)}</div>
          </details>
        `).join('')}
      </div>
    </section>
  `;
}

export function setActiveGuideLine(container, line) {
  if (!container) return;
  container.querySelectorAll('.line-note').forEach((note) => {
    note.classList.toggle('is-active', Number(note.dataset.line) === Number(line));
  });
}

export function guideToMarkdown(guide, analysis, trace, modeName = 'Flowchart') {
  const lines = [];
  lines.push(`# ${guide.headline || 'Prism guide'}`);
  lines.push('');
  lines.push(`**Language:** ${analysis.language.name}  `);
  lines.push(`**View when exported:** ${modeName}  `);
  lines.push(`**Generated:** ${new Date().toLocaleString()}  `);
  if (guide.author === 'ai' && guide.aiMeta) {
    lines.push(`**Explanation:** AI-enhanced with ${guide.aiMeta.providerName} · ${guide.aiMeta.model}  `);
  } else {
    lines.push('**Explanation:** Local Prism guide');
  }
  lines.push('');
  lines.push('## Source');
  lines.push('');
  lines.push('```' + (analysis.language.extension || ''));
  lines.push(analysis.source);
  lines.push('```');
  lines.push('');
  lines.push('## Summary');
  lines.push('');
  lines.push(guide.summary ?? '');
  lines.push('');
  lines.push('## Overview');
  lines.push('');
  for (const paragraph of guide.overview?.paragraphs ?? []) {
    lines.push(paragraph);
    lines.push('');
  }
  if (guide.overview?.mentalModel?.title) {
    lines.push(`### Mental model: ${guide.overview.mentalModel.title}`);
    lines.push('');
    lines.push(guide.overview.mentalModel.body ?? '');
    lines.push('');
  }
  const glance = guide.overview?.glance ?? [];
  if (glance.length) {
    lines.push('### At a glance');
    lines.push('');
    for (const item of glance) {
      lines.push(`- **${item.label}:** ${item.value}`);
    }
    lines.push('');
  }
  lines.push('## Walkthrough');
  lines.push('');
  (guide.walkthrough ?? []).forEach((step, index) => {
    lines.push(`### ${index + 1}. ${step.title}`);
    lines.push('');
    lines.push(step.body ?? '');
    if (step.lines?.length) {
      lines.push('');
      lines.push(`*Lines: ${step.lines.map((line) => `L${line}`).join(', ')}*`);
    }
    if (step.points?.length) {
      lines.push('');
      for (const point of step.points) lines.push(`- ${point}`);
    }
    if (step.output) {
      lines.push('');
      lines.push('```text');
      lines.push(step.output.replace(/\n$/, ''));
      lines.push('```');
    }
    lines.push('');
  });
  lines.push('## Line by line');
  lines.push('');
  for (const note of guide.lineNotes ?? []) {
    lines.push(`**Line ${note.line}**${note.code ? ` — \`${note.code}\`` : ''}`);
    lines.push('');
    lines.push(note.note);
    lines.push('');
  }
  lines.push('## Concepts');
  lines.push('');
  for (const concept of guide.concepts ?? []) {
    lines.push(`### ${concept.term}`);
    lines.push('');
    lines.push(concept.definition);
    lines.push('');
    lines.push(`*In this code:* ${concept.inThisCode}`);
    if (concept.line) lines.push(`*Line: ${concept.line}*`);
    lines.push('');
  }
  if (guide.watchOuts?.length) {
    lines.push('## Things to watch');
    lines.push('');
    for (const item of guide.watchOuts) {
      lines.push(`- **${item.title}** — ${item.body}`);
    }
    lines.push('');
  }
  if (guide.quiz?.length) {
    lines.push('## Check yourself');
    lines.push('');
    for (const item of guide.quiz) {
      lines.push(`- **Q:** ${item.question}`);
      lines.push(`  **A:** ${item.answer}`);
    }
    lines.push('');
  }
  if (trace?.output) {
    lines.push('## Output from the sample run');
    lines.push('');
    lines.push('```text');
    lines.push(trace.output.replace(/\n$/, ''));
    lines.push('```');
    lines.push('');
  }
  if (trace && !trace.complete) {
    lines.push('> The local execution trace stopped early, so some runtime values are intentionally omitted.');
    lines.push('');
  }
  lines.push('---');
  lines.push('');
  lines.push('Made with Prism — understand the code, not just the output.');
  return lines.join('\n');
}

export function guideToExportData(guide, analysis, trace, options = {}) {
  return {
    app: 'prism',
    version: 1,
    generatedAt: new Date().toISOString(),
    language: {
      id: analysis.language.id,
      name: analysis.language.name,
      extension: analysis.language.extension
    },
    view: options.modeName ?? null,
    entry: analysis.entry
      ? {
          kind: analysis.entry.kind,
          name: analysis.entry.name,
          line: analysis.entry.node?.startLine ?? null,
          inferred: !!analysis.entry.inferred
        }
      : null,
    source: analysis.source,
    metrics: analysis.metrics,
    featureSummary: analysis.featureSummary,
    functions: analysis.functions.map((fn) => ({
      name: fn.name,
      line: fn.startLine,
      endLine: fn.endLine,
      params: fn.params,
      returnType: fn.returnType || ''
    })),
    assignments: analysis.assignments.map((assignment) => ({
      line: assignment.line,
      target: assignment.target,
      operator: assignment.operator,
      expression: assignment.expressionText,
      scope: assignment.scope,
      dependencies: assignment.dependencies
    })),
    trace: trace
      ? {
          complete: trace.complete,
          entryName: trace.entryName,
          output: trace.output,
          warnings: trace.warnings,
          stoppedReason: trace.stoppedReason,
          functionCalls: trace.functionCalls,
          iterations: trace.iterations,
          steps: trace.steps.map((step) => ({
            index: step.index,
            line: step.line,
            kind: step.kind,
            title: step.title,
            detail: step.detail,
            vars: step.vars,
            callStack: step.callStack,
            output: step.output
          })),
          events: trace.events
        }
      : null,
    guide,
    suggestedAIContext: {
      promptEndpoint: '/api/ai',
      provider: guide.aiMeta?.provider ?? null,
      model: guide.aiMeta?.model ?? null
    }
  };
}

function badgeClassFor(badge) {
  const normalized = String(badge).toLowerCase();
  if (normalized.includes('loop')) return 'loop';
  if (normalized.includes('decision') || normalized.includes('if')) return 'decision';
  if (normalized.includes('helper') || normalized.includes('function') || normalized.includes('call')) return 'helper';
  if (normalized.includes('output') || normalized.includes('print')) return 'output';
  if (normalized.includes('return')) return 'return';
  return 'setup';
}

function toneLabel(tone) {
  const labels = {
    function: 'function',
    decision: 'decision',
    loop: 'loop',
    output: 'output',
    return: 'return',
    assignment: 'value',
    call: 'call',
    structure: 'structure',
    ai: 'note'
  };
  return labels[tone] ?? tone;
}
