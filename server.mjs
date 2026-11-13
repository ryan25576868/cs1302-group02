#!/usr/bin/env node
/**
 * Prism's tiny local server.
 *
 * Responsibilities:
 *   1. Serve the dependency-free static app.
 *   2. Provide a thin, stateless proxy for the AI provider chosen by the user.
 *
 * The proxy exists because most AI APIs do not allow direct browser requests
 * (CORS), not because Prism wants to keep your key. The key lives in the browser
 * and is forwarded only for the request you initiate. Nothing is persisted here.
 */

import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const HOST = process.env.HOST || '127.0.0.1';
const PORT = Number(process.env.PORT || 4173);
const MAX_BODY_BYTES = 1_500_000;
const AI_TIMEOUT_MS = 120_000;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8'
};

const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url || '/', `http://${request.headers.host || `${HOST}:${PORT}`}`);

    if (url.pathname === '/api/health' && request.method === 'GET') {
      return json(response, 200, { ok: true, app: 'prism', version: '1.0.0', proxy: true });
    }

    if (url.pathname === '/api/ai' && request.method === 'POST') {
      return handleAI(request, response);
    }

    if (url.pathname.startsWith('/api/')) {
      return json(response, 404, { error: 'Unknown API route.' });
    }

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      response.writeHead(405, { Allow: 'GET, HEAD' });
      response.end('Method not allowed');
      return;
    }

    await serveStatic(url.pathname, request, response);
  } catch (error) {
    console.error('[prism] request failed:', friendlyError(error));
    if (!response.headersSent) json(response, 500, { error: 'The local server could not complete this request.' });
    else response.end();
  }
});

async function serveStatic(pathname, request, response) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    response.writeHead(400);
    response.end('Bad path');
    return;
  }
  const relative = decoded === '/' ? 'index.html' : decoded.replace(/^\/+/, '');
  const candidate = path.resolve(ROOT, relative);
  if (candidate !== ROOT && !candidate.startsWith(`${ROOT}${path.sep}`)) {
    response.writeHead(403);
    response.end('Forbidden');
    return;
  }
  let target = candidate;
  try {
    const info = await stat(target);
    if (info.isDirectory()) target = path.join(target, 'index.html');
  } catch {
    if (!path.extname(relative)) {
      target = path.join(ROOT, 'index.html');
    } else {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Not found');
      return;
    }
  }
  let body;
  try {
    body = await readFile(target);
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('Not found');
    return;
  }
  const ext = path.extname(target).toLowerCase();
  response.writeHead(200, {
    'Content-Type': MIME[ext] || 'application/octet-stream',
    'Content-Length': body.byteLength,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy': [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self'",
      "connect-src 'self'",
      "object-src 'none'",
      "base-uri 'none'",
      "form-action 'self'",
      "frame-ancestors 'none'"
    ].join('; ')
  });
  if (request.method === 'HEAD') response.end();
  else response.end(body);
}

async function handleAI(request, response) {
  let payload;
  try {
    payload = await readJSONBody(request);
  } catch (error) {
    return json(response, error.statusCode || 400, { error: friendlyError(error) });
  }

  const provider = String(payload.provider || 'openai');
  if (!['openai', 'deepseek', 'grok', 'anthropic', 'gemini'].includes(provider)) {
    return json(response, 400, { error: 'Unsupported AI provider. Choose openai, deepseek, grok, anthropic, or gemini.' });
  }

  const model = stringValue(payload.model).trim();
  if (!model) return json(response, 400, { error: 'A model name is required.' });
  const baseUrl = stringValue(payload.baseUrl).trim();
  if (!baseUrl) return json(response, 400, { error: 'A provider base URL is required.' });
  let parsedBase;
  try {
    parsedBase = new URL(baseUrl);
  } catch {
    return json(response, 400, { error: 'The provider base URL is not a valid URL.' });
  }
  if (!['http:', 'https:'].includes(parsedBase.protocol)) {
    return json(response, 400, { error: 'The provider base URL must start with http:// or https://.' });
  }

  const apiKey = stringValue(payload.apiKey);
  const messages = Array.isArray(payload.messages)
    ? payload.messages
        .filter((message) => message && ['user', 'assistant'].includes(message.role) && typeof message.content === 'string')
        .slice(-20)
        .map((message) => ({ role: message.role, content: limit(message.content, 60_000) }))
    : [];
  if (!messages.length) return json(response, 400, { error: 'At least one message is required.' });

  const system = limit(stringValue(payload.system), 30_000);
  const temperature = clampNumber(payload.temperature, 0, 1, 0.3);
  const maxTokens = Math.round(clampNumber(payload.maxTokens, 64, 8000, 2600));

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), AI_TIMEOUT_MS);
  const started = Date.now();

  try {
    let result;
    if (provider === 'anthropic') {
      result = await callAnthropic({ baseUrl, apiKey, model, system, messages, temperature, maxTokens, signal: controller.signal });
    } else if (provider === 'gemini') {
      result = await callGemini({ baseUrl, apiKey, model, system, messages, temperature, maxTokens, signal: controller.signal });
    } else {
      result = await callOpenAICompatible({ provider, baseUrl, apiKey, model, system, messages, temperature, maxTokens, signal: controller.signal });
    }
    const elapsed = Date.now() - started;
    console.log(`[prism] AI request complete · ${provider} · ${model} · ${elapsed}ms`);
    return json(response, 200, {
      text: result.text,
      provider,
      model,
      usage: result.usage ?? null,
      elapsedMs: elapsed
    });
  } catch (error) {
    const status = error.status && error.status >= 400 && error.status < 600 ? error.status : 502;
    const message = redact(friendlyError(error), apiKey);
    console.warn(`[prism] AI request failed · ${provider} · ${status} · ${message}`);
    return json(response, 502, { error: message });
  } finally {
    clearTimeout(timeout);
  }
}

async function callOpenAICompatible({ provider, baseUrl, apiKey, model, system, messages, temperature, maxTokens, signal }) {
  const endpoint = openAIEndpoint(baseUrl);
  // GPT-6 models use developer messages, max_completion_tokens, and choose
  // their own sampling unless reasoning_effort is explicitly "none".
  const usesGPT6Rules = provider === 'openai' && /^gpt-6(?:[.-]|$)/i.test(model);
  const requestMessages = system
    ? [{ role: usesGPT6Rules ? 'developer' : 'system', content: system }, ...messages]
    : messages;
  const body = {
    model,
    messages: requestMessages,
    stream: false
  };
  if (usesGPT6Rules) {
    body.max_completion_tokens = maxTokens;
  } else {
    body.temperature = temperature;
    body.max_tokens = maxTokens;
  }
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  const data = await fetchProvider(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal
  });
  const text = extractOpenAIText(data);
  if (!text) throw providerError('The provider returned an empty response.', 'empty_response');
  return { text, usage: data.usage ?? null };
}

async function callAnthropic({ baseUrl, apiKey, model, system, messages, temperature, maxTokens, signal }) {
  if (!apiKey) throw providerError('Anthropic requires an API key.', 'missing_key');
  const endpoint = appendPath(baseUrl, 'v1/messages');
  // Fable and Mythos 5.x only allow their own sampling settings.
  const supportsCustomSampling = !/^claude-(?:fable|mythos)-/i.test(model);
  const requestBody = {
    model,
    max_tokens: maxTokens,
    system: system || undefined,
    messages: messages.map((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: message.content
    }))
  };
  if (supportsCustomSampling) requestBody.temperature = temperature;
  const data = await fetchProvider(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01'
    },
    body: JSON.stringify(requestBody),
    signal
  });
  const parts = Array.isArray(data.content) ? data.content : [];
  const text = parts.filter((part) => part?.type === 'text').map((part) => part.text).join('\n').trim();
  if (!text) throw providerError('Anthropic returned an empty response.', 'empty_response');
  return { text, usage: data.usage ?? null };
}

async function callGemini({ baseUrl, apiKey, model, system, messages, temperature, maxTokens, signal }) {
  if (!apiKey) throw providerError('Google Gemini requires an API key.', 'missing_key');
  const base = baseUrl.replace(/\/+$/, '');
  const endpoint = base.includes(':generateContent')
    ? base
    : `${base}/v1beta/models/${encodeURIComponent(model)}:generateContent${apiKey ? `?key=${encodeURIComponent(apiKey)}` : ''}`;
  const contents = messages.map((message) => ({
    role: message.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: message.content }]
  }));
  const body = {
    contents,
    generationConfig: {
      temperature,
      maxOutputTokens: maxTokens
    }
  };
  if (system) body.systemInstruction = { parts: [{ text: system }] };
  const data = await fetchProvider(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal
  });
  const candidate = data.candidates?.[0];
  // Gemini 4 thinking models may return their scratchpad alongside the answer.
  // Only user-visible parts belong in the guide response.
  const text = (candidate?.content?.parts ?? [])
    .filter((part) => !part?.thought)
    .map((part) => part.text ?? '')
    .join('')
    .trim();
  if (!text) {
    const blockReason = data.promptFeedback?.blockReason
      || (candidate?.finishReason && candidate.finishReason !== 'STOP' ? candidate.finishReason : '');
    throw providerError(blockReason ? `Gemini blocked the request: ${blockReason}.` : 'Gemini returned an empty response.', 'empty_response');
  }
  return { text, usage: data.usageMetadata ?? null };
}

async function fetchProvider(endpoint, options) {
  let response;
  try {
    response = await fetch(endpoint, options);
  } catch (error) {
    if (error.name === 'AbortError') {
      throw providerError('The AI provider took too long to respond (120 second limit).', 'timeout');
    }
    throw providerError(
      `Could not reach the provider at ${safeHost(endpoint)}. Check the base URL and your network connection.`,
      'network_error'
    );
  }
  const raw = await response.text();
  let data;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    throw providerError(
      response.ok
        ? 'The provider returned a response that was not valid JSON.'
        : `The provider returned HTTP ${response.status} with a non-JSON error body.`,
      'invalid_json'
    );
  }
  if (!response.ok) {
    const message = extractProviderError(data) || `The provider returned HTTP ${response.status}.`;
    const error = providerError(message, 'provider_error');
    error.status = response.status;
    throw error;
  }
  return data;
}

function extractOpenAIText(data) {
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content === 'string') return content.trim();
  if (Array.isArray(content)) {
    return content.map((part) => (typeof part === 'string' ? part : part?.text ?? '')).join('').trim();
  }
  // Some OpenAI-compatible servers put text in a non-streaming convenience field.
  if (typeof data?.choices?.[0]?.text === 'string') return data.choices[0].text.trim();
  return '';
}

function extractProviderError(data) {
  if (!data) return '';
  if (typeof data.error === 'string') return data.error;
  if (typeof data.error?.message === 'string') return data.error.message;
  if (typeof data.message === 'string') return data.message;
  if (Array.isArray(data.error?.errors) && data.error.errors[0]?.message) return data.error.errors[0].message;
  if (Array.isArray(data.errors) && data.errors[0]?.message) return data.errors[0].message;
  return '';
}

function openAIEndpoint(baseUrl) {
  const clean = baseUrl.replace(/\/+$/, '');
  if (/\/chat\/completions$/.test(clean)) return clean;
  try {
    const url = new URL(clean);
    if (url.pathname === '/' || !url.pathname) {
      return `${clean}${url.hostname === 'api.openai.com' ? '/v1/chat/completions' : '/chat/completions'}`;
    }
    return `${clean}/chat/completions`;
  } catch {
    return `${clean}/chat/completions`;
  }
}

function appendPath(baseUrl, suffix) {
  const clean = baseUrl.replace(/\/+$/, '');
  if (clean.endsWith(`/${suffix}`)) return clean;
  if (clean.endsWith('/v1') && suffix.startsWith('v1/')) return `${clean}/${suffix.slice(3)}`;
  return `${clean}/${suffix}`;
}

function safeHost(endpoint) {
  try {
    return new URL(endpoint).host;
  } catch {
    return 'the configured endpoint';
  }
}

function providerError(message, code) {
  const error = new Error(message);
  error.code = code;
  return error;
}

async function readJSONBody(request) {
  let size = 0;
  const chunks = [];
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      const error = new Error('Request body is too large.');
      error.statusCode = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  if (!chunks.length) {
    const error = new Error('Request body is required.');
    error.statusCode = 400;
    throw error;
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    const error = new Error('Request body must be valid JSON.');
    error.statusCode = 400;
    throw error;
  }
}

function json(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  });
  response.end(body);
}

function stringValue(value) {
  return typeof value === 'string' ? value : '';
}

function limit(value, max) {
  return String(value ?? '').slice(0, max);
}

function clampNumber(value, min, max, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}

function redact(text, secret) {
  let safe = String(text ?? '');
  if (secret) safe = safe.split(secret).join('[redacted]');
  safe = safe.replace(/Bearer\s+[A-Za-z0-9._~+/=-]{12,}/gi, 'Bearer [redacted]');
  safe = safe.replace(/[?&]key=[^&\s]+/gi, '?key=[redacted]');
  return safe.slice(0, 1000);
}

function friendlyError(error) {
  if (!error) return 'Unknown error.';
  if (error.code === 'ECONNREFUSED') return 'The provider refused the connection.';
  const message = error instanceof Error ? error.message : String(error);
  return redact(message);
}

server.listen(PORT, HOST, () => {
  console.log('');
  console.log('  prism · visual code lab');
  console.log(`  Local app:  http://${HOST}:${PORT}`);
  console.log(`  AI proxy:   http://${HOST}:${PORT}/api/ai`);
  console.log('  Press Ctrl+C to stop.');
  console.log('');
});

server.on('error', (error) => {
  if (error.code === 'EADDRINUSE') {
    console.error(`Port ${PORT} is already in use. Set PORT to another value, for example: PORT=4180 node server.mjs`);
  } else {
    console.error('[prism] server error:', friendlyError(error));
  }
  process.exitCode = 1;
});
