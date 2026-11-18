/**
 * AI connection settings.
 *
 * This modal never sends a request by itself except when you explicitly press
 * "Test connection". It exposes the local proxy contract as well, so the app can
 * be connected to providers or gateways that Prism has never heard of.
 */

import {
  AI_DEFAULT_MODELS_VERIFIED,
  AI_PROVIDERS,
  EXPLAIN_LEVELS,
  getProvider,
  isAIConfigured,
  normaliseAISettings,
  testAIConnection
} from '../ai.js';
import { icon, spinner } from '../icons.js';
import { escapeHTML, copyText, announce } from '../utils.js';

const TABS = [
  { id: 'provider', label: 'Connection', icon: 'plug' },
  { id: 'prompt', label: 'Explanation', icon: 'book' },
  { id: 'api', label: 'Developer API', icon: 'code' }
];

// Older saved settings should not keep an unrelated model when the user
// switches to a new provider. Custom model IDs are still preserved.
const LEGACY_DEFAULT_MODELS = new Set([
  'gpt-4o-mini',
  'claude-3-5-sonnet-latest',
  'gemini-2.0-flash',
  'deepseek-chat'
]);

export function openAISettingsModal({
  settings,
  proxyAvailable = false,
  initialTab = 'provider',
  getPortablePrompt = null,
  onSave = () => {}
}) {
  const root = document.getElementById('modalRoot');
  if (!root) return;
  const initial = normaliseAISettings(settings);
  const draft = { ...initial };
  let activeTab = TABS.some((tab) => tab.id === initialTab) ? initialTab : 'provider';
  let previousFocus = document.activeElement;
  let testBusy = false;
  let closing = false;

  root.innerHTML = `
    <div class="modal-backdrop" data-ai-backdrop>
      <div class="modal modal--ai" role="dialog" aria-modal="true" aria-labelledby="aiModalTitle">
        <header class="modal-head">
          <div>
            <div class="modal-eyebrow">${icon('sparkles', 12)} Bring your own intelligence</div>
            <h2 id="aiModalTitle">Connect your AI</h2>
            <p>Prism writes the full guide locally. Connect a model only when you want a second, richer explanation of the same code.</p>
          </div>
          <button type="button" class="icon-button modal-close" data-ai-close aria-label="Close AI settings">${icon('close', 18)}</button>
        </header>
        <div class="modal-body">
          <nav class="modal-nav" aria-label="AI settings sections">
            ${TABS.map((tab) => `<button type="button" class="modal-nav-button ${tab.id === activeTab ? 'is-active' : ''}" data-ai-nav="${tab.id}">${icon(tab.icon, 14)}<span>${tab.label}</span></button>`).join('')}
            <p class="modal-nav-note">${icon('lock', 12)} Keys stay in your browser and are forwarded only for requests you start.</p>
          </nav>
          <div class="modal-content">
            <div class="modal-panel" data-ai-panel="provider">
              <div class="panel-intro">
                <h3>Choose a provider</h3>
                <p>Prism speaks to OpenAI, DeepSeek, xAI Grok, Anthropic, and Google Gemini. The first three share an OpenAI-compatible connection; your provider must allow the model you enter.</p>
                <p>Defaults point at each provider's newest generally available model (verified ${escapeHTML(AI_DEFAULT_MODELS_VERIFIED)}). You can always type a different model ID.</p>
              </div>
              <div class="provider-grid" data-provider-grid></div>
              <div class="field-grid">
                <label class="field field--full">
                  <span class="field-label">Base URL</span>
                  <input class="field-input" data-ai-field="baseUrl" type="url" spellcheck="false" autocomplete="off" placeholder="https://api.openai.com/v1">
                  <span class="field-hint" data-hint="baseUrl"></span>
                </label>
                <label class="field field--full">
                  <span class="field-label">Model</span>
                  <input class="field-input" data-ai-field="model" type="text" spellcheck="false" autocomplete="off" placeholder="gpt-6.1-terra">
                  <span class="field-hint" data-hint="model"></span>
                </label>
                <label class="field field--full">
                  <span class="field-label">API key <span class="field-optional">stored locally</span></span>
                  <span class="input-with-action">
                    <input class="field-input" data-ai-field="apiKey" type="password" spellcheck="false" autocomplete="off" placeholder="sk-…">
                    <button type="button" class="field-inline-button" data-toggle-key aria-label="Show API key" title="Show / hide key">${icon('eye', 14)}</button>
                  </span>
                </label>
              </div>
              <p class="field-hint" data-hint="key"></p>
              <label class="check-row">
                <input type="checkbox" data-ai-field="rememberKey">
                <span>Remember the key on this device. When unchecked, it lives only in this page’s memory and disappears on refresh.</span>
              </label>
              <div class="privacy-box">${icon('lock', 14)}<span>Your key is sent to Prism’s local proxy, not to a Prism account. The proxy forwards it to the provider you choose, stores no request, and logs no key. Run this app locally to keep the whole path on your machine.</span></div>
              <div class="connection-status" data-test-status role="status"></div>
            </div>

            <div class="modal-panel" data-ai-panel="prompt" hidden>
              <div class="panel-intro">
                <h3>Set the reading level</h3>
                <p>The AI receives the source, the local run trace, and this guide’s structure. It is told to explain only what it can verify.</p>
              </div>
              <div class="level-grid" data-level-grid>
                ${EXPLAIN_LEVELS.map((level) => `
                  <button type="button" class="level-card" data-level="${level.id}">
                    <strong>${escapeHTML(level.label)}</strong>
                    <span>${escapeHTML(level.description)}</span>
                  </button>
                `).join('')}
              </div>
              <label class="field field--full">
                <span class="field-label">Extra guidance for your AI <span class="field-optional">optional</span></span>
                <textarea class="field-textarea" data-ai-field="extraInstructions" maxlength="1200" placeholder="For example: use a sports analogy, or spend more time on the loop boundary."></textarea>
                <span class="field-hint">Kept with your local settings. It is included in each AI guide request.</span>
              </label>
              <details class="advanced-box">
                <summary>Advanced <span>temperature</span></summary>
                <div class="advanced-content">
                  <div class="field">
                    <span class="field-label">Creativity</span>
                    <div class="range-row">
                      <input type="range" min="0" max="1" step="0.05" data-ai-field="temperature">
                      <span class="range-value" data-temp-value>0.30</span>
                    </div>
                    <span class="field-hint">Lower values are more literal and consistent; higher values are more conversational. 0.3 is a good default for explanations. Some newer reasoning models choose their own sampling and ignore this value.</span>
                  </div>
                </div>
              </details>
              <div class="prompt-summary-card">
                <strong>What gets sent?</strong>
                <span>The source, language, entry point, a compact execution trace, and the local guide’s outline. Never your entire browser storage, never another tab, and never your API key in a log.</span>
              </div>
              ${getPortablePrompt ? `<button type="button" class="button button--ghost button--sm" data-copy-prompt>${icon('copy', 14)} Copy portable prompt</button>` : ''}
            </div>

            <div class="modal-panel" data-ai-panel="api" hidden>
              <div class="panel-intro">
                <h3>A deliberately small API</h3>
                <p>The UI is just one client. The local /api/ai endpoint is documented here so you can connect any compatible workflow, script, or gateway.</p>
              </div>
              <div class="api-block">
                <div class="api-block-head">
                  <span>POST /api/ai · request</span>
                  <button type="button" class="copy-mini" data-copy-target="curl">${icon('copy', 11)} copy</button>
                </div>
                <pre class="api-code" data-api-sample></pre>
              </div>
              <div class="api-block">
                <div class="api-block-head">
                  <span>response</span>
                  <button type="button" class="copy-mini" data-copy-target="response">${icon('copy', 11)} copy</button>
                </div>
                <pre class="api-code" data-api-response></pre>
              </div>
              <p class="api-note"><strong>No key is stored server-side.</strong> The proxy is stateless and binds to <code>127.0.0.1</code> by default. It accepts <code>provider</code> (<code>openai</code>, <code>deepseek</code>, <code>grok</code>, <code>anthropic</code>, or <code>gemini</code>), <code>baseUrl</code>, <code>model</code>, <code>apiKey</code>, <code>system</code>, and an OpenAI-style <code>messages</code> array, then normalises the provider response to <code>{ text, provider, model, usage, elapsedMs }</code>.</p>
              <div class="privacy-box">${icon('server', 14)}<span>This endpoint is a bring-your-own-key bridge, not a Prism cloud service. Do not expose it to the public internet without adding authentication and rate limiting.</span></div>
            </div>
          </div>
        </div>
        <footer class="modal-footer">
          <span class="modal-footer-note">${proxyAvailable ? 'Local AI proxy is reachable.' : 'Local AI proxy not detected. Start the app with npm start to call a provider.'}</span>
          <div class="modal-footer-actions">
            <button type="button" class="button button--ghost button--sm" data-test-connection>${icon('plug', 14)} Test connection</button>
            <button type="button" class="button button--primary button--sm" data-save-ai>Save configuration</button>
          </div>
        </footer>
      </div>
    </div>
  `;

  const backdrop = root.querySelector('[data-ai-backdrop]');
  const content = root.querySelector('.modal-content');
  const closeButton = root.querySelector('[data-ai-close]');
  const providerGrid = root.querySelector('[data-provider-grid]');
  const levelGrid = root.querySelector('[data-level-grid]');
  const fields = {
    baseUrl: root.querySelector('[data-ai-field="baseUrl"]'),
    model: root.querySelector('[data-ai-field="model"]'),
    apiKey: root.querySelector('[data-ai-field="apiKey"]'),
    rememberKey: root.querySelector('[data-ai-field="rememberKey"]'),
    extraInstructions: root.querySelector('[data-ai-field="extraInstructions"]'),
    temperature: root.querySelector('[data-ai-field="temperature"]')
  };
  const testStatus = root.querySelector('[data-test-status]');
  const apiSample = root.querySelector('[data-api-sample]');
  const apiResponse = root.querySelector('[data-api-response]');

  function renderProviderGrid() {
    providerGrid.innerHTML = AI_PROVIDERS.map((provider) => `
      <button type="button" class="provider-card ${draft.provider === provider.id ? 'is-selected' : ''}" data-provider="${provider.id}" aria-pressed="${draft.provider === provider.id}">
        <span class="provider-icon" style="--provider-color:${provider.color}" aria-hidden="true">${escapeHTML(provider.monogram)}</span>
        <span class="provider-name">${escapeHTML(provider.name)}</span>
        <span class="provider-description">${escapeHTML(provider.description)}</span>
      </button>
    `).join('');
  }

  function renderLevelGrid() {
    levelGrid.querySelectorAll('[data-level]').forEach((button) => {
      button.classList.toggle('is-selected', button.dataset.level === draft.explainLevel);
    });
  }

  function syncFields() {
    const provider = getProvider(draft.provider);
    fields.baseUrl.value = draft.baseUrl;
    fields.model.value = draft.model;
    fields.apiKey.value = draft.apiKey;
    fields.rememberKey.checked = !!draft.rememberKey;
    fields.extraInstructions.value = draft.extraInstructions;
    fields.temperature.value = String(draft.temperature);
    root.querySelector('[data-temp-value]').textContent = Number(draft.temperature).toFixed(2);
    fields.baseUrl.placeholder = provider.defaultBaseUrl;
    fields.model.placeholder = provider.defaultModel;
    fields.apiKey.placeholder = provider.requiresKey ? 'Required for this provider' : 'Optional for local models';
    root.querySelector('[data-hint="baseUrl"]').textContent = provider.baseHint;
    root.querySelector('[data-hint="model"]').textContent = provider.modelHint;
    root.querySelector('[data-hint="key"]').textContent = provider.keyHint;
    renderLevelGrid();
    renderApiDocs();
  }

  function setTab(tabId) {
    activeTab = tabId;
    root.querySelectorAll('[data-ai-nav]').forEach((button) => button.classList.toggle('is-active', button.dataset.aiNav === tabId));
    root.querySelectorAll('[data-ai-panel]').forEach((panel) => { panel.hidden = panel.dataset.aiPanel !== tabId; });
    const panel = root.querySelector(`[data-ai-panel="${tabId}"]`);
    if (panel) {
      panel.classList.remove('is-entering');
      void panel.offsetWidth;
      panel.classList.add('is-entering');
    }
    content.scrollTop = 0;
  }

  function renderApiDocs() {
    const provider = getProvider(draft.provider);
    const origin = location.protocol.startsWith('http') ? location.origin : 'http://127.0.0.1:4173';
    const payload = {
      provider: draft.provider,
      baseUrl: draft.baseUrl || provider.defaultBaseUrl,
      model: draft.model || provider.defaultModel,
      apiKey: provider.requiresKey ? 'YOUR_API_KEY' : '',
      system: 'You are a patient programming tutor.',
      messages: [{ role: 'user', content: 'Explain this JavaScript code for a beginner.' }],
      temperature: 0.3,
      maxTokens: 2600
    };
    apiSample.textContent = `curl -X POST ${origin}/api/ai \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(payload, null, 2)}'`;
    apiResponse.textContent = JSON.stringify({
      text: 'The JSON explanation returned by your model…',
      provider: draft.provider,
      model: draft.model || provider.defaultModel,
      usage: { input_tokens: 1280, output_tokens: 920 },
      elapsedMs: 4120
    }, null, 2);
  }

  providerGrid.addEventListener('click', (event) => {
    const card = event.target.closest('[data-provider]');
    if (!card) return;
    const previous = getProvider(draft.provider);
    const next = getProvider(card.dataset.provider);
    if (!draft.baseUrl || draft.baseUrl === previous.defaultBaseUrl) draft.baseUrl = next.defaultBaseUrl;
    if (!draft.model || draft.model === previous.defaultModel || LEGACY_DEFAULT_MODELS.has(draft.model)) {
      draft.model = next.defaultModel;
    }
    draft.provider = next.id;
    renderProviderGrid();
    syncFields();
  });

  levelGrid.addEventListener('click', (event) => {
    const card = event.target.closest('[data-level]');
    if (!card) return;
    draft.explainLevel = card.dataset.level;
    renderLevelGrid();
  });

  fields.baseUrl.addEventListener('input', () => { draft.baseUrl = fields.baseUrl.value.trim(); renderApiDocs(); });
  fields.model.addEventListener('input', () => { draft.model = fields.model.value.trim(); renderApiDocs(); });
  fields.apiKey.addEventListener('input', () => { draft.apiKey = fields.apiKey.value; });
  fields.rememberKey.addEventListener('change', () => { draft.rememberKey = fields.rememberKey.checked; });
  fields.extraInstructions.addEventListener('input', () => { draft.extraInstructions = fields.extraInstructions.value; });
  fields.temperature.addEventListener('input', () => {
    draft.temperature = Number(fields.temperature.value);
    root.querySelector('[data-temp-value]').textContent = Number(draft.temperature).toFixed(2);
  });

  root.querySelector('[data-toggle-key]').addEventListener('click', (event) => {
    const visible = fields.apiKey.type === 'text';
    fields.apiKey.type = visible ? 'password' : 'text';
    event.currentTarget.innerHTML = icon(visible ? 'eye' : 'eyeOff', 14);
    event.currentTarget.setAttribute('aria-label', visible ? 'Show API key' : 'Hide API key');
  });

  root.querySelectorAll('[data-ai-nav]').forEach((button) => {
    button.addEventListener('click', () => setTab(button.dataset.aiNav));
  });

  root.querySelector('[data-test-connection]').addEventListener('click', async () => {
    if (testBusy) return;
    const validation = validateDraft(draft);
    if (!validation.ok) {
      setTab('provider');
      setTestStatus(validation.message, 'error');
      return;
    }
    testBusy = true;
    const button = root.querySelector('[data-test-connection]');
    button.disabled = true;
    button.innerHTML = `${spinner(14)} Testing…`;
    setTestStatus('Trying a tiny request through the local proxy…', 'busy');
    try {
      const result = await testAIConnection(draft);
      setTestStatus(`Connected to ${getProvider(draft.provider).name} · ${result.model} · ${Math.round(result.elapsedMs ?? 0)} ms`, 'success');
    } catch (error) {
      setTestStatus(error?.message || 'The connection test failed.', 'error');
    } finally {
      testBusy = false;
      button.disabled = false;
      button.innerHTML = `${icon('plug', 14)} Test connection`;
    }
  });

  root.querySelector('[data-save-ai]').addEventListener('click', () => {
    const validation = validateDraft(draft);
    if (!validation.ok) {
      setTab('provider');
      setTestStatus(validation.message, 'error');
      fields.baseUrl.focus();
      return;
    }
    const saved = normaliseAISettings(draft);
    onSave(saved);
    close();
    announce(isAIConfigured(saved) ? 'AI configuration saved.' : 'AI configuration saved, but it is incomplete.');
  });

  const copyButtons = root.querySelectorAll('[data-copy-target]');
  copyButtons.forEach((button) => {
    button.addEventListener('click', async () => {
      const target = button.dataset.copyTarget;
      const text = target === 'curl' ? apiSample.textContent : apiResponse.textContent;
      try {
        await copyText(text);
        announce('Copied to clipboard.');
      } catch {
        announce('The clipboard is unavailable in this browser.');
      }
    });
  });

  const promptCopy = root.querySelector('[data-copy-prompt]');
  if (promptCopy) {
    promptCopy.addEventListener('click', async () => {
      try {
        const text = getPortablePrompt?.(normaliseAISettings(draft));
        if (!text) {
          announce('Run an analysis first, then open this setting to copy its prompt.');
          return;
        }
        await copyText(text);
        announce('Portable AI prompt copied.');
      } catch (error) {
        announce(error?.message || 'Could not prepare the prompt.');
      }
    });
  }

  function setTestStatus(message, tone) {
    testStatus.textContent = message;
    testStatus.className = `connection-status ${tone ? `is-${tone}` : ''}`;
  }

  function close() {
    if (closing) return;
    closing = true;
    document.removeEventListener('keydown', onKeyDown);
    const closingBackdrop = backdrop;
    closingBackdrop.classList.add('is-closing');
    root.querySelector('.modal')?.classList.add('is-closing');
    const delay = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 170;
    window.setTimeout(() => {
      if (!closingBackdrop.isConnected) return;
      root.innerHTML = '';
      previousFocus?.focus?.();
    }, delay);
  }

  const onKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...root.querySelectorAll('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
      .filter((element) => element.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  closeButton.addEventListener('click', close);
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) close();
  });
  document.addEventListener('keydown', onKeyDown);

  renderProviderGrid();
  syncFields();
  renderLevelGrid();
  setTab(activeTab);
  closeButton.focus();
}

function validateDraft(draft) {
  const provider = getProvider(draft.provider);
  if (!draft.baseUrl) return { ok: false, message: 'Enter the provider base URL.' };
  try {
    const url = new URL(draft.baseUrl);
    if (!['http:', 'https:'].includes(url.protocol)) return { ok: false, message: 'The base URL must start with http:// or https://.' };
  } catch {
    return { ok: false, message: 'The base URL is not a valid URL.' };
  }
  if (!draft.model) return { ok: false, message: 'Enter a model name.' };
  if (provider.requiresKey && !draft.apiKey) return { ok: false, message: `${provider.name} requires an API key.` };
  const normalisedBase = String(draft.baseUrl).trim().replace(/\/+$/, '');
  const defaultBase = String(provider.defaultBaseUrl).trim().replace(/\/+$/, '');
  if (provider.id === 'openai' && !draft.apiKey && normalisedBase === defaultBase) {
    return { ok: false, message: 'Add an API key for OpenAI, or enter a local/custom compatible endpoint that does not need one.' };
  }
  return { ok: true };
}
