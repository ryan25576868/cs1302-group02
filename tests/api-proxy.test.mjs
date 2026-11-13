/**
 * Integration test for Prism's local AI proxy adapters.
 * Assumes the app server is running (npm start) on the default port or PRISM_URL.
 */
import http from 'node:http';
import assert from 'node:assert/strict';

const PRISM = process.env.PRISM_URL || 'http://127.0.0.1:4173';
const ports = { openai: 9661, anthropic: 9662, gemini: 9663 };
const observed = [];

function startServer(port, handler) {
  return new Promise((resolve) => {
    const server = http.createServer(async (req, res) => {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const raw = Buffer.concat(chunks).toString('utf8');
      let body = {};
      try { body = raw ? JSON.parse(raw) : {}; } catch { body = {}; }
      observed.push({ port, path: req.url, headers: req.headers, body });
      handler(req, res, body);
    });
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

const servers = await Promise.all([
  startServer(ports.openai, (req, res) => {
    if (req.url.includes('error-path')) {
      res.writeHead(401, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: { message: 'Bad demo key sk-secret-demo-value' } }));
      return;
    }
    if (!req.headers.authorization?.startsWith('Bearer ')) {
      res.writeHead(401, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: { message: 'Missing auth.' } }));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      choices: [{ message: { role: 'assistant', content: 'OPENAI_OK' } }],
      usage: { prompt_tokens: 12, completion_tokens: 2 }
    }));
  }),
  startServer(ports.anthropic, (req, res, body) => {
    if (req.headers['x-api-key'] !== 'anthropic-test-key' || !req.headers['anthropic-version']) {
      res.writeHead(401, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: { message: 'Missing Anthropic headers.' } }));
      return;
    }
    if (body.system !== 'system prompt') {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: { message: 'Missing system prompt.' } }));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      content: [{ type: 'text', text: 'ANTHROPIC_OK' }],
      usage: { input_tokens: 8, output_tokens: 2 }
    }));
  }),
  startServer(ports.gemini, (req, res) => {
    if (!req.url.includes('key=gemini-test-key')) {
      res.writeHead(401, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: { message: 'Missing query key.' } }));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      candidates: [{
        content: { parts: [{ text: 'private scratchpad', thought: true }, { text: 'GEMINI_OK' }] },
        finishReason: 'STOP'
      }],
      usageMetadata: { promptTokenCount: 9, candidatesTokenCount: 2 }
    }));
  })
]);

async function callProxy(payload) {
  const response = await fetch(`${PRISM}/api/ai`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  return { status: response.status, data };
}

try {
  const health = await (await fetch(`${PRISM}/api/health`)).json();
  assert.equal(health.ok, true);
  assert.equal(health.app, 'prism');

  const openai = await callProxy({
    provider: 'openai',
    baseUrl: `http://127.0.0.1:${ports.openai}/v1`,
    model: 'mock-openai',
    apiKey: 'openai-test-key',
    system: 'system prompt',
    messages: [{ role: 'user', content: 'Hello' }],
    maxTokens: 50,
    temperature: 0.2
  });
  assert.equal(openai.status, 200, JSON.stringify(openai));
  assert.equal(openai.data.text, 'OPENAI_OK');
  assert.equal(openai.data.provider, 'openai');

  const deepseek = await callProxy({
    provider: 'deepseek',
    baseUrl: `http://127.0.0.1:${ports.openai}/v1`,
    model: 'deepseek-flash',
    apiKey: 'deepseek-test-key',
    system: 'system prompt',
    messages: [{ role: 'user', content: 'Hello' }],
    maxTokens: 50
  });
  assert.equal(deepseek.status, 200, JSON.stringify(deepseek));
  assert.equal(deepseek.data.text, 'OPENAI_OK');
  assert.equal(deepseek.data.provider, 'deepseek');

  const grok = await callProxy({
    provider: 'grok',
    baseUrl: `http://127.0.0.1:${ports.openai}/v1`,
    model: 'grok-4.7',
    apiKey: 'grok-test-key',
    system: 'system prompt',
    messages: [{ role: 'user', content: 'Hello' }],
    maxTokens: 50
  });
  assert.equal(grok.status, 200, JSON.stringify(grok));
  assert.equal(grok.data.text, 'OPENAI_OK');
  assert.equal(grok.data.provider, 'grok');

  const gpt6 = await callProxy({
    provider: 'openai',
    baseUrl: `http://127.0.0.1:${ports.openai}/v1`,
    model: 'gpt-6.1-terra',
    apiKey: 'openai-test-key',
    system: 'system prompt',
    messages: [{ role: 'user', content: 'Hello' }],
    maxTokens: 200,
    temperature: 0.2
  });
  assert.equal(gpt6.status, 200, JSON.stringify(gpt6));
  const gpt6Request = [...observed].reverse().find((entry) => entry.body.model === 'gpt-6.1-terra');
  assert.ok(gpt6Request, 'GPT-6 request reached the mock provider');
  assert.equal(gpt6Request.body.max_completion_tokens, 200);
  assert.equal(gpt6Request.body.max_tokens, undefined);
  assert.equal(gpt6Request.body.temperature, undefined);
  assert.equal(gpt6Request.body.messages[0].role, 'developer');

  const anthropic = await callProxy({
    provider: 'anthropic',
    baseUrl: `http://127.0.0.1:${ports.anthropic}`,
    model: 'mock-anthropic',
    apiKey: 'anthropic-test-key',
    system: 'system prompt',
    messages: [{ role: 'user', content: 'Hello' }],
    maxTokens: 50
  });
  assert.equal(anthropic.status, 200, JSON.stringify(anthropic));
  assert.equal(anthropic.data.text, 'ANTHROPIC_OK');

  const fable = await callProxy({
    provider: 'anthropic',
    baseUrl: `http://127.0.0.1:${ports.anthropic}`,
    model: 'claude-fable-5-2',
    apiKey: 'anthropic-test-key',
    system: 'system prompt',
    messages: [{ role: 'user', content: 'Hello' }],
    maxTokens: 200,
    temperature: 0.2
  });
  assert.equal(fable.status, 200, JSON.stringify(fable));
  const fableRequest = [...observed].reverse().find((entry) => entry.body.model === 'claude-fable-5-2');
  assert.ok(fableRequest, 'Fable request reached the mock provider');
  assert.equal(fableRequest.body.temperature, undefined);
  assert.equal(fableRequest.body.max_tokens, 200);

  const gemini = await callProxy({
    provider: 'gemini',
    baseUrl: `http://127.0.0.1:${ports.gemini}`,
    model: 'gemini-mock',
    apiKey: 'gemini-test-key',
    system: 'system prompt',
    messages: [{ role: 'user', content: 'Hello' }],
    maxTokens: 50
  });
  assert.equal(gemini.status, 200, JSON.stringify(gemini));
  assert.equal(gemini.data.text, 'GEMINI_OK');

  const error = await callProxy({
    provider: 'openai',
    baseUrl: `http://127.0.0.1:${ports.openai}/error-path`,
    model: 'mock-error',
    apiKey: 'sk-secret-demo-value',
    messages: [{ role: 'user', content: 'Trigger an error' }]
  });
  assert.equal(error.status, 502, JSON.stringify(error));
  assert.match(error.data.error, /Bad demo key/);
  assert.ok(!JSON.stringify(error.data).includes('sk-secret-demo-value'), 'The API key must be redacted from error responses.');

  const validation = await callProxy({ provider: 'openai', messages: [] });
  assert.equal(validation.status, 400, JSON.stringify(validation));

  const unsupported = await callProxy({
    provider: 'unknown-provider',
    baseUrl: 'http://127.0.0.1:9661/v1',
    model: 'test',
    messages: [{ role: 'user', content: 'Hello' }]
  });
  assert.equal(unsupported.status, 400, JSON.stringify(unsupported));

  console.log('AI proxy tests passed');
  console.log('  OpenAI GPT-6 adapter & parameter rules: ok');
  console.log('  DeepSeek adapter: ok');
  console.log('  xAI Grok adapter: ok');
  console.log('  Anthropic adapter & Fable sampling rules: ok');
  console.log('  Google Gemini adapter: ok');
  console.log('  Provider errors & key redaction: ok');
  console.log('  Request validation: ok');
  console.log('Observed requests:', observed.map((entry) => `${entry.port}${entry.path}`));
} finally {
  servers.forEach((server) => server.close());
}
