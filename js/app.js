/**
 * Prism application controller.
 *
 * The app is deliberately a single static page. All parsing, tracing, diagram
 * layout, and local guide writing happen in this browser tab. The only network
 * call is the optional AI request, and that is explicitly initiated by the user.
 */

import {
  LANGUAGES,
  LANGUAGE_BY_ID,
  MODES,
  MODE_BY_ID
} from './data/languages.js';
import { analyzeSource, getFlowFoci } from './core/analyzer.js';
import { simulate } from './core/interpreter.js';
import { buildGuide } from './core/explainer.js';
import { CodeEditor, SourceView } from './ui/editor.js';
import { buildPortablePrompt, checkProxy, enhanceGuide, getProvider, isAIConfigured, normaliseAISettings } from './ai.js';
import { openAISettingsModal } from './ui/ai-modal.js';
import {
  renderGuideContent,
  setActiveGuideLine,
  guideToMarkdown,
  guideToExportData
} from './ui/guide-view.js';
import { renderFlowchart } from './views/flowchart.js';
import { renderSyntaxTree } from './views/tree.js';
import { renderTrace } from './views/trace.js';
import { renderDataFlow } from './views/dataflow.js';
import { brandMark, icon, spinner } from './icons.js';
import {
  announce,
  clamp,
  copyText,
  debounce,
  downloadFile,
  escapeHTML,
  fileStem,
  safeJSONParse
} from './utils.js';

const STORAGE_KEY = 'prism:workspace:v1';
const SECRET_KEY = 'prism:ai-key:v1';
const MAX_SOURCE_CHARS = 60_000;
const VIEW_COPY = {
  flow: {
    title: 'Flowchart',
    subtitle: 'See every decision, loop, and exit in one continuous route.'
  },
  tree: {
    title: 'Syntax Tree',
    subtitle: 'Open up the code and see how statements and expressions nest.'
  },
  trace: {
    title: 'Live Trace',
    subtitle: 'Walk through a safe simulated run, one small step at a time.'
  },
  data: {
    title: 'Data Flow',
    subtitle: 'Follow values from the line that creates them to the line that uses them.'
  }
};
const MODE_ICONS = { flow: 'flow', tree: 'tree', trace: 'trace', data: 'data' };

const refs = {};
const state = {
  theme: 'light',
  languageId: null,
  modeId: null,
  drafts: {},
  editor: null,
  analysis: null,
  trace: null,
  localGuide: null,
  guide: null,
  activeMode: 'flow',
  activeGuideTab: 'overview',
  focusId: null,
  selectedLine: null,
  inStudio: false,
  analyzing: false,
  aiSettings: normaliseAISettings({}),
  aiLoading: false,
  aiError: null,
  aiRequestId: 0,
  proxyAvailable: false,
  sourceView: null,
  activeView: null,
  exportOpen: false
};

const persistDebounced = debounce(() => persist(), 220);
let themeTransitionTimer = null;

init();

function init() {
  cacheRefs();
  hydrateStaticIcons();
  hydrateBrand();
  const saved = readSavedWorkspace();
  state.theme = saved.theme;
  state.drafts = saved.drafts;
  state.aiSettings = normaliseAISettings({
    ...saved.aiSettings,
    apiKey: saved.apiKey ?? ''
  });
  applyTheme(state.theme);
  renderLanguageGrid();
  renderModeGrid();
  createEditor();
  wireInterfaceEvents();
  restoreSelection(saved);
  updateEditorMeta();
  updateSelectionUI();
  updateAnalyzeButton();
  updateAIChrome();
  checkProxyState();
  if (new URLSearchParams(location.search).get('demo') === '1') {
    window.setTimeout(() => runDemo(), 120);
  }
}

function cacheRefs() {
  const ids = [
    'intakeView', 'studioView', 'languageGrid', 'modeGrid', 'modeStep', 'modeHint',
    'editorMount', 'editorLanguageChip', 'editorLanguageGlyph', 'editorFileName',
    'editorFileLabel', 'editorLines', 'loadSampleButton', 'analyzeButton', 'codeCard',
    'demoLink', 'aiButton', 'aiStatusDot', 'themeToggle', 'brandLink', 'brandSymbol',
    'backButton', 'editCodeButton', 'sourceEditButton', 'copyGuideButton', 'exportButton',
    'exportMenu', 'studioKicker', 'studioTitle', 'studioRunChip', 'sourceFile', 'sourceLanguage',
    'sourceCount', 'sourceCode', 'sourceScroller', 'vizTabs', 'vizKicker', 'vizTitle',
    'vizContext', 'vizSubtitle', 'vizControls', 'vizStage', 'vizFooter', 'guideBadge',
    'guideReadingTime', 'guideHeadSub', 'aiStrip', 'guideTabs', 'guideScroller', 'guideContent'
  ];
  for (const id of ids) refs[id] = document.getElementById(id);
  refs.modalRoot = document.getElementById('modalRoot');
  refs.toastRoot = document.getElementById('toastRoot');
  refs.studioView?.setAttribute('aria-hidden', 'true');
}

function hydrateStaticIcons() {
  document.querySelectorAll('[data-icon]').forEach((node) => {
    if (node.dataset.iconReady === 'true') return;
    const name = node.dataset.icon;
    const size = Number(node.dataset.iconSize) || 18;
    node.innerHTML = icon(name, size);
    node.dataset.iconReady = 'true';
  });
}

function hydrateBrand() {
  if (refs.brandSymbol) refs.brandSymbol.innerHTML = brandMark(29);
}

/* -------------------------------------------------------------------------- */
/* Persistence and theme                                                     */
/* -------------------------------------------------------------------------- */

function readSavedWorkspace() {
  let saved = {};
  try {
    saved = safeJSONParse(localStorage.getItem(STORAGE_KEY), {}) ?? {};
  } catch {
    saved = {};
  }
  const drafts = {};
  if (saved.drafts && typeof saved.drafts === 'object') {
    for (const language of LANGUAGES) {
      if (typeof saved.drafts[language.id] === 'string') {
        drafts[language.id] = saved.drafts[language.id];
      }
    }
  }
  let apiKey = '';
  let storedSettings = saved.aiSettings && typeof saved.aiSettings === 'object' ? saved.aiSettings : {};
  if (storedSettings.rememberKey) {
    try {
      apiKey = localStorage.getItem(SECRET_KEY) ?? '';
    } catch {
      apiKey = '';
    }
  }
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  const theme = saved.theme === 'dark' || saved.theme === 'light'
    ? saved.theme
    : prefersDark ? 'dark' : 'light';
  return {
    theme,
    drafts,
    lastLanguageId: LANGUAGE_BY_ID[saved.lastLanguageId] ? saved.lastLanguageId : null,
    lastModeId: MODE_BY_ID[saved.lastModeId] ? saved.lastModeId : null,
    aiSettings: storedSettings,
    apiKey
  };
}

function persist() {
  const safeSettings = {
    provider: state.aiSettings.provider,
    baseUrl: state.aiSettings.baseUrl,
    model: state.aiSettings.model,
    rememberKey: !!state.aiSettings.rememberKey,
    explainLevel: state.aiSettings.explainLevel,
    extraInstructions: state.aiSettings.extraInstructions,
    temperature: state.aiSettings.temperature
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      version: 1,
      theme: state.theme,
      drafts: state.drafts,
      lastLanguageId: state.languageId,
      lastModeId: state.modeId,
      aiSettings: safeSettings
    }));
    if (safeSettings.rememberKey && state.aiSettings.apiKey) {
      localStorage.setItem(SECRET_KEY, state.aiSettings.apiKey);
    } else {
      localStorage.removeItem(SECRET_KEY);
    }
  } catch {
    // Storage may be unavailable in private mode. The app still works in memory.
  }
}

function applyTheme(theme) {
  state.theme = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = state.theme;
  document.documentElement.style.colorScheme = state.theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', state.theme === 'dark' ? '#101113' : '#f4f1ea');
  if (refs.themeToggle) {
    refs.themeToggle.innerHTML = icon(state.theme === 'dark' ? 'sun' : 'moon', 18);
    refs.themeToggle.setAttribute('aria-label', state.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    refs.themeToggle.setAttribute('title', state.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  }
}

function toggleTheme() {
  const root = document.documentElement;
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!reduceMotion) {
    root.classList.add('is-theme-transitioning');
    clearTimeout(themeTransitionTimer);
    themeTransitionTimer = window.setTimeout(() => {
      root.classList.remove('is-theme-transitioning');
    }, 520);
  }
  applyTheme(state.theme === 'dark' ? 'light' : 'dark');
  persist();
}

function replayClass(element, className) {
  if (!element) return;
  element.classList.remove(className);
  // Force a style flush so the same animation can run again.
  void element.offsetWidth;
  element.classList.add(className);
}

/* -------------------------------------------------------------------------- */
/* Intake                                                                     */
/* -------------------------------------------------------------------------- */

function renderLanguageGrid() {
  refs.languageGrid.innerHTML = LANGUAGES.map((language) => `
    <button type="button" class="language-card" data-language="${language.id}" role="radio" aria-checked="false"
      style="--lang-tint:${language.tint}; --lang-ink:${language.tintInk};">
      <span class="language-glyph" aria-hidden="true">${escapeHTML(language.monogram)}</span>
      <span class="language-copy">
        <span class="language-name">${escapeHTML(language.name)}</span>
        <span class="language-tagline">${escapeHTML(language.tagline)}</span>
      </span>
      <span class="language-check" aria-hidden="true">${icon('check', 10)}</span>
    </button>
  `).join('');
}

function renderModeGrid() {
  refs.modeGrid.innerHTML = MODES.map((mode) => `
    <button type="button" class="lens-card" data-mode="${mode.id}" role="radio" aria-checked="false"
      style="--lens-accent:${mode.accent}; --lens-soft:${mode.accentSoft}; --lens-ink:${mode.accentInk};">
      <span class="lens-icon" aria-hidden="true">${icon(MODE_ICONS[mode.id], 16)}</span>
      <span class="lens-name-row">
        <span class="lens-name">${escapeHTML(mode.name)}</span>
        <span class="lens-tag">${escapeHTML(mode.micro)}</span>
      </span>
      <span class="lens-desc">${escapeHTML(mode.description)}</span>
    </button>
  `).join('');
}

function createEditor() {
  state.editor = new CodeEditor(refs.editorMount, {
    onChange: handleEditorChange,
    onRun: () => {
      if (!refs.analyzeButton.disabled) startAnalysis();
    }
  });
}

function restoreSelection(saved) {
  if (saved.lastLanguageId) {
    selectLanguage(saved.lastLanguageId, { silent: true, restored: true, skipPersist: true });
    if (saved.lastModeId) selectMode(saved.lastModeId, { silent: true, restored: true, skipPersist: true });
  }
}

function selectLanguage(languageId, options = {}) {
  const language = LANGUAGE_BY_ID[languageId];
  if (!language) return;
  if (!options.force && state.languageId === languageId && state.editor?.language?.id === languageId) {
    updateSelectionUI();
    return;
  }
  if (state.languageId && state.languageId !== languageId && state.editor) {
    state.drafts[state.languageId] = state.editor.getValue();
  }

  state.languageId = languageId;
  const fallback = language.sample;
  if (options.force || typeof state.drafts[languageId] !== 'string') {
    state.drafts[languageId] = fallback;
  }
  const code = state.drafts[languageId] ?? fallback;
  state.editor.setLanguage(language);
  state.editor.setEnabled(true);
  state.editor.setValue(code, { silent: true });
  state.drafts[languageId] = state.editor.getValue();

  refs.modeHint.innerHTML = `<span data-icon="check" data-icon-size="13" aria-hidden="true"></span>Lenses unlocked. Pick a view to continue.`;
  hydrateWithin(refs.modeHint);
  updateEditorMeta();
  updateSelectionUI();
  updateAnalyzeButton();
  if (!options.skipPersist) persistDebounced();
  if (!options.silent && !options.restored) {
    refs.modeStep.animate?.(
      [
        { boxShadow: '0 0 0 0 rgba(228,90,52,0)' },
        { boxShadow: '0 0 0 3px rgba(228,90,52,.12)' },
        { boxShadow: '0 0 0 0 rgba(228,90,52,0)' }
      ],
      { duration: 600, easing: 'ease-out' }
    );
  }
}

function selectMode(modeId, options = {}) {
  if (!state.languageId) {
    announce('Choose a language first.');
    return;
  }
  if (!MODE_BY_ID[modeId]) return;
  state.modeId = modeId;
  updateSelectionUI();
  updateAnalyzeButton();
  if (!options.skipPersist) persistDebounced();
}

function updateSelectionUI() {
  refs.languageGrid.querySelectorAll('[data-language]').forEach((button) => {
    const selected = button.dataset.language === state.languageId;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-checked', String(selected));
  });
  const modeButtons = refs.modeGrid.querySelectorAll('[data-mode]');
  modeButtons.forEach((button) => {
    const selected = button.dataset.mode === state.modeId;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-checked', String(selected));
    button.disabled = !state.languageId;
  });
  const locked = !state.languageId;
  const wasLocked = refs.modeStep.classList.contains('is-locked');
  refs.modeStep.classList.toggle('is-locked', locked);
  if (wasLocked && !locked) {
    replayClass(refs.modeStep, 'is-unlocked');
    window.setTimeout(() => refs.modeStep.classList.remove('is-unlocked'), 900);
  }
  if (locked) {
    refs.modeHint.innerHTML = `<span data-icon="lock" data-icon-size="13" aria-hidden="true"></span>Pick a language to unlock the lenses.`;
    hydrateWithin(refs.modeHint);
  } else if (!state.modeId) {
    refs.modeHint.innerHTML = `<span data-icon="sparkles" data-icon-size="13" aria-hidden="true"></span>Choose any lens. You can switch later without re-running the analysis.`;
    hydrateWithin(refs.modeHint);
    refs.modeHint.style.display = 'flex';
  } else {
    refs.modeHint.style.display = 'none';
  }
}

function hydrateWithin(root) {
  root.querySelectorAll('[data-icon]').forEach((node) => {
    if (node.dataset.iconReady === 'true') return;
    node.innerHTML = icon(node.dataset.icon, Number(node.dataset.iconSize) || 18);
    node.dataset.iconReady = 'true';
  });
}

function updateEditorMeta() {
  const language = state.languageId ? LANGUAGE_BY_ID[state.languageId] : null;
  if (!language) {
    refs.editorLanguageChip.hidden = true;
    refs.editorFileLabel.textContent = 'No file selected';
    refs.editorLines.textContent = '0 lines';
    refs.loadSampleButton.disabled = true;
    return;
  }
  const fileName = sourceFileName(language);
  refs.editorLanguageChip.hidden = false;
  refs.editorLanguageChip.style.setProperty('--lang-tint', language.tint);
  refs.editorLanguageChip.style.setProperty('--lang-ink', language.tintInk);
  refs.editorLanguageGlyph.textContent = language.monogram;
  refs.editorFileName.textContent = fileName;
  refs.editorFileLabel.textContent = fileName;
  refs.editorLines.textContent = countLines(state.editor?.getValue() ?? '');
  refs.loadSampleButton.disabled = false;
}

function handleEditorChange(value) {
  if (!state.languageId) return;
  state.drafts[state.languageId] = value;
  updateEditorMeta();
  updateAnalyzeButton();
  persistDebounced();
}

function updateAnalyzeButton() {
  const language = state.languageId ? LANGUAGE_BY_ID[state.languageId] : null;
  const code = state.editor?.getValue?.() ?? '';
  const mode = state.modeId ? MODE_BY_ID[state.modeId] : null;
  let label = 'Visualize & explain';
  let disabled = false;

  if (state.analyzing) {
    label = 'Building your guide…';
    disabled = true;
  } else if (!language) {
    label = 'Choose a language';
    disabled = true;
  } else if (!mode) {
    label = 'Choose a lens';
    disabled = true;
  } else if (!code.trim()) {
    label = 'Add some code';
    disabled = true;
  }

  refs.analyzeButton.disabled = disabled;
  refs.analyzeButton.classList.toggle('is-loading', state.analyzing);
  refs.analyzeButton.innerHTML = state.analyzing
    ? `${spinner(16)}<span class="button-label">${escapeHTML(label)}</span>`
    : `<span class="button-label">${escapeHTML(label)}</span><span class="button-arrow">${icon('arrowRight', 18)}</span>`;
}

function handleLoadStarter() {
  const language = LANGUAGE_BY_ID[state.languageId];
  if (!language) return;
  if (state.editor.getValue().trim() === language.sample.trim()) {
    announce('You are already using the starter.');
    return;
  }
  openConfirm({
    title: 'Restore the starter?',
    message: 'This replaces the code currently in the editor with the original example. You can still paste your own code afterwards.',
    confirmLabel: 'Load starter',
    onConfirm: () => {
      state.editor.setValue(language.sample);
      state.drafts[language.id] = language.sample;
      updateEditorMeta();
      updateAnalyzeButton();
      persistDebounced();
      state.editor.focus();
      announce('Starter code loaded.');
    }
  });
}

function runDemo() {
  if (state.inStudio) showIntake();
  const javascript = LANGUAGE_BY_ID.javascript;
  state.drafts.javascript = javascript.sample;
  selectLanguage('javascript', { silent: true, restored: true, force: true, skipPersist: true });
  selectMode('flow', { silent: true, restored: true, skipPersist: true });
  startAnalysis();
}

async function startAnalysis() {
  if (state.analyzing) return;
  const language = LANGUAGE_BY_ID[state.languageId];
  const mode = state.modeId;
  if (!language || !mode) return;
  const code = state.editor.getValue();
  if (!code.trim()) {
    announce('Add some code first.');
    return;
  }
  if (code.length > MAX_SOURCE_CHARS) {
    announce(`Please keep a snippet under ${MAX_SOURCE_CHARS.toLocaleString()} characters so the local analysis stays responsive.`);
    return;
  }

  state.analyzing = true;
  updateAnalyzeButton();
  await nextFrame();
  try {
    const analysis = analyzeSource(code, language);
    const trace = simulate(analysis);
    let guide = buildGuide(analysis, trace);
    guide.sourceLineCount = analysis.lineCount;
    state.analysis = analysis;
    state.trace = trace;
    state.localGuide = guide;
    state.guide = guide;
    state.aiError = null;
    state.aiLoading = false;
    state.activeMode = mode;
    state.activeGuideTab = 'overview';
    state.selectedLine = null;
    state.drafts[language.id] = code;

    const foci = getFlowFoci(analysis);
    const entryFocus = analysis.entry?.kind === 'function'
      ? foci.find((focus) => focus.id === `function:${analysis.entry.node.id}`)
      : foci.find((focus) => focus.id === 'program');
    state.focusId = entryFocus?.id ?? foci[0]?.id ?? null;

    persist();
    showStudio();
    announce('Analysis ready. Four views and a full beginner’s guide were created locally.');
    if (trace.warnings.length) {
      window.setTimeout(() => announce('The trace stopped early; the structure and guide are still available.'), 1200);
    }
  } catch (error) {
    console.error('[prism] analysis failed', error);
    if (state.inStudio) showIntake();
    announce(`Analysis could not finish: ${error?.message || 'unknown error'}`);
  } finally {
    state.analyzing = false;
    updateAnalyzeButton();
  }
}

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function showStudio() {
  if (!state.analysis) return;
  state.inStudio = true;
  document.body.classList.add('is-studio');
  refs.intakeView.hidden = true;
  refs.studioView.hidden = false;
  refs.studioView.setAttribute('aria-hidden', 'false');
  window.scrollTo({ top: 0, behavior: 'auto' });
  renderStudio();
  document.title = `Prism · ${state.analysis.language.name} · ${MODE_BY_ID[state.activeMode].name}`;
  window.setTimeout(() => refs.studioView.classList.add('is-ready'), 20);
}

function showIntake(options = {}) {
  state.aiRequestId += 1;
  state.aiLoading = false;
  state.inStudio = false;
  cleanupStudioViews();
  document.body.classList.remove('is-studio');
  refs.studioView.hidden = true;
  refs.studioView.setAttribute('aria-hidden', 'true');
  refs.studioView.classList.remove('is-ready');
  refs.intakeView.hidden = false;
  replayClass(refs.intakeView, 'is-entering');
  document.title = 'Prism — see your code from every angle';
  window.scrollTo({ top: 0, behavior: 'auto' });
  if (options.focusEditor) {
    window.setTimeout(() => state.editor?.focus(), 80);
  }
}

function cleanupStudioViews() {
  try { state.activeView?.destroy?.(); } catch { /* free the view even if it is already gone */ }
  state.activeView = null;
  state.sourceView = null;
  refs.vizStage.innerHTML = '';
  refs.vizFooter.innerHTML = '';
  refs.vizControls.innerHTML = '';
  refs.sourceCode.innerHTML = '';
  refs.guideContent.innerHTML = '';
  refs.aiStrip.innerHTML = '';
}

/* -------------------------------------------------------------------------- */
/* Studio rendering                                                          */
/* -------------------------------------------------------------------------- */

function renderStudio() {
  const analysis = state.analysis;
  if (!analysis) return;
  const language = analysis.language;
  const mode = MODE_BY_ID[state.activeMode] ?? MODES[0];
  refs.studioKicker.textContent = `${language.name.toUpperCase()} · ${mode.name.toUpperCase()}`;
  refs.studioTitle.textContent = 'Your code, unpacked.';
  updateStudioRunChip();
  renderSourcePanel();
  renderModeTabs();
  renderAIStrip();
  renderGuide({ resetScroll: true });
  updateAIChrome();
  renderActiveView();
  if (state.selectedLine) {
    highlightSource(state.selectedLine, state.selectedLine, { scroll: false });
    setActiveGuideLine(refs.guideContent, state.selectedLine);
  }
}

function updateStudioRunChip() {
  if (!refs.studioRunChip) return;
  if (state.trace?.complete) {
    refs.studioRunChip.innerHTML = '<span class="pulse-dot" aria-hidden="true"></span>Local analysis';
    refs.studioRunChip.title = 'All analysis happens in this browser tab.';
  } else {
    refs.studioRunChip.innerHTML = '<span class="pulse-dot" aria-hidden="true" style="background:var(--amber)"></span>Partial trace';
    refs.studioRunChip.title = 'The safe tracer stopped before the end of this program.';
  }
}

function renderSourcePanel() {
  const analysis = state.analysis;
  const language = analysis.language;
  const file = sourceFileName(language);
  refs.sourceFile.textContent = file;
  refs.sourceLanguage.textContent = language.name;
  refs.sourceCount.textContent = `${analysis.metrics.codeLines} code lines · ${analysis.functions.length} function${analysis.functions.length === 1 ? '' : 's'}`;
  refs.sourceCode.innerHTML = '';
  state.sourceView = new SourceView(refs.sourceCode, analysis);
  state.sourceView.setOnSelect((line) => {
    state.selectedLine = line;
    state.activeView?.highlightLine?.(line);
    highlightSource(line, line, { scroll: false });
    setActiveGuideLine(refs.guideContent, line);
  });
  refs.sourceScroller.scrollTop = 0;
  refs.sourceScroller.scrollLeft = 0;
}

function renderModeTabs() {
  refs.vizTabs.querySelectorAll('[data-mode]').forEach((tab) => {
    const active = tab.dataset.mode === state.activeMode;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', String(active));
  });
}

function setActiveMode(modeId) {
  if (!MODE_BY_ID[modeId] || modeId === state.activeMode) return;
  state.activeMode = modeId;
  state.modeId = modeId;
  refs.studioKicker.textContent = `${state.analysis.language.name.toUpperCase()} · ${MODE_BY_ID[modeId].name.toUpperCase()}`;
  renderModeTabs();
  renderActiveView();
  updateSelectionUI();
  persist();
  document.title = `Prism · ${state.analysis.language.name} · ${MODE_BY_ID[modeId].name}`;
}

function renderActiveView() {
  try {
    renderActiveViewContents();
    replayClass(refs.vizStage, 'is-entering');
  } catch (error) {
    console.error('[prism] view render failed', error);
    try { state.activeView?.destroy?.(); } catch { /* ignore */ }
    state.activeView = null;
    refs.vizStage.innerHTML = `<div class="view-empty">
      <div class="view-empty-icon">${icon('warning', 26)}</div>
      <h3>This view could not be drawn</h3>
      <p>The other lenses and the guide are still available. ${escapeHTML(error?.message || '')}</p>
    </div>`;
    refs.vizFooter.innerHTML = '';
    refs.vizControls.innerHTML = '';
    setVizContext('View unavailable');
  }
}

function renderActiveViewContents() {
  const analysis = state.analysis;
  if (!analysis) return;
  try { state.activeView?.destroy?.(); } catch { /* view cleanup is best-effort */ }
  state.activeView = null;
  refs.vizStage.innerHTML = '';
  refs.vizFooter.innerHTML = '';
  refs.vizControls.innerHTML = '';

  const modeId = state.activeMode;
  const mode = MODE_BY_ID[modeId];
  const viewCopy = VIEW_COPY[modeId];
  refs.vizKicker.textContent = mode.kicker.toUpperCase();
  refs.vizTitle.textContent = viewCopy.title;
  refs.vizSubtitle.textContent = viewCopy.subtitle;
  refs.vizContext.hidden = true;
  refs.vizContext.textContent = '';

  if (modeId === 'flow') {
    renderFlowView();
    return;
  }
  if (modeId === 'tree') {
    const view = renderSyntaxTree(refs.vizStage, analysis, {
      onSelectLine: handleViewSelection
    });
    state.activeView = view;
    refs.vizFooter.innerHTML = view.footer ?? '';
    const count = view.getRenderedNodeCount?.();
    setVizContext(count ? `${count} visible nodes` : 'Syntax structure');
    finishViewRender();
    return;
  }
  if (modeId === 'trace') {
    const view = renderTrace(refs.vizStage, analysis, state.trace, {
      onActiveLine: handleTraceActiveLine
    });
    state.activeView = view;
    refs.vizFooter.innerHTML = view.footer ?? '';
    setVizContext(state.trace?.steps?.length ? `${state.trace.steps.length} recorded steps` : 'No trace');
    finishViewRender();
    return;
  }
  if (modeId === 'data') {
    const view = renderDataFlow(refs.vizStage, analysis, state.trace, {
      onSelectLine: handleViewSelection
    });
    state.activeView = view;
    refs.vizFooter.innerHTML = view.footer ?? '';
    setVizContext(view.groupCount ? `${view.groupCount} value card${view.groupCount === 1 ? '' : 's'}` : 'Value map');
    finishViewRender();
  }
}

function finishViewRender() {
  if (state.selectedLine) {
    state.activeView?.highlightLine?.(state.selectedLine);
  }
}

function renderFlowView() {
  const foci = getFlowFoci(state.analysis);
  let focus = foci.find((item) => item.id === state.focusId);
  if (!focus) {
    const entry = state.analysis.entry;
    focus = entry?.kind === 'function'
      ? foci.find((item) => item.id === `function:${entry.node.id}`)
      : foci.find((item) => item.id === 'program');
    focus = focus ?? foci[0];
    state.focusId = focus?.id ?? null;
  }
  if (!focus) {
    refs.vizStage.innerHTML = '<div class="view-empty"><h3>No flow to draw</h3></div>';
    return;
  }

  refs.vizControls.innerHTML = foci.length > 1
    ? `<label class="sr-only" for="focusSelect">Flowchart focus</label>
       <select class="focus-select" id="focusSelect" aria-label="Flowchart focus">
         ${foci.map((item) => `<option value="${escapeHTML(item.id)}" ${item.id === focus.id ? 'selected' : ''}>${escapeHTML(item.label)}</option>`).join('')}
       </select>`
    : '';
  const select = refs.vizControls.querySelector('#focusSelect');
  if (select) {
    select.addEventListener('change', () => {
      state.focusId = select.value;
      renderActiveView();
    });
  }

  const view = renderFlowchart(refs.vizStage, state.analysis, {
    focus: {
      kind: focus.kind,
      node: focus.node,
      name: focus.kind === 'function' ? focus.node.name : 'Program',
      isEntry: focus.kind === 'function' && state.analysis.entry?.kind === 'function' && state.analysis.entry.node === focus.node
    },
    onSelectLine: handleViewSelection
  });
  state.activeView = view;
  refs.vizFooter.innerHTML = view.footer ?? '';
  setVizContext(focus.kind === 'program' ? 'Whole program' : `${focus.node.name}()`);
  finishViewRender();
}

function setVizContext(text) {
  refs.vizContext.textContent = text;
  refs.vizContext.hidden = !text;
}

function handleViewSelection({ line, endLine }) {
  if (!Number.isFinite(line)) return;
  state.selectedLine = line;
  highlightSource(line, endLine ?? line, { scroll: true });
  setActiveGuideLine(refs.guideContent, line);
}

function handleTraceActiveLine({ line, endLine }) {
  if (!Number.isFinite(line)) return;
  state.selectedLine = line;
  highlightSource(line, endLine ?? line, { scroll: true });
  setActiveGuideLine(refs.guideContent, line);
}

function highlightSource(line, endLine = line, { scroll = true } = {}) {
  if (!state.sourceView) return;
  const start = clamp(Number(line) || 1, 1, state.analysis.lineCount);
  const end = clamp(Number(endLine) || start, start, Math.min(state.analysis.lineCount, start + 80));
  const lines = [];
  for (let current = start; current <= end; current += 1) lines.push(current);
  state.sourceView.highlight(lines, { scroll, primary: start });
}

/* -------------------------------------------------------------------------- */
/* Guide                                                                      */
/* -------------------------------------------------------------------------- */

function renderGuide({ resetScroll = false } = {}) {
  if (!state.guide || !state.analysis) return;
  const guide = state.guide;
  const isAI = guide.author === 'ai';
  refs.guideBadge.innerHTML = `<span class="badge-dot"></span>${isAI ? 'AI-enhanced' : 'Local guide'}`;
  refs.guideBadge.classList.toggle('is-ai', isAI);
  refs.guideReadingTime.textContent = `≈ ${guide.readingMinutes ?? 1} min read`;
  refs.guideHeadSub.textContent = isAI && guide.aiMeta
    ? `Enhanced by ${guide.aiMeta.providerName} · checked against the local run.`
    : 'No jargon. Built from the program you just analyzed.';
  updateGuideTabs();
  renderGuideContent(refs.guideContent, guide, state.analysis, state.activeGuideTab);
  replayClass(refs.guideContent, 'is-entering');
  if (resetScroll) refs.guideScroller.scrollTop = 0;
  if (state.selectedLine) setActiveGuideLine(refs.guideContent, state.selectedLine);
}

function updateGuideTabs() {
  refs.guideTabs.querySelectorAll('[data-guide-tab]').forEach((tab) => {
    const active = tab.dataset.guideTab === state.activeGuideTab;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', String(active));
  });
}

function setGuideTab(tab) {
  if (!['overview', 'walkthrough', 'lines', 'concepts'].includes(tab)) return;
  state.activeGuideTab = tab;
  updateGuideTabs();
  renderGuideContent(refs.guideContent, state.guide, state.analysis, tab);
  replayClass(refs.guideContent, 'is-entering');
  refs.guideScroller.scrollTop = 0;
  if (state.selectedLine) setActiveGuideLine(refs.guideContent, state.selectedLine);
}

function handleGuideClick(event) {
  const target = event.target.closest('[data-line]');
  if (!target) return;
  const line = Number(target.dataset.line);
  if (!Number.isFinite(line)) return;
  const endLine = Number(target.dataset.endLine || target.dataset.line);
  state.selectedLine = line;
  highlightSource(line, endLine, { scroll: true });
  state.activeView?.highlightLine?.(line);
  setActiveGuideLine(refs.guideContent, line);
}

/* -------------------------------------------------------------------------- */
/* AI                                                                         */
/* -------------------------------------------------------------------------- */

async function checkProxyState() {
  state.proxyAvailable = await checkProxy();
  updateAIChrome();
  if (state.inStudio) renderAIStrip();
}

function updateAIChrome() {
  if (!refs.aiButton) return;
  const configured = isAIConfigured(state.aiSettings);
  const label = refs.aiButton.querySelector('[data-ai-label]');
  if (label) label.textContent = configured ? 'AI ready' : 'Connect AI';
  refs.aiButton.setAttribute('aria-label', configured ? 'AI is configured. Open AI settings.' : 'Connect your AI');
  if (refs.aiStatusDot) {
    refs.aiStatusDot.hidden = !configured;
    refs.aiStatusDot.classList.toggle('is-offline', configured && !state.proxyAvailable);
  }
  const provider = getProvider(state.aiSettings.provider);
  refs.aiButton.title = configured
    ? `${provider.name} · ${state.aiSettings.model}${state.proxyAvailable ? '' : ' · local proxy offline'}`
    : 'Connect your own AI provider';
}

function renderAIStrip() {
  if (!state.inStudio) return;
  const configured = isAIConfigured(state.aiSettings);
  const provider = getProvider(state.aiSettings.provider);
  const aiGuide = state.guide?.author === 'ai';
  const model = state.aiSettings.model || provider.defaultModel;
  const proxyNote = state.proxyAvailable
    ? ''
    : ' Local proxy offline — start the app with npm start.';

  if (state.aiLoading) {
    refs.aiStrip.className = 'ai-strip is-loading';
    refs.aiStrip.innerHTML = `
      <div class="ai-strip-card">
        <span class="ai-strip-icon">${spinner(15)}</span>
        <div class="ai-strip-copy">
          <span class="ai-strip-title">Your AI is reading the code…</span>
          <span class="ai-strip-desc">Sending the source, local trace, and guide outline. This can take 10–30 seconds.</span>
        </div>
        <button type="button" class="ai-strip-action" disabled>Working…</button>
      </div>
    `;
    return;
  }

  if (!configured) {
    refs.aiStrip.className = 'ai-strip';
    refs.aiStrip.innerHTML = `
      <div class="ai-strip-card">
        <span class="ai-strip-icon">${icon('sparkles', 14)}</span>
        <div class="ai-strip-copy">
          <span class="ai-strip-title">Want a second explanation?</span>
          <span class="ai-strip-desc">Connect your own model. Prism sends the code only when you ask.</span>
        </div>
        <button type="button" class="ai-strip-action" data-ai-action="settings">Connect AI</button>
      </div>
      ${state.aiError ? renderAIError(state.aiError) : ''}
    `;
    return;
  }

  if (aiGuide) {
    refs.aiStrip.className = 'ai-strip is-ai';
    refs.aiStrip.innerHTML = `
      <div class="ai-strip-card">
        <span class="ai-strip-icon">${icon('sparkles', 14)}</span>
        <div class="ai-strip-copy">
          <span class="ai-strip-title">Enhanced by ${escapeHTML(state.guide.aiMeta?.providerName ?? provider.name)}</span>
          <span class="ai-strip-desc">${escapeHTML(state.guide.aiMeta?.model ?? model)} · ${state.proxyAvailable ? 'grounded in your local analysis' : 'the local proxy is currently offline'}</span>
        </div>
        <div class="ai-strip-actions">
          <button type="button" class="ai-strip-action" data-ai-action="enhance">Refresh</button>
          <button type="button" class="ai-strip-reset" data-ai-action="reset">Use local</button>
          <button type="button" class="ai-strip-settings" data-ai-action="settings" aria-label="AI settings" title="AI settings">${icon('sliders', 13)}</button>
        </div>
      </div>
      ${state.aiError ? renderAIError(state.aiError) : ''}
    `;
    return;
  }

  refs.aiStrip.className = 'ai-strip';
  refs.aiStrip.innerHTML = `
    <div class="ai-strip-card">
      <span class="ai-strip-icon">${icon('sparkles', 14)}</span>
      <div class="ai-strip-copy">
        <span class="ai-strip-title">A second pair of eyes?</span>
        <span class="ai-strip-desc">${escapeHTML(provider.name)} · ${escapeHTML(model)}. Ask your AI to expand the same guide.${escapeHTML(proxyNote)}</span>
      </div>
      <div class="ai-strip-actions">
        <button type="button" class="ai-strip-action" data-ai-action="enhance">Enhance guide</button>
        <button type="button" class="ai-strip-settings" data-ai-action="settings" aria-label="AI settings" title="AI settings">${icon('sliders', 13)}</button>
      </div>
    </div>
    ${state.aiError ? renderAIError(state.aiError) : ''}
  `;
}

function renderAIError(message) {
  return `<div class="ai-error"><span>${icon('warning', 13)}</span><span>${escapeHTML(message)}</span><button type="button" class="ai-strip-reset" data-ai-action="settings">Fix settings</button></div>`;
}

function openAISettings(initialTab = 'provider') {
  const getPortablePrompt = state.analysis && state.trace && state.localGuide
    ? (settings) => buildPortablePrompt({
        analysis: state.analysis,
        trace: state.trace,
        guide: state.localGuide,
        settings
      })
    : null;
  checkProxyState();
  openAISettingsModal({
    settings: state.aiSettings,
    proxyAvailable: state.proxyAvailable,
    initialTab,
    getPortablePrompt,
    onSave: (settings) => {
      state.aiSettings = normaliseAISettings(settings);
      state.aiError = null;
      updateAIChrome();
      persist();
      if (state.inStudio) renderAIStrip();
      checkProxyState();
    }
  });
}

async function enhanceWithAI() {
  if (!state.analysis || !state.trace || !state.localGuide) return;
  if (!isAIConfigured(state.aiSettings)) {
    openAISettings('provider');
    return;
  }
  if (state.aiLoading) return;
  const requestId = ++state.aiRequestId;
  const analysis = state.analysis;
  const trace = state.trace;
  const localGuide = state.localGuide;
  state.aiLoading = true;
  state.aiError = null;
  renderAIStrip();
  renderGuide();
  try {
    const result = await enhanceGuide({
      analysis,
      trace,
      guide: localGuide,
      settings: state.aiSettings
    });
    if (requestId !== state.aiRequestId || state.analysis !== analysis) return;
    result.guide.sourceLineCount = analysis.lineCount;
    state.guide = result.guide;
    state.aiLoading = false;
    state.aiError = null;
    renderGuide();
    renderAIStrip();
    updateAIChrome();
    state.activeGuideTab = 'overview';
    setGuideTab('overview');
    replayClass(refs.guideBadge, 'is-updated');
    announce('AI-enhanced guide ready.');
  } catch (error) {
    if (requestId !== state.aiRequestId) return;
    state.aiLoading = false;
    state.aiError = error?.message || 'The AI request failed.';
    renderAIStrip();
    renderGuide();
    updateAIChrome();
    announce('The AI request failed. The local guide is still available.');
  }
}

function resetAIGuide() {
  if (!state.localGuide) return;
  state.aiRequestId += 1;
  state.aiLoading = false;
  state.aiError = null;
  state.guide = state.localGuide;
  renderGuide();
  renderAIStrip();
  announce('Showing the local guide again.');
}

/* -------------------------------------------------------------------------- */
/* Copy, export, and the developer-facing surface                            */
/* -------------------------------------------------------------------------- */

async function copyCurrentGuide() {
  if (!state.guide || !state.analysis) return;
  const markdown = guideToMarkdown(state.guide, state.analysis, state.trace, MODE_BY_ID[state.activeMode].name);
  try {
    await copyText(markdown);
    announce('Guide copied as Markdown.');
  } catch {
    announce('The clipboard is unavailable. Use Export instead.');
  }
}

function toggleExportMenu(open = !state.exportOpen) {
  state.exportOpen = open;
  refs.exportMenu.hidden = !open;
  refs.exportButton.setAttribute('aria-expanded', String(open));
}

function handleExport(kind) {
  if (!state.guide || !state.analysis) return;
  toggleExportMenu(false);
  const base = `prism-${state.analysis.language.id}-${fileStem(MODE_BY_ID[state.activeMode].name)}`;
  if (kind === 'markdown') {
    downloadFile(`${base}-guide.md`, guideToMarkdown(state.guide, state.analysis, state.trace, MODE_BY_ID[state.activeMode].name), 'text/markdown;charset=utf-8');
    announce('Markdown guide downloaded.');
    return;
  }
  if (kind === 'json') {
    const data = guideToExportData(state.guide, state.analysis, state.trace, { modeName: MODE_BY_ID[state.activeMode].name });
    downloadFile(`${base}-analysis.json`, JSON.stringify(data, null, 2), 'application/json;charset=utf-8');
    announce('Analysis JSON downloaded.');
    return;
  }
  if (kind === 'prompt') {
    if (!state.localGuide) return;
    const prompt = buildPortablePrompt({
      analysis: state.analysis,
      trace: state.trace,
      guide: state.localGuide,
      settings: state.aiSettings
    });
    copyText(prompt)
      .then(() => announce('Portable AI prompt copied.'))
      .catch(() => announce('The clipboard is unavailable in this browser.'));
  }
}

/* -------------------------------------------------------------------------- */
/* Confirmation dialog                                                        */
/* -------------------------------------------------------------------------- */

function openConfirm({ title, message, confirmLabel = 'Confirm', onConfirm }) {
  if (!refs.modalRoot) return;
  refs.modalRoot.innerHTML = `
    <div class="modal-backdrop" data-confirm-backdrop>
      <div class="modal modal--compact" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
        <header class="modal-head">
          <div>
            <div class="modal-eyebrow">${icon('info', 12)} One quick check</div>
            <h2 id="confirmTitle">${escapeHTML(title)}</h2>
          </div>
          <button type="button" class="icon-button" data-confirm-close aria-label="Close dialog">${icon('close', 18)}</button>
        </header>
        <div class="confirm-body"><p>${escapeHTML(message)}</p></div>
        <footer class="modal-footer">
          <span class="modal-footer-note">Nothing is uploaded by this action.</span>
          <div class="modal-footer-actions">
            <button type="button" class="button button--ghost button--sm" data-confirm-cancel>Cancel</button>
            <button type="button" class="button button--primary button--sm" data-confirm-ok>${escapeHTML(confirmLabel)}</button>
          </div>
        </footer>
      </div>
    </div>
  `;
  const backdrop = refs.modalRoot.querySelector('[data-confirm-backdrop]');
  const previousFocus = document.activeElement;
  let closing = false;
  const close = (afterClose = null) => {
    if (closing) return;
    closing = true;
    document.removeEventListener('keydown', keyHandler);
    const closingBackdrop = backdrop;
    closingBackdrop.classList.add('is-closing');
    refs.modalRoot.querySelector('.modal')?.classList.add('is-closing');
    const delay = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 170;
    window.setTimeout(() => {
      if (!closingBackdrop.isConnected) return;
      refs.modalRoot.innerHTML = '';
      previousFocus?.focus?.();
      afterClose?.();
    }, delay);
  };
  const keyHandler = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  };
  refs.modalRoot.querySelector('[data-confirm-close]').addEventListener('click', close);
  refs.modalRoot.querySelector('[data-confirm-cancel]').addEventListener('click', close);
  refs.modalRoot.querySelector('[data-confirm-ok]').addEventListener('click', () => {
    close(onConfirm);
  });
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) close();
  });
  document.addEventListener('keydown', keyHandler);
  refs.modalRoot.querySelector('[data-confirm-ok]').focus();
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function sourceFileName(language) {
  if (!language) return '';
  if (language.id === 'java') return 'Main.java';
  return `main.${language.extension}`;
}

function countLines(code) {
  const count = String(code ?? '').split('\n').length;
  return `${count} line${count === 1 ? '' : 's'}`;
}

/* -------------------------------------------------------------------------- */
/* Event wiring                                                              */
/* -------------------------------------------------------------------------- */

function wireInterfaceEvents() {
  refs.languageGrid.addEventListener('click', (event) => {
    const button = event.target.closest('[data-language]');
    if (!button) return;
    selectLanguage(button.dataset.language);
  });

  refs.modeGrid.addEventListener('click', (event) => {
    const button = event.target.closest('[data-mode]');
    if (!button || button.disabled) return;
    selectMode(button.dataset.mode);
  });

  refs.analyzeButton.addEventListener('click', () => startAnalysis());
  refs.loadSampleButton.addEventListener('click', handleLoadStarter);
  refs.demoLink.addEventListener('click', () => runDemo());
  refs.themeToggle.addEventListener('click', toggleTheme);
  refs.brandLink.addEventListener('click', (event) => {
    event.preventDefault();
    if (state.inStudio) showIntake();
    else window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  refs.aiButton.addEventListener('click', () => openAISettings('provider'));

  refs.backButton.addEventListener('click', () => showIntake());
  refs.editCodeButton.addEventListener('click', () => showIntake({ focusEditor: true }));
  refs.sourceEditButton.addEventListener('click', () => showIntake({ focusEditor: true }));
  refs.copyGuideButton.addEventListener('click', copyCurrentGuide);

  refs.exportButton.addEventListener('click', (event) => {
    event.stopPropagation();
    toggleExportMenu();
  });
  refs.exportMenu.addEventListener('click', (event) => {
    const item = event.target.closest('[data-export]');
    if (!item) return;
    handleExport(item.dataset.export);
  });
  document.addEventListener('click', (event) => {
    if (!state.exportOpen) return;
    if (event.target.closest('.menu-wrap')) return;
    toggleExportMenu(false);
  });

  refs.vizTabs.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-mode]');
    if (!tab) return;
    setActiveMode(tab.dataset.mode);
  });

  refs.guideTabs.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-guide-tab]');
    if (!tab) return;
    setGuideTab(tab.dataset.guideTab);
  });

  refs.guideContent.addEventListener('click', handleGuideClick);

  refs.aiStrip.addEventListener('click', (event) => {
    const action = event.target.closest('[data-ai-action]')?.dataset.aiAction;
    if (!action) return;
    if (action === 'settings') openAISettings('provider');
    else if (action === 'enhance') enhanceWithAI();
    else if (action === 'reset') resetAIGuide();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (state.exportOpen) {
      toggleExportMenu(false);
      refs.exportButton.focus();
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') persist();
  });
  window.addEventListener('beforeunload', () => persist());

  const handleGuideTabKeys = (event) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    const tabs = [...refs.guideTabs.querySelectorAll('[data-guide-tab]')];
    const current = tabs.findIndex((tab) => tab.classList.contains('is-active'));
    if (current === -1) return;
    const next = clamp(current + (event.key === 'ArrowRight' ? 1 : -1), 0, tabs.length - 1);
    if (next === current) return;
    event.preventDefault();
    tabs[next].focus();
    setGuideTab(tabs[next].dataset.guideTab);
  };
  refs.guideTabs.addEventListener('keydown', handleGuideTabKeys);

  refs.vizTabs.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    const tabs = [...refs.vizTabs.querySelectorAll('[data-mode]')];
    const current = tabs.findIndex((tab) => tab.classList.contains('is-active'));
    if (current === -1) return;
    const next = clamp(current + (event.key === 'ArrowRight' ? 1 : -1), 0, tabs.length - 1);
    if (next === current) return;
    event.preventDefault();
    tabs[next].focus();
    setActiveMode(tabs[next].dataset.mode);
  });
}
