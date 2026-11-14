/**
 * A lightweight, dependency-free code editor with a real syntax-highlighting
 * layer. A transparent textarea handles input and selection while the coloured
 * <pre> underneath handles presentation; both scroll in lockstep.
 */

import { highlightHTML } from '../core/lexer.js';
import { normalizeCode } from '../utils.js';

export class CodeEditor {
  constructor(mount, options = {}) {
    this.mount = mount;
    this.language = options.language ?? null;
    this.onChange = options.onChange ?? (() => {});
    this.onRun = options.onRun ?? (() => {});
    this.value = normalizeCode(options.value ?? '');
    this.enabled = false;
    this.raf = null;
    this.render();
    this.bind();
    this.setEnabled(false);
  }

  render() {
    this.mount.innerHTML = `
      <div class="editor-shell" data-enabled="false">
        <div class="editor-gutter" aria-hidden="true">
          <div class="editor-gutter-inner"></div>
        </div>
        <div class="editor-main">
          <pre class="editor-highlight" aria-hidden="true"></pre>
          <textarea class="editor-input" spellcheck="false" autocorrect="off" autocapitalize="off"
            autocomplete="off" wrap="off" aria-label="Code editor"
            placeholder="Start typing, paste code, or import a file…"></textarea>
        </div>
        <div class="editor-empty" aria-hidden="true">
          <div class="editor-empty-art">
            <span></span><span></span><span></span>
          </div>
          <div class="editor-empty-copy">
            <p class="editor-empty-title">Start a file</p>
            <p>Paste code or import a source file.</p>
          </div>
          <div class="editor-empty-hint"><span>01</span> Choose a language</div>
        </div>
      </div>
    `;
    this.shell = this.mount.querySelector('.editor-shell');
    this.textarea = this.mount.querySelector('.editor-input');
    this.highlight = this.mount.querySelector('.editor-highlight');
    this.gutter = this.mount.querySelector('.editor-gutter-inner');
    this.textarea.value = this.value;
    this.refresh();
  }

  bind() {
    this.textarea.addEventListener('input', () => {
      if (!this.enabled) return;
      this.normalizeTextarea();
      this.value = this.textarea.value;
      this.scheduleRefresh();
      this.onChange(this.value);
    });
    this.textarea.addEventListener('scroll', () => this.syncScroll(), { passive: true });
    this.textarea.addEventListener('keydown', (event) => this.onKeyDown(event));
    this.textarea.addEventListener('click', () => this.markCursorLine());
    this.textarea.addEventListener('keyup', () => this.markCursorLine());
    this.textarea.addEventListener('select', () => this.markCursorLine());
    this.textarea.addEventListener('focus', () => this.shell.classList.add('is-focused'));
    this.textarea.addEventListener('blur', () => this.shell.classList.remove('is-focused'));
  }

  onKeyDown(event) {
    if (!this.enabled) return;

    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      this.onRun();
      return;
    }

    if (event.key === 'Tab') {
      event.preventDefault();
      if (event.shiftKey) {
        this.dedentSelection();
      } else {
        this.insertText('  ', '  ');
      }
      return;
    }

    if (event.key === 'Enter' && !event.metaKey && !event.ctrlKey && !event.altKey) {
      const start = this.textarea.selectionStart;
      const before = this.textarea.value.slice(0, start);
      const lineStart = before.lastIndexOf('\n') + 1;
      const currentLine = before.slice(lineStart);
      const indent = currentLine.match(/^[ \t]*/)?.[0] ?? '';
      const trimmed = currentLine.trimEnd();
      const addIndent = /[{\[(]$/.test(trimmed) || (trimmed.endsWith(':') && /^(?:if|elif|else|for|while|def|class|try|except|finally|with)\b/.test(trimmed.trim()));
      event.preventDefault();
      this.insertText(`\n${indent}${addIndent ? '  ' : ''}`);
      return;
    }

    // A simple, friendly dedent: typing a closing brace on an otherwise empty
    // indented line removes one level of indentation.
    if (event.key === '}' && !event.ctrlKey && !event.metaKey) {
      const start = this.textarea.selectionStart;
      const beforeLine = this.textarea.value.slice(0, start);
      const lineStart = beforeLine.lastIndexOf('\n') + 1;
      const currentIndent = beforeLine.slice(lineStart).match(/^[ \t]*/)?.[0] ?? '';
      if (currentIndent.length >= 2 && beforeLine.slice(lineStart).trim() === '') {
        event.preventDefault();
        this.insertText(`${currentIndent.slice(0, -2)}}`);
      }
    }
  }

  insertText(text, selectOffset = text.length) {
    if (!this.enabled) return;
    const start = this.textarea.selectionStart;
    const end = this.textarea.selectionEnd;
    this.textarea.setRangeText(text, start, end, 'end');
    if (selectOffset !== text.length) {
      this.textarea.selectionStart = start + selectOffset;
      this.textarea.selectionEnd = start + selectOffset;
    }
    this.normalizeTextarea();
    this.value = this.textarea.value;
    this.scheduleRefresh();
    this.onChange(this.value);
  }

  normalizeTextarea() {
    const raw = this.textarea.value;
    const normalized = normalizeCode(raw);
    if (raw === normalized) return;
    const start = this.textarea.selectionStart;
    const end = this.textarea.selectionEnd;
    const removedBeforeStart = (raw.slice(0, start).match(/\r/g) ?? []).length;
    const removedBeforeEnd = (raw.slice(0, end).match(/\r/g) ?? []).length;
    const scrollTop = this.textarea.scrollTop;
    const scrollLeft = this.textarea.scrollLeft;
    this.textarea.value = normalized;
    this.textarea.setSelectionRange(
      Math.max(0, start - removedBeforeStart),
      Math.max(0, end - removedBeforeEnd)
    );
    this.textarea.scrollTop = scrollTop;
    this.textarea.scrollLeft = scrollLeft;
  }

  dedentSelection() {
    if (!this.enabled) return;
    const start = this.textarea.selectionStart;
    const value = this.textarea.value;
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    const slice = value.slice(lineStart);
    if (!/^[ \t]{1,2}/.test(slice)) return;
    const remove = slice.startsWith('  ') ? 2 : 1;
    this.textarea.setRangeText('', lineStart, lineStart + remove, 'preserve');
    this.textarea.selectionStart = Math.max(lineStart, start - remove);
    this.textarea.selectionEnd = Math.max(lineStart, start - remove);
    this.normalizeTextarea();
    this.value = this.textarea.value;
    this.scheduleRefresh();
    this.onChange(this.value);
  }

  scheduleRefresh() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = requestAnimationFrame(() => {
      this.raf = null;
      this.refresh();
    });
  }

  refresh() {
    const value = normalizeCode(this.textarea.value);
    this.value = value;
    this.highlight.innerHTML = this.language
      ? highlightHTML(value, this.language)
      : '';
    const lineCount = Math.max(1, value.split('\n').length);
    this.buildLineNumbers(lineCount);
    this.markCursorLine();
    this.syncScroll();
    this.shell.classList.toggle('is-empty', !this.language);
    this.shell.classList.toggle('has-language', !!this.language);
    this.textarea.readOnly = !this.enabled;
  }

  buildLineNumbers(count) {
    const current = this.gutter.childElementCount;
    if (current === count) return;
    const fragment = document.createDocumentFragment();
    for (let i = 1; i <= count; i += 1) {
      const line = document.createElement('span');
      line.className = 'editor-line-number';
      line.textContent = String(i);
      fragment.append(line);
    }
    this.gutter.replaceChildren(fragment);
  }

  markCursorLine() {
    if (!this.textarea) return;
    const before = this.textarea.value.slice(0, this.textarea.selectionStart);
    const line = before.split('\n').length;
    const children = this.gutter.children;
    if (this.lastLine && children[this.lastLine - 1]) children[this.lastLine - 1].classList.remove('is-current');
    if (children[line - 1]) children[line - 1].classList.add('is-current');
    this.lastLine = line;
  }

  syncScroll() {
    if (!this.highlight) return;
    const x = this.textarea.scrollLeft;
    const y = this.textarea.scrollTop;
    this.highlight.style.transform = `translate(${-x}px, ${-y}px)`;
    this.gutter.style.transform = `translateY(${-y}px)`;
    this.shell.classList.toggle('is-scrolled', y > 2 || x > 2);
  }

  setValue(value, options = {}) {
    const normalized = normalizeCode(value);
    this.value = normalized;
    this.textarea.value = normalized;
    this.refresh();
    if (!options.silent) this.onChange(normalized);
  }

  getValue() {
    return normalizeCode(this.textarea.value);
  }

  setLanguage(language) {
    this.language = language;
    this.textarea.setAttribute('aria-label', `${language?.name ?? 'Code'} editor`);
    this.refresh();
  }

  setEnabled(enabled) {
    this.enabled = !!enabled;
    this.shell.dataset.enabled = String(this.enabled);
    // Keep the textarea focusable before a language is chosen so an early
    // paste can be captured instead of silently doing nothing.
    this.textarea.disabled = false;
    this.textarea.readOnly = !this.enabled;
    this.textarea.setAttribute('aria-disabled', String(!this.enabled));
    if (this.enabled) {
      this.refresh();
    }
  }

  setEmptyCopy(title, detail) {
    const titleNode = this.mount.querySelector('.editor-empty-title');
    const detailNode = titleNode?.nextElementSibling;
    if (titleNode) titleNode.textContent = title;
    if (detailNode) detailNode.textContent = detail;
  }

  focus() {
    this.textarea.focus();
  }

  setReadOnly(readOnly) {
    this.textarea.readOnly = !!readOnly;
  }

  destroy() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.mount.innerHTML = '';
  }
}

/**
 * Render the read-only source view used in the studio. Each line is a row so it
 * can be highlighted precisely and scrolled into view when a diagram node is
 * selected.
 */
export class SourceView {
  constructor(container, analysis) {
    this.container = container;
    this.analysis = analysis;
    this.activeLines = new Set();
    this.render();
    this.bind();
  }

  render() {
    const lines = this.analysis.highlightedLines ?? [];
    this.container.innerHTML = lines.map((html, index) => {
      const number = index + 1;
      return `<div class="code-line" data-line="${number}" tabindex="0" role="button" aria-label="Highlight line ${number}">
        <span class="code-lineno" aria-hidden="true">${number}</span>
        <span class="code-text">${html || ' '}</span>
      </div>`;
    }).join('');
    this.rows = [...this.container.querySelectorAll('.code-line')];
  }

  bind() {
    this.container.addEventListener('click', (event) => {
      const row = event.target.closest('.code-line');
      if (!row) return;
      const line = Number(row.dataset.line);
      this.onSelect?.(line, { source: 'code' });
      this.highlight([line], { scroll: false });
    });
    this.container.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const row = event.target.closest('.code-line');
      if (!row) return;
      event.preventDefault();
      const line = Number(row.dataset.line);
      this.onSelect?.(line, { source: 'code' });
      this.highlight([line], { scroll: false });
    });
  }

  setOnSelect(callback) {
    this.onSelect = callback;
  }

  highlight(lines, options = {}) {
    const set = new Set((lines ?? []).filter((line) => Number.isFinite(line)));
    for (const row of this.rows ?? []) {
      const line = Number(row.dataset.line);
      const active = set.has(line);
      row.classList.toggle('is-active', active);
      row.classList.toggle('is-primary', active && (options.primary ?? lines?.[0]) === line);
    }
    this.activeLines = set;
    if (options.scroll !== false && set.size) {
      const first = Math.min(...set);
      const row = this.rows?.[first - 1];
      const scroller = this.container.parentElement;
      if (row && scroller) {
        // Scroll only the source pane. Calling scrollIntoView here would also
        // scroll the page on narrow screens, yanking the user out of the diagram.
        const rowRect = row.getBoundingClientRect();
        const scrollerRect = scroller.getBoundingClientRect();
        const offset = rowRect.top - scrollerRect.top + scroller.scrollTop;
        const target = offset - scroller.clientHeight / 2 + rowRect.height / 2;
        scroller.scrollTo({
          top: Math.max(0, target),
          behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
        });
      }
    }
  }

  clear() {
    this.highlight([]);
  }
}
