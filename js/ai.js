/**
 * Bring-your-own-AI integration.
 *
 * The browser never talks to a provider directly. It sends a single stateless
 * request to Prism's local /api/ai proxy, which forwards it to the provider the
 * user configured. The proxy stores neither the key nor the conversation.
 */

/**
 * Provider defaults were checked against the providers' documentation on
 * 13 November 2026. Model names change often; every field below is editable.
 */
export const AI_DEFAULT_MODELS_VERIFIED = 'November 2026';

export const AI_PROVIDERS = [
  {
    id: 'openai',
    name: 'OpenAI / compatible',
    short: 'OpenAI',
    description: 'OpenAI plus any other OpenAI-compatible /chat/completions endpoint.',
    defaultBaseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-6.1-terra',
    baseHint: 'Include the version path, e.g. https://api.openai.com/v1 or http://localhost:11434/v1',
    modelHint: 'Latest general-purpose default: gpt-6.1-terra. Use the model ID your gateway exposes.',
    requiresKey: false,
    keyHint: 'OpenAI requires a key. Leave it empty only for a local model such as Ollama.',
    monogram: 'O',
    color: '#2f6b56'
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    short: 'DeepSeek',
    description: 'DeepSeek through its OpenAI-compatible chat endpoint.',
    defaultBaseUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-flash',
    baseHint: 'Usually https://api.deepseek.com/v1',
    modelHint: 'Latest default: deepseek-flash. Another option is deepseek-v4-pro.',
    requiresKey: true,
    keyHint: 'Your DeepSeek API key. It is forwarded only for requests you start.',
    monogram: 'DS',
    color: '#3a63f0'
  },
  {
    id: 'grok',
    name: 'Grok (xAI)',
    short: 'Grok',
    description: "xAI's Grok through its OpenAI-compatible API.",
    defaultBaseUrl: 'https://api.x.ai/v1',
    defaultModel: 'grok-4.7',
    baseHint: 'Usually https://api.x.ai/v1',
    modelHint: 'Latest default: grok-4.7. Older example: grok-4.6.',
    requiresKey: true,
    keyHint: 'Your xAI API key. It is forwarded only for requests you start.',
    monogram: 'x',
    color: '#1f1f1f'
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    short: 'Anthropic',
    description: 'Claude models through the native Messages API.',
    defaultBaseUrl: 'https://api.anthropic.com',
    defaultModel: 'claude-fable-5-2',
    baseHint: 'Usually https://api.anthropic.com',
    modelHint: 'Latest default: claude-fable-5-2. Another option is claude-opus-5-5.',
    requiresKey: true,
    keyHint: 'Your Anthropic API key. It is forwarded only for this one request.',
    monogram: 'A',
    color: '#b35a2a'
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    short: 'Gemini',
    description: 'Gemini models through the Google Generative Language API.',
    defaultBaseUrl: 'https://generativelanguage.googleapis.com',
    defaultModel: 'gemini-4-hydrogen',
    baseHint: 'Usually https://generativelanguage.googleapis.com',
    modelHint: 'Latest default: gemini-4-hydrogen. Another option is gemini-4-carbon.',
    requiresKey: true,
    keyHint: 'Your Google AI Studio API key. It is forwarded only for this one request.',
    monogram: 'G',
    color: '#2f6bd8'
  }
];

export const EXPLAIN_LEVELS = [
  {
    id: 'beginner',
    label: 'Complete beginner',
    description: 'Assume no prior programming experience. Define every term the first time it matters.'
  },
  {
    id: 'some-experience',
    label: 'A little experience',
    description: 'You know basic variables and loops, but want the program’s intent and data flow spelled out.'
  },
  {
    id: 'deep-dive',
    label: 'Deep dive',
    description: 'You are comfortable with code and want sharper insight into design, edge cases, and language behaviour.'
  }
];

export const DEFAULT_AI_SETTINGS = {
  provider: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-6.1-terra',
  apiKey: '',
  rememberKey: false,
  explainLevel: 'beginner',
  extraInstructions: '',
  temperature: 0.3
};

// Old stock defaults are upgraded when settings are loaded. A custom base URL
// or a custom model ID is left untouched.
const LEGACY_DEFAULT_MODELS = {
  openai: new Set(['gpt-4o-mini']),
  anthropic: new Set(['claude-3-5-sonnet-latest']),
  gemini: new Set(['gemini-2.0-flash'])
};

export class AIRequestError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = 'AIRequestError';
    this.code = options.code ?? 'ai_error';
    this.status = options.status ?? null;
    this.raw = options.raw ?? '';
  }
}

export function getProvider(providerId) {
  return AI_PROVIDERS.find((provider) => provider.id === providerId) ?? AI_PROVIDERS[0];
}

export function normaliseAISettings(settings = {}) {
  const provider = getProvider(settings.provider);
  const requestedBase = String(settings.baseUrl || provider.defaultBaseUrl).trim();
  const requestedModel = String(settings.model || provider.defaultModel).trim();
  const usesStockBase = trimSlash(requestedBase) === trimSlash(provider.defaultBaseUrl);
  const isLegacyStockModel = usesStockBase && LEGACY_DEFAULT_MODELS[provider.id]?.has(requestedModel);
  return {
    ...DEFAULT_AI_SETTINGS,
    ...settings,
    provider: provider.id,
    baseUrl: requestedBase,
    model: isLegacyStockModel ? provider.defaultModel : requestedModel,
    apiKey: String(settings.apiKey ?? ''),
    explainLevel: EXPLAIN_LEVELS.some((level) => level.id === settings.explainLevel)
      ? settings.explainLevel
      : 'beginner',
    extraInstructions: String(settings.extraInstructions ?? '').slice(0, 1200),
    temperature: clamp(Number(settings.temperature ?? 0.3), 0, 1)
  };
}

export function isAIConfigured(settings) {
  if (!settings) return false;
  const provider = getProvider(settings.provider);
  if (!settings.baseUrl || !settings.model) return false;
  if (provider.requiresKey && !settings.apiKey) return false;
  const usingStockHostedEndpoint = trimSlash(settings.baseUrl) === trimSlash(provider.defaultBaseUrl);
  if (provider.id === 'openai' && usingStockHostedEndpoint && !settings.apiKey) return false;
  return true;
}

function trimSlash(value) {
  return String(value ?? '').trim().replace(/\/+$/, '');
}

export async function checkProxy() {
  try {
    const response = await fetch('/api/health', { headers: { Accept: 'application/json' } });
    if (!response.ok) return false;
    const data = await response.json();
    return !!data.ok;
  } catch {
    return false;
  }
}

export async function testAIConnection(settings) {
  const normalised = normaliseAISettings(settings);
  const data = await postAI(normalised, {
    system: 'You are a connectivity check. Reply with exactly PRISM_OK and nothing else.',
    messages: [{ role: 'user', content: 'Reply with exactly PRISM_OK.' }],
    maxTokens: 24,
    temperature: 0
  });
  return {
    text: data.text,
    provider: data.provider,
    model: data.model,
    elapsedMs: data.elapsedMs
  };
}

export async function enhanceGuide({ analysis, trace, guide, settings }) {
  const normalised = normaliseAISettings(settings);
  const provider = getProvider(normalised.provider);
  const { system, user } = buildAIPrompt({ analysis, trace, guide, settings: normalised });
  const data = await postAI(normalised, {
    system,
    messages: [{ role: 'user', content: user }],
    // Reasoning-capable defaults can spend part of this budget on internal
    // thinking, so leave room for the complete structured guide.
    maxTokens: 7000,
    temperature: normalised.temperature
  });
  const parsed = parseAIResponse(data.text);
  const merged = mergeAIGuide(guide, parsed, {
    provider: provider.id,
    providerName: provider.name,
    model: normalised.model
  });
  return {
    guide: merged,
    meta: {
      provider: provider.id,
      providerName: provider.name,
      model: normalised.model,
      elapsedMs: data.elapsedMs,
      usage: data.usage
    }
  };
}

async function postAI(settings, { system, messages, maxTokens, temperature }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 135_000);
  let response;
  try {
    response = await fetch('/api/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        provider: settings.provider,
        baseUrl: settings.baseUrl,
        model: settings.model,
        apiKey: settings.apiKey,
        system,
        messages,
        temperature,
        maxTokens
      }),
      signal: controller.signal
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new AIRequestError('The request took too long. The AI provider may be busy or unreachable.', { code: 'timeout' });
    }
    throw new AIRequestError(
      'Could not reach Prism’s local AI proxy. Start the app with “npm start” instead of opening the HTML file directly.',
      { code: 'proxy_unavailable' }
    );
  } finally {
    clearTimeout(timer);
  }

  let data;
  try {
    data = await response.json();
  } catch {
    throw new AIRequestError('The local proxy returned an unreadable response.', { code: 'bad_proxy_response' });
  }
  if (!response.ok) {
    throw new AIRequestError(data.error || `The AI request failed with HTTP ${response.status}.`, {
      code: 'provider_error',
      status: response.status
    });
  }
  if (typeof data.text !== 'string' || !data.text.trim()) {
    throw new AIRequestError('The AI provider returned an empty response.', { code: 'empty_response' });
  }
  return data;
}

/* -------------------------------------------------------------------------- */
/* Prompt construction                                                        */
/* -------------------------------------------------------------------------- */

export function buildAIPrompt({ analysis, trace, guide, settings }) {
  const level = EXPLAIN_LEVELS.find((item) => item.id === settings.explainLevel) ?? EXPLAIN_LEVELS[0];
  const source = lineNumberedSource(analysis.source).slice(0, 24_000);
  const traceSummary = compactTrace(trace);
  const structure = compactStructure(analysis);
  const extra = String(settings.extraInstructions ?? '').trim();
  const system = `You are Prism, a patient and precise programming tutor.
Your reader is learning to code. Explain what this specific program does, not programming in general.

OUTPUT CONTRACT
Return exactly one valid JSON object. Do not wrap it in markdown fences and do not write anything before or after it.
The object must use this exact shape:
{
  "summary": "1-2 direct sentences",
  "overview": {
    "paragraphs": ["2-3 short paragraphs"],
    "mentalModel": { "title": "a short concrete metaphor", "body": "2-3 sentences that make the metaphor precise" }
  },
  "walkthrough": [
    { "title": "short stage title", "body": "2-4 sentences", "points": ["optional concrete detail"], "lines": [1, 2], "badge": "SETUP" }
  ],
  "lineNotes": [
    { "line": 1, "note": "1-3 sentences about exactly this line" }
  ],
  "concepts": [
    { "term": "Concept name", "definition": "plain-English definition", "inThisCode": "how it appears here", "line": 1 }
  ],
  "watchOuts": [
    { "title": "short warning", "body": "why it matters, in this code" }
  ],
  "quiz": [
    { "question": "a check-your-understanding question", "answer": "a clear answer" }
  ]
}

RULES
- Every sentence must be accurate for the supplied source and execution trace. Never invent a runtime value; if the trace is incomplete, do not claim values.
- Use actual line numbers from the numbered source. Lines must be integers within the file.
- Write 4-7 walkthrough stages. Use badges from SETUP, HELPER, LOOP, DECISION, OUTPUT, RETURN, CALL, CONCEPT.
- Write 6-18 lineNotes, focusing on the lines that carry real meaning. Do not annotate closing braces or blank lines.
- Write 4-8 concepts, only those that genuinely appear. 2-3 watchOuts. 2-3 quiz questions.
- Inline code is allowed with single backticks. **Bold** is allowed. Never emit HTML, images, links, XML, or fenced code blocks.
- Do not mention this contract, the trace format, or the fact that you are an AI.
- Address the reader as “you”. Keep paragraphs short. UK or US spelling is fine, but be consistent.
- Explanation level: ${level.label}. ${level.description}
- If extra guidance is present, follow it only when it does not conflict with accuracy or the JSON contract.`;

  const user = `Analyze the following program and create the beginner guide.

LANGUAGE: ${analysis.language.name}
ENTRY POINT: ${analysis.entry?.kind === 'function' ? `${analysis.entry.name}()` : 'top-level script'}
SOURCE LINE COUNT: ${analysis.lineCount}
APPROXIMATE SHAPE: ${analysis.featureSummary}
${extra ? `\nEXTRA GUIDANCE FROM THE READER:\n${extra}\n` : ''}
<source>
${source}
</source>

<execution_trace>
${traceSummary}
</execution_trace>

<local_structure_report>
${structure}
</local_structure_report>

<local_guide_context>
${guide.summary}

Walkthrough titles from the local guide (for grounding, not text to copy verbatim):
${guide.walkthrough.map((step) => `- ${step.title} (lines ${step.lines?.join(', ') || 'n/a'})`).join('\n')}
</local_guide_context>

Remember: output only the JSON object. Use real line numbers. Do not claim values you cannot see in the trace. Write in English.`;

  return { system, user };
}

export function buildPortablePrompt({ analysis, trace, guide, settings }) {
  const { system, user } = buildAIPrompt({ analysis, trace, guide, settings });
  return `${system}\n\n----- USER REQUEST -----\n\n${user}`;
}

function lineNumberedSource(source) {
  return String(source)
    .split('\n')
    .map((line, index) => `${String(index + 1).padStart(4, ' ')} | ${line}`)
    .join('\n');
}

function compactTrace(trace) {
  if (!trace) return 'No trace available.';
  const lines = [];
  lines.push(`Complete: ${trace.complete ? 'yes' : 'no'}`);
  if (trace.output) lines.push(`Output:\n${truncate(trace.output, 4000)}`);
  if (trace.warnings?.length) {
    lines.push(`Trace notes:\n${trace.warnings.map((warning) => `- line ${warning.line}: ${warning.message}`).join('\n')}`);
  }
  lines.push('Steps:');
  for (const step of trace.steps.slice(0, 90)) {
    const vars = (step.vars ?? []).slice(-5).map((variable) => `${variable.name}=${variable.display}`).join(', ');
    lines.push(`- L${step.line} [${step.kind}] ${step.title}${vars ? ` | ${vars}` : ''}`);
  }
  if (trace.steps.length > 90) lines.push(`- … ${trace.steps.length - 90} more steps`);
  return truncate(lines.join('\n'), 16_000);
}

function compactStructure(analysis) {
  const parts = [];
  parts.push(`Functions: ${analysis.functions.map((fn) => `${fn.name}(${fn.params.map((param) => param.name).join(', ')}) at L${fn.startLine}`).join('; ') || 'none'}`);
  const loops = [];
  const conditions = [];
  const actions = [];
  const visit = (node) => {
    if (!node) return;
    if (node.type === 'for' || node.type === 'while' || node.type === 'do') loops.push(`L${node.startLine} ${node.header ?? node.condition}`);
    if (node.type === 'if') conditions.push(`L${node.startLine} ${node.condition}`);
    if (node.type === 'action' && node.action?.subtype !== 'comment') {
      actions.push(`L${node.startLine} [${node.action?.subtype ?? node.type}] ${(node.text ?? '').slice(0, 110)}`);
    }
    if (node.type === 'block') node.children?.forEach(visit);
    if (node.body?.children) node.body.children.forEach(visit);
    if (node.consequent?.children) node.consequent.children.forEach(visit);
    if (node.alternate?.children) node.alternate.children.forEach(visit);
    node.handlers?.forEach((handler) => handler.body?.children?.forEach(visit));
  };
  visit(analysis.root);
  parts.push(`Loops: ${loops.join('; ') || 'none'}`);
  parts.push(`Conditions: ${conditions.join('; ') || 'none'}`);
  parts.push(`Statements:\n${actions.slice(0, 60).join('\n')}`);
  return truncate(parts.join('\n'), 10_000);
}

/* -------------------------------------------------------------------------- */
/* Response validation and merge                                              */
/* -------------------------------------------------------------------------- */

export function parseAIResponse(text) {
  const clean = stripFences(String(text ?? '')).trim();
  if (!clean) throw new AIRequestError('The AI returned no text.', { code: 'empty_response', raw: text });
  const start = clean.indexOf('{');
  const end = clean.lastIndexOf('}');
  if (start === -1 || end === -1 || end <= start) {
    throw new AIRequestError(
      'The AI replied, but not in the structured guide format Prism expects. Try again or switch models.',
      { code: 'invalid_json', raw: clean }
    );
  }
  let parsed;
  try {
    parsed = JSON.parse(clean.slice(start, end + 1));
  } catch (error) {
    throw new AIRequestError(
      'The AI’s JSON response was incomplete or malformed. Try again with a model that follows JSON instructions well.',
      { code: 'invalid_json', raw: clean }
    );
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new AIRequestError('The AI response was not a JSON object.', { code: 'invalid_json', raw: clean });
  }
  return parsed;
}

function stripFences(text) {
  return text
    .replace(/^\s*```(?:json)?\s*/i, '')
    .replace(/\s*```\s*$/i, '');
}

export function mergeAIGuide(localGuide, parsed, meta) {
  const safe = sanitiseAIResponse(parsed, localGuide);
  const mergedNotes = mergeLineNotes(localGuide.lineNotes, safe.lineNotes);
  const merged = {
    ...localGuide,
    author: 'ai',
    summary: safe.summary || localGuide.summary,
    overview: {
      ...localGuide.overview,
      paragraphs: safe.overview.paragraphs.length ? safe.overview.paragraphs : localGuide.overview.paragraphs,
      mentalModel: safe.overview.mentalModel.title && safe.overview.mentalModel.body
        ? safe.overview.mentalModel
        : localGuide.overview.mentalModel
    },
    walkthrough: safe.walkthrough.length ? ensureOutputStep(localGuide, safe.walkthrough) : localGuide.walkthrough,
    lineNotes: mergedNotes,
    concepts: safe.concepts.length ? safe.concepts : localGuide.concepts,
    watchOuts: safe.watchOuts.length ? safe.watchOuts : localGuide.watchOuts,
    quiz: safe.quiz.length ? safe.quiz : localGuide.quiz,
    aiMeta: {
      provider: meta.provider,
      providerName: meta.providerName,
      model: meta.model,
      enhancedAt: Date.now()
    }
  };
  const text = [
    merged.summary,
    ...merged.overview.paragraphs,
    merged.overview.mentalModel.title,
    merged.overview.mentalModel.body,
    ...merged.walkthrough.flatMap((step) => [step.title, step.body, ...(step.points ?? [])]),
    ...merged.lineNotes.map((note) => note.note),
    ...merged.concepts.flatMap((concept) => [concept.term, concept.definition, concept.inThisCode]),
    ...merged.watchOuts.flatMap((item) => [item.title, item.body]),
    ...merged.quiz.flatMap((item) => [item.question, item.answer])
  ].join(' ');
  merged.wordCount = text.split(/\s+/).filter(Boolean).length;
  merged.readingMinutes = Math.max(1, Math.round(merged.wordCount / 210));
  return merged;
}

function sanitiseAIResponse(parsed, localGuide) {
  const summary = cleanString(parsed.summary, 1200);
  const overviewSource = parsed.overview && typeof parsed.overview === 'object' ? parsed.overview : {};
  const paragraphs = Array.isArray(overviewSource.paragraphs)
    ? overviewSource.paragraphs.map((paragraph) => cleanString(paragraph, 1800)).filter(Boolean).slice(0, 4)
    : [];
  const mentalModelData = overviewSource.mentalModel && typeof overviewSource.mentalModel === 'object'
    ? overviewSource.mentalModel
    : {};
  const mentalModel = {
    title: cleanString(mentalModelData.title, 160),
    body: cleanString(mentalModelData.body, 1200)
  };
  const sourceLineCount = Number(localGuide.sourceLineCount) || 0;
  const walkthrough = Array.isArray(parsed.walkthrough)
    ? parsed.walkthrough
        .slice(0, 8)
        .map((step) => {
          if (!step || typeof step !== 'object') return null;
          return {
            title: cleanString(step.title, 180),
            body: cleanString(step.body, 1600),
            points: Array.isArray(step.points)
              ? step.points.map((point) => cleanString(point, 500)).filter(Boolean).slice(0, 5)
              : [],
            lines: cleanLines(step.lines, sourceLineCount),
            badge: cleanBadge(step.badge),
            author: 'ai'
          };
        })
        .filter((step) => step && step.title && step.body)
    : [];
  const lineNotes = Array.isArray(parsed.lineNotes)
    ? parsed.lineNotes
        .slice(0, 40)
        .map((item) => {
          if (!item) return null;
          const line = Number(item.line);
          if (!Number.isInteger(line) || line < 1 || (sourceLineCount && line > sourceLineCount)) return null;
          return { line, note: cleanString(item.note, 1200) };
        })
        .filter((item) => item && item.note)
    : [];
  const concepts = Array.isArray(parsed.concepts)
    ? parsed.concepts
        .slice(0, 10)
        .map((concept) => {
          if (!concept || typeof concept !== 'object') return null;
          const line = Number(concept.line);
          return {
            term: cleanString(concept.term, 120),
            definition: cleanString(concept.definition, 1000),
            inThisCode: cleanString(concept.inThisCode, 1000),
            line: Number.isInteger(line) && line >= 1 && (!sourceLineCount || line <= sourceLineCount) ? line : null,
            author: 'ai'
          };
        })
        .filter((concept) => concept && concept.term && concept.definition && concept.inThisCode)
    : [];
  const watchOuts = Array.isArray(parsed.watchOuts)
    ? parsed.watchOuts
        .slice(0, 4)
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          return { title: cleanString(item.title, 180), body: cleanString(item.body, 1000) };
        })
        .filter((item) => item && item.title && item.body)
    : [];
  const quiz = Array.isArray(parsed.quiz)
    ? parsed.quiz
        .slice(0, 4)
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          return { question: cleanString(item.question, 500), answer: cleanString(item.answer, 1000) };
        })
        .filter((item) => item && item.question && item.answer)
    : [];
  return { summary, overview: { paragraphs, mentalModel }, walkthrough, lineNotes, concepts, watchOuts, quiz };
}

function mergeLineNotes(localNotes, aiNotes) {
  if (!aiNotes.length) return localNotes;
  const localByLine = new Map(localNotes.map((note) => [note.line, note]));
  const merged = new Map(localNotes.map((note) => [note.line, note]));
  for (const note of aiNotes) {
    const existing = localByLine.get(note.line);
    merged.set(note.line, {
      line: note.line,
      endLine: existing?.endLine ?? note.line,
      code: existing?.code ?? '',
      note: note.note,
      tone: existing?.tone ?? 'ai',
      synthetic: false,
      author: 'ai'
    });
  }
  return [...merged.values()].sort((a, b) => a.line - b.line).slice(0, 60);
}

function ensureOutputStep(localGuide, walkthrough) {
  if (walkthrough.some((step) => step.output || /print|output/i.test(`${step.title} ${step.badge}`))) {
    return walkthrough;
  }
  const outputStep = localGuide.walkthrough.find((step) => step.output);
  if (outputStep) {
    return [
      ...walkthrough,
      { ...outputStep, author: 'ai' }
    ].slice(0, 12);
  }
  return walkthrough;
}

function cleanString(value, max) {
  if (typeof value !== 'string') return '';
  return value
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/\u0000/g, '')
    .trim()
    .slice(0, max);
}

function cleanLines(value, sourceLineCount) {
  if (!Array.isArray(value)) return [];
  const maxLine = Math.max(1, Number(sourceLineCount) || 1);
  return [...new Set(value.map(Number).filter((line) => Number.isInteger(line) && line >= 1 && line <= maxLine))].slice(0, 8);
}

function cleanBadge(value) {
  const badge = typeof value === 'string' ? value.trim().toUpperCase().slice(0, 20) : '';
  return badge || 'CONCEPT';
}

function clamp(value, min, max) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function truncate(value, max) {
  const text = String(value ?? '');
  return text.length > max ? `${text.slice(0, max)}\n…` : text;
}
