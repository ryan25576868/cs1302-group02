/**
 * Core regression suite. No browser or network required.
 * Run with: npm test
 */
import assert from 'node:assert/strict';
import { LANGUAGES } from '../js/data/languages.js';
import { analyzeSource, getFlowFoci } from '../js/core/analyzer.js';
import { simulate } from '../js/core/interpreter.js';
import { buildGuide } from '../js/core/explainer.js';
import { buildSyntaxTree } from '../js/core/syntax-tree.js';
import { guideToExportData, guideToMarkdown } from '../js/ui/guide-view.js';
import {
  AI_PROVIDERS,
  getProvider,
  isAIConfigured,
  normaliseAISettings,
  parseAIResponse
} from '../js/ai.js';

const EXPECTED_OUTPUT = {
  javascript: 'Total: 40.5\n',
  python: 'Total: 40.5\n',
  typescript: 'Total: 40.5\n',
  java: 'Total: 40.5\n',
  cpp: 'Total: 40.5\n',
  c: 'Total: 40.50\n'
};

let checks = 0;
const check = (condition, message) => {
  assert.ok(condition, message);
  checks += 1;
};

for (const language of LANGUAGES) {
  console.log(`Checking ${language.name}…`);
  const analysis = analyzeSource(language.sample, language);
  check(analysis.lineCount > 0, `${language.id}: line count`);
  check(analysis.diagnostics.length === 0, `${language.id}: no parser warnings`);
  check(analysis.functions.length >= 1, `${language.id}: functions were found`);
  check(analysis.actionNodes.length >= 3, `${language.id}: actions were found`);
  check(analysis.metrics.loops === 1, `${language.id}: loop count`);

  const trace = simulate(analysis);
  check(trace.steps.length > 8, `${language.id}: trace steps`);
  check(trace.complete === true, `${language.id}: trace should complete`);
  check(trace.output === EXPECTED_OUTPUT[language.id], `${language.id}: expected sample output`);
  check(trace.warnings.length === 0, `${language.id}: no trace warnings`);
  check(trace.events.length > 0, `${language.id}: trace events`);
  check(trace.steps.at(-1).kind === 'end', `${language.id}: final step`);

  const guide = buildGuide(analysis, trace);
  guide.sourceLineCount = analysis.lineCount;
  check(guide.overview.paragraphs.length >= 2, `${language.id}: overview paragraphs`);
  check(guide.walkthrough.length >= 3, `${language.id}: walkthrough steps`);
  check(guide.lineNotes.length >= 5, `${language.id}: line notes`);
  check(guide.concepts.length >= 4, `${language.id}: concepts`);
  check(guide.watchOuts.length >= 1, `${language.id}: watch-outs`);
  check(guide.quiz.length >= 1, `${language.id}: quiz`);
  check(guide.readingMinutes >= 1, `${language.id}: reading time`);
  check(guide.lineNotes.every((note) => note.line >= 1 && note.line <= analysis.lineCount), `${language.id}: valid note lines`);
  check(guide.summary.includes(language.name), `${language.id}: summary names the language`);

  const syntaxTree = buildSyntaxTree(analysis);
  check(syntaxTree.root.type === 'Program', `${language.id}: syntax tree root`);
  check(syntaxTree.count > 10, `${language.id}: syntax tree size`);

  const foci = getFlowFoci(analysis);
  check(foci.length >= 1, `${language.id}: flow focus options`);
  if (analysis.entry.kind === 'function') {
    check(foci[0].id === `function:${analysis.entry.node.id}`, `${language.id}: entry function listed first`);
  } else {
    check(foci[0].id === 'program', `${language.id}: program focus listed first`);
  }

  const markdown = guideToMarkdown(guide, analysis, trace, 'Flowchart');
  check(markdown.includes('## Source'), `${language.id}: markdown source`);
  check(markdown.includes('## Line by line'), `${language.id}: markdown notes`);
  check(markdown.includes(language.name), `${language.id}: markdown language`);

  const exported = guideToExportData(guide, analysis, trace, { modeName: 'Flowchart' });
  check(exported.trace.steps.length === trace.steps.length, `${language.id}: export trace steps`);
  const serialised = JSON.stringify(exported);
  check(serialised.length > 100, `${language.id}: export serialises`);
  check(!serialised.includes('apiKey'), `${language.id}: no API key in export`);
  check(exported.source === language.sample, `${language.id}: export source`);
}

// Parser / explanation guardrails
const js = LANGUAGES.find((language) => language.id === 'javascript');
const jsAnalysis = analyzeSource(js.sample, js);
const jsTrace = simulate(jsAnalysis);
const jsGuide = buildGuide(jsAnalysis, jsTrace);
check(jsAnalysis.assignments.some((assignment) => assignment.target === 'total' && assignment.dependencies.includes('total')), 'compound assignment records its previous value');
check(jsGuide.lineNotes.some((note) => note.line === 12), 'loop body has a line note');
check(jsTrace.events.some((event) => event.target === 'total' && event.kind === 'assignment'), 'trace records accumulator updates');
check(jsTrace.events.some((event) => event.kind === 'parameter' && event.scope === 'applyDiscount'), 'trace records function parameters');

// Expression / AI configuration guardrails
const parsed = parseAIResponse('```json\n{"summary":"ok","overview":{"paragraphs":[],"mentalModel":{}},"walkthrough":[],"lineNotes":[],"concepts":[],"watchOuts":[],"quiz":[]}\n```');
check(parsed.summary === 'ok', 'AI JSON parser strips fences');
assert.throws(() => parseAIResponse('not json'), /structured guide format|JSON response/i);
check(isAIConfigured(normaliseAISettings({ provider: 'openai' })) === false, 'default hosted endpoint is not considered configured without a key');
check(isAIConfigured(normaliseAISettings({
  provider: 'openai',
  baseUrl: 'http://127.0.0.1:11434/v1',
  model: 'llama3.1',
  apiKey: ''
})) === true, 'local no-key OpenAI-compatible endpoint is allowed');
check(isAIConfigured(normaliseAISettings({
  provider: 'anthropic',
  apiKey: 'test-key',
  model: 'claude-test'
})) === true, 'Anthropic with key is configured');

// Provider catalog and current default models.
check(AI_PROVIDERS.length === 5, 'five providers are exposed');
check(AI_PROVIDERS.map((provider) => provider.id).join(',') === 'openai,deepseek,grok,anthropic,gemini', 'provider order is stable');
const expectedDefaults = {
  openai: 'gpt-6.1-terra',
  deepseek: 'deepseek-flash',
  grok: 'grok-4.7',
  anthropic: 'claude-fable-5-2',
  gemini: 'gemini-4-hydrogen'
};
for (const [providerId, model] of Object.entries(expectedDefaults)) {
  check(getProvider(providerId).defaultModel === model, `${providerId}: latest default model is ${model}`);
  check(normaliseAISettings({ provider: providerId }).model === model, `${providerId}: settings inherit its default model`);
}
for (const providerId of ['deepseek', 'grok']) {
  check(isAIConfigured(normaliseAISettings({ provider: providerId })) === false, `${providerId}: requires a key by default`);
  check(isAIConfigured(normaliseAISettings({
    provider: providerId,
    apiKey: 'test-key'
  })) === true, `${providerId}: configured with a key`);
}
check(getProvider('deepseek').defaultBaseUrl === 'https://api.deepseek.com/v1', 'DeepSeek base URL');
check(getProvider('grok').defaultBaseUrl === 'https://api.x.ai/v1', 'Grok base URL');

// Stock defaults from the previous release migrate; custom overrides do not.
check(normaliseAISettings({
  provider: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini'
}).model === 'gpt-6.1-terra', 'legacy OpenAI stock default migrates');
check(normaliseAISettings({
  provider: 'openai',
  baseUrl: 'https://gateway.example/v1',
  model: 'gpt-4o-mini'
}).model === 'gpt-4o-mini', 'custom OpenAI model choice is preserved');
check(normaliseAISettings({
  provider: 'anthropic',
  baseUrl: 'https://api.anthropic.com',
  model: 'claude-3-5-sonnet-latest'
}).model === 'claude-fable-5-2', 'legacy Anthropic stock default migrates');

console.log(`All core checks passed (${checks} assertions).`);
