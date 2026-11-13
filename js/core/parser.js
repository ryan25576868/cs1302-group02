/**
 * Lightweight structural parser.
 *
 * This deliberately stops short of a formal compiler grammar. It recognises the
 * constructs beginners use most often — declarations, assignments, conditions,
 * loops, functions, classes, returns, and calls — while keeping every original
 * line number so the visual layer can point back at real code.
 */

import { lex, syntaxTokens } from './lexer.js';

const CONTROL_KEYWORDS = new Set(['if', 'for', 'while', 'switch', 'catch', 'try', 'do', 'else', 'finally']);
const CLASS_KEYWORDS = new Set(['class', 'interface', 'enum', 'record', 'struct', 'union', 'namespace']);
const DECLARATION_MODIFIERS = new Set([
  'public', 'private', 'protected', 'static', 'final', 'abstract', 'synchronized',
  'native', 'strictfp', 'default', 'export', 'async', 'declare', 'readonly'
]);
const EXPRESSION_PREFIXES = new Set(['return', 'new', 'throw', 'delete', 'typeof', 'await', 'yield']);
const CONTROL_FLOW_ACTIONS = new Set(['return', 'break', 'continue', 'throw', 'yield']);

function makeBlock(startLine, endLine, children = []) {
  return {
    type: 'block',
    startLine,
    endLine,
    children
  };
}

export function parseProgram(source, language) {
  const text = String(source ?? '').replace(/\r\n?/g, '\n');
  const lineCount = text.split('\n').length;
  const diagnostics = [];
  const root = {
    type: 'program',
    startLine: 1,
    endLine: lineCount,
    body: makeBlock(1, lineCount, []),
    header: 'Program',
    language: language.name,
    parseMode: language.family === 'python' ? 'indentation' : 'braces',
    diagnostics
  };

  if (language.family === 'python') {
    parsePythonProgram(root, text, language, diagnostics);
  } else {
    parseBraceProgram(root, text, language, diagnostics);
  }

  assignNodeIds(root);
  return { root, diagnostics, lineCount };
}

/* -------------------------------------------------------------------------- */
/* C-family: JavaScript, TypeScript, Java, C, C++                             */
/* -------------------------------------------------------------------------- */

function parseBraceProgram(root, source, language, diagnostics) {
  const tokens = syntaxTokens(source, language);
  const cursor = new TokenCursor(tokens, source, language, diagnostics);
  root.body = cursor.parseBlockBody({ openBrace: false, startLine: 1, endLine: root.endLine });
  if (cursor.index < tokens.length) {
    diagnostics.push({
      severity: 'warning',
      message: 'Some code could not be placed in the structure tree.',
      line: tokens[cursor.index]?.line ?? root.endLine
    });
  }
  root.body.startLine = 1;
  root.body.endLine = root.endLine;
}

class TokenCursor {
  constructor(tokens, source, language, diagnostics) {
    this.tokens = tokens;
    this.source = source;
    this.language = language;
    this.diagnostics = diagnostics;
    this.index = 0;
  }

  peek(offset = 0) {
    return this.tokens[this.index + offset];
  }

  next() {
    const token = this.tokens[this.index];
    this.index += 1;
    return token;
  }

  isEof() {
    return this.index >= this.tokens.length;
  }

  skipSemicolons() {
    while (this.peek()?.value === ';') this.index += 1;
  }

  parseBlockBody({ openBrace, startLine, endLine }) {
    const children = [];
    if (openBrace) {
      if (this.peek()?.value !== '{') {
        this.diagnostics.push({ severity: 'warning', message: 'Expected a block opening.', line: startLine });
        return makeBlock(startLine, startLine, children);
      }
      this.next();
    }

    while (!this.isEof()) {
      this.skipSemicolons();
      const token = this.peek();
      if (!token) break;
      if (openBrace && token.value === '}') break;
      if (!openBrace && token.value === '}') {
        // Stray closing brace at the top level. Skip it so parsing can continue.
        this.next();
        continue;
      }
      const before = this.index;
      const node = this.parseStatement();
      if (node) children.push(node);
      if (this.index === before) this.index += 1;
    }

    let closeLine = children.at(-1)?.endLine ?? startLine;
    if (openBrace && this.peek()?.value === '}') {
      closeLine = this.next().value === '}' ? this.tokens[this.index - 1].endLine : closeLine;
    }
    return makeBlock(startLine, Math.max(endLine ?? startLine, closeLine), children);
  }

  parseStatement() {
    const startToken = this.peek();
    if (!startToken) return null;
    const word = startToken.value;

    if (word === 'if') return this.parseIf();
    if (word === 'for') return this.parseFor();
    if (word === 'while') return this.parseWhile();
    if (word === 'do') return this.parseDoWhile();
    if (word === 'switch') return this.parseSwitch();
    if (word === 'try') return this.parseTry();
    if (word === 'else' || word === 'catch' || word === 'finally') {
      // An orphaned keyword is unusual; skip it rather than looping forever.
      this.next();
      return null;
    }

    const shape = this.scanStatementShape();
    if (shape.kind === 'brace') {
      const header = this.tokens.slice(this.index, shape.boundary);
      if (looksLikeClassHeader(header, this.language)) {
        return this.parseClass(shape.boundary);
      }
      if (looksLikeFunctionHeader(header, this.language)) {
        return this.parseFunction(shape.boundary);
      }
    }

    if (startToken.value === '{') {
      return this.parseStandaloneBlock();
    }

    return this.parseAction();
  }

  scanStatementShape() {
    let paren = 0;
    let bracket = 0;
    for (let i = this.index; i < this.tokens.length; i += 1) {
      const token = this.tokens[i];
      if (token.value === '(') paren += 1;
      else if (token.value === ')') paren = Math.max(0, paren - 1);
      else if (token.value === '[') bracket += 1;
      else if (token.value === ']') bracket = Math.max(0, bracket - 1);
      else if (paren === 0 && bracket === 0) {
        if (token.value === ';') return { kind: 'simple', boundary: i };
        if (token.value === '{') return { kind: 'brace', boundary: i };
        if (token.value === '}') return { kind: 'boundary', boundary: i };
      }
    }
    return { kind: 'eof', boundary: this.tokens.length - 1 };
  }

  findMatching(openIndex) {
    const open = this.tokens[openIndex]?.value;
    const close = open === '(' ? ')' : open === '[' ? ']' : open === '{' ? '}' : null;
    if (!close) return -1;
    let depth = 0;
    for (let i = openIndex; i < this.tokens.length; i += 1) {
      if (this.tokens[i].value === open) depth += 1;
      else if (this.tokens[i].value === close) {
        depth -= 1;
        if (depth === 0) return i;
      }
    }
    return -1;
  }

  consumeParenthesised() {
    const open = this.peek();
    if (open?.value !== '(') return null;
    const openIndex = this.index;
    const closeIndex = this.findMatching(openIndex);
    if (closeIndex === -1) {
      this.diagnostics.push({ severity: 'warning', message: 'Found an unclosed parenthesis.', line: open.line });
      this.index += 1;
      return null;
    }
    const raw = this.source.slice(this.tokens[openIndex].end, this.tokens[closeIndex].start).trim();
    const closeToken = this.tokens[closeIndex];
    this.index = closeIndex + 1;
    return {
      raw,
      openIndex,
      closeIndex,
      openLine: open.line,
      closeLine: closeToken.line
    };
  }

  parseBody() {
    if (this.isEof()) {
      return makeBlock(this.tokens.at(-1)?.endLine ?? 1, this.tokens.at(-1)?.endLine ?? 1, []);
    }
    if (this.peek()?.value === '{') {
      return this.parseBlockBody({ openBrace: true, startLine: this.peek().line, endLine: null });
    }
    if (this.peek()?.value === ';') {
      const line = this.next().line;
      return makeBlock(line, line, []);
    }
    const before = this.index;
    const node = this.parseStatement();
    if (!node) {
      const line = this.peek()?.line ?? this.tokens.at(-1)?.endLine ?? 1;
      return makeBlock(line, line, []);
    }
    if (this.index === before) this.index += 1;
    return makeBlock(node.startLine, node.endLine, [node]);
  }

  parseIf() {
    const start = this.next();
    const condition = this.consumeParenthesised();
    if (!condition) {
      return this.fallbackAction(start.line);
    }
    const consequent = this.parseBody();
    let alternate = null;
    if (this.peek()?.value === 'else') {
      this.next();
      if (this.peek()?.value === 'if') {
        const nested = this.parseIf();
        alternate = makeBlock(nested.startLine, nested.endLine, nested ? [nested] : []);
      } else {
        alternate = this.parseBody();
      }
    }
    const endLine = (alternate ?? consequent).endLine;
    return {
      type: 'if',
      startLine: start.line,
      endLine,
      header: `if (${condition.raw})`,
      condition: condition.raw,
      consequent,
      alternate,
      hasElse: !!alternate,
      keyword: 'if'
    };
  }

  parseFor() {
    const start = this.next();
    const header = this.consumeParenthesised();
    if (!header) return this.fallbackAction(start.line);
    const body = this.parseBody();
    return {
      type: 'for',
      startLine: start.line,
      endLine: body.endLine,
      header: `for (${header.raw})`,
      loopHeader: header.raw,
      body,
      keyword: 'for'
    };
  }

  parseWhile() {
    const start = this.next();
    const header = this.consumeParenthesised();
    if (!header) return this.fallbackAction(start.line);
    const body = this.parseBody();
    return {
      type: 'while',
      startLine: start.line,
      endLine: body.endLine,
      header: `while (${header.raw})`,
      condition: header.raw,
      body,
      keyword: 'while'
    };
  }

  parseDoWhile() {
    const start = this.next();
    const body = this.parseBody();
    let condition = '';
    let endLine = body.endLine;
    if (this.peek()?.value === 'while') {
      const whileToken = this.next();
      const header = this.consumeParenthesised();
      condition = header?.raw ?? '';
      endLine = header?.closeLine ?? whileToken.line;
      if (this.peek()?.value === ';') this.next();
    }
    return {
      type: 'do',
      startLine: start.line,
      endLine,
      header: `do … while (${condition})`,
      condition,
      body,
      keyword: 'do'
    };
  }

  parseSwitch() {
    const start = this.next();
    const header = this.consumeParenthesised();
    const body = this.peek()?.value === '{'
      ? this.parseBlockBody({ openBrace: true, startLine: this.peek().line, endLine: null })
      : this.parseBody();
    return {
      type: 'switch',
      startLine: start.line,
      endLine: body.endLine,
      header: `switch (${header?.raw ?? ''})`,
      condition: header?.raw ?? '',
      body,
      keyword: 'switch'
    };
  }

  parseTry() {
    const start = this.next();
    const body = this.parseBody();
    const handlers = [];
    if (this.peek()?.value === 'catch') {
      const catchToken = this.next();
      let parameter = '';
      if (this.peek()?.value === '(') {
        parameter = this.consumeParenthesised()?.raw ?? '';
      }
      const handlerBody = this.parseBody();
      handlers.push({ type: 'catch', parameter, body: handlerBody, startLine: catchToken.line, endLine: handlerBody.endLine });
    }
    let finallyBody = null;
    if (this.peek()?.value === 'finally') {
      const token = this.next();
      finallyBody = this.parseBody();
      handlers.push({ type: 'finally', body: finallyBody, startLine: token.line, endLine: finallyBody.endLine });
    }
    let endLine = body.endLine;
    if (handlers.length) endLine = handlers.at(-1).endLine;
    return {
      type: 'try',
      startLine: start.line,
      endLine,
      header: 'try',
      body,
      handlers,
      finallyBody,
      keyword: 'try'
    };
  }

  parseFunction(braceIndex) {
    const headerTokens = this.tokens.slice(this.index, braceIndex);
    const headerStartLine = headerTokens[0]?.line ?? 1;
    const headerEndLine = headerTokens.at(-1)?.endLine ?? headerStartLine;
    const header = this.source.slice(headerTokens[0].start, headerTokens.at(-1).end).trim();
    const paramsInfo = extractBraceParams(headerTokens, this.source, this.language);
    this.index = braceIndex;
    const body = this.parseBlockBody({ openBrace: true, startLine: headerEndLine, endLine: null });
    return {
      type: 'function',
      startLine: headerStartLine,
      endLine: body.endLine,
      header,
      name: paramsInfo.name,
      params: paramsInfo.params,
      returnType: paramsInfo.returnType,
      body,
      keyword: 'function'
    };
  }

  parseClass(braceIndex) {
    const headerTokens = this.tokens.slice(this.index, braceIndex);
    const startLine = headerTokens[0]?.line ?? 1;
    const header = this.source.slice(headerTokens[0].start, headerTokens.at(-1).end).trim();
    const nameToken = headerTokens.find((token) => CLASS_KEYWORDS.has(token.value) && token !== headerTokens[0]);
    const classKeywordIndex = headerTokens.findIndex((token) => CLASS_KEYWORDS.has(token.value));
    const name = headerTokens[classKeywordIndex + 1]?.value ?? nameToken?.value ?? 'Class';
    this.index = braceIndex;
    const body = this.parseBlockBody({ openBrace: true, startLine, endLine: null });
    return {
      type: 'class',
      startLine,
      endLine: body.endLine,
      header,
      name,
      body,
      keyword: headerTokens[classKeywordIndex]?.value ?? 'class'
    };
  }

  parseStandaloneBlock() {
    const startLine = this.peek()?.line ?? 1;
    const body = this.parseBlockBody({ openBrace: true, startLine, endLine: null });
    return {
      type: 'block',
      startLine,
      endLine: body.endLine,
      header: 'Nested block',
      body
    };
  }

  parseAction() {
    const startIndex = this.index;
    const first = this.peek();
    if (!first) return null;
    let paren = 0;
    let bracket = 0;
    let brace = 0;
    let last = startIndex;
    let endIndex = null;
    let sawSemicolon = false;
    const allowASI = this.language.id === 'javascript' || this.language.id === 'typescript';

    for (let i = startIndex; i < this.tokens.length; i += 1) {
      const token = this.tokens[i];
      if (token.value === '(') paren += 1;
      else if (token.value === ')') paren = Math.max(0, paren - 1);
      else if (token.value === '[') bracket += 1;
      else if (token.value === ']') bracket = Math.max(0, bracket - 1);
      else if (token.value === '{') brace += 1;
      else if (token.value === '}') {
        if (paren === 0 && bracket === 0 && brace === 0) {
          endIndex = i - 1;
          break;
        }
        brace = Math.max(0, brace - 1);
      } else if (token.value === ';' && paren === 0 && bracket === 0 && brace === 0) {
        endIndex = i - 1;
        sawSemicolon = true;
        this.index = i + 1;
        break;
      }

      if (allowASI && i > startIndex && paren === 0 && bracket === 0 && brace === 0) {
        const previous = this.tokens[i - 1];
        const startsNewLine = token.line > previous.endLine;
        const previousCanEnd = !isContinuation(previous.value);
        const currentStartsNew = !isContinuation(token.value) && !['.', '?.', ',', ')', ']', '}', ';', '?', ':'].includes(token.value);
        if (startsNewLine && previousCanEnd && currentStartsNew) {
          endIndex = i - 1;
          break;
        }
      }

      last = i;
      if (!sawSemicolon) this.index = i + 1;
    }

    if (endIndex === null) endIndex = last;
    if (endIndex < startIndex) {
      // A stray closing brace before any tokens: consume one token to progress.
      this.index = startIndex + 1;
      return null;
    }
    const endToken = this.tokens[endIndex];
    const text = this.source.slice(first.start, endToken.end).trim();
    const kind = classifyActionKeyword(first.value);
    if (this.index <= startIndex) this.index = endIndex + 1;

    return {
      type: 'action',
      startLine: first.line,
      endLine: endToken.endLine,
      header: text,
      text,
      kind,
      rawFirst: first.value
    };
  }

  fallbackAction(line) {
    const start = this.index;
    let i = start;
    while (i < this.tokens.length && this.tokens[i].value !== ';' && this.tokens[i].value !== '}') i += 1;
    const slice = this.tokens.slice(start, Math.max(i, start + 1));
    if (this.tokens[i]?.value === ';') i += 1;
    this.index = Math.max(i, this.index + 1);
    const last = slice.at(-1);
    return {
      type: 'action',
      startLine: line,
      endLine: last?.endLine ?? line,
      header: this.source.slice(slice[0]?.start ?? 0, last?.end ?? 0).trim(),
      text: this.source.slice(slice[0]?.start ?? 0, last?.end ?? 0).trim(),
      kind: 'unknown',
      rawFirst: slice[0]?.value
    };
  }
}

function isContinuation(value) {
  return new Set([
    '+', '-', '*', '/', '%', '=', '==', '===', '!=', '!==', '<', '>', '<=', '>=',
    '&&', '||', '??', '.', '?.', ',', '(', '[', '{', '?', ':', '=>', '+=', '-=',
    '*=', '/=', '%=', '&', '|', '^', '!', '~'
  ]).has(value);
}

function classifyActionKeyword(word) {
  if (CONTROL_FLOW_ACTIONS.has(word)) return word;
  if (word === 'import' || word === 'from' || word === 'package' || word === 'using') return 'import';
  if (word === '#') return 'meta';
  return 'action';
}

function stripDeclarationModifiers(tokens) {
  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index];
    if (DECLARATION_MODIFIERS.has(token.value) || token.value === '@') {
      index += 1;
      // Skip annotation arguments such as @SuppressWarnings("unchecked").
      if (token.value === '@' && tokens[index]?.value) {
        index += 1;
        if (tokens[index]?.value === '(') {
          let depth = 0;
          while (index < tokens.length) {
            if (tokens[index].value === '(') depth += 1;
            else if (tokens[index].value === ')') {
              depth -= 1;
              if (depth === 0) {
                index += 1;
                break;
              }
            }
            index += 1;
          }
        }
      }
      continue;
    }
    break;
  }
  return index;
}

function looksLikeClassHeader(headerTokens, language) {
  const start = stripDeclarationModifiers(headerTokens);
  const first = headerTokens[start];
  if (!first) return false;
  if (!CLASS_KEYWORDS.has(first.value)) return false;
  if (first.value === 'namespace') return true;
  // Avoid treating a variable declaration like "struct Point p" as a class.
  if (language.id === 'c' && first.value === 'struct') {
    return headerTokens.slice(start + 1).every((token) => token.type !== 'identifier' || token.value === headerTokens[start + 1]?.value);
  }
  return true;
}

function looksLikeFunctionHeader(headerTokens, language) {
  if (!headerTokens.length) return false;
  const start = stripDeclarationModifiers(headerTokens);
  const first = headerTokens[start];
  if (!first) return false;
  if (CONTROL_KEYWORDS.has(first.value)) return false;
  if (CLASS_KEYWORDS.has(first.value)) return false;
  if (EXPRESSION_PREFIXES.has(first.value)) return false;

  const openIndex = headerTokens.findIndex((token) => token.value === '(');
  if (openIndex <= start) return false;
  const nameToken = headerTokens[openIndex - 1];
  if (!nameToken || (nameToken.type !== 'identifier' && nameToken.type !== 'keyword')) return false;

  let depth = 0;
  let closeIndex = -1;
  for (let i = openIndex; i < headerTokens.length; i += 1) {
    if (headerTokens[i].value === '(') depth += 1;
    else if (headerTokens[i].value === ')') {
      depth -= 1;
      if (depth === 0) {
        closeIndex = i;
        break;
      }
    }
  }

  // Assignments and arrows only disqualify a function header when they appear
  // outside the parameter list (defaults and arrow types live inside it).
  const topLevelForbidden = new Set(['=', '=>', '+=']);
  let scanDepth = 0;
  for (let i = start; i < headerTokens.length; i += 1) {
    const token = headerTokens[i];
    if (token.value === '(') scanDepth += 1;
    else if (token.value === ')') scanDepth = Math.max(0, scanDepth - 1);
    else if (scanDepth === 0 && topLevelForbidden.has(token.value)) return false;
  }

  if (closeIndex === -1) return false;
  const trailing = headerTokens.slice(closeIndex + 1);
  if (!trailing.length) return true;
  // A TypeScript return type or a C++ trailing return type is allowed.
  if (trailing[0]?.value === ':' || trailing[0]?.value === '->') return true;
  // C++ trailing qualifiers and Java throws clauses.
  const allowedTrailing = new Set(['const', 'override', 'final', 'noexcept', 'throws', 'mutable']);
  return trailing.every((token, index) => {
    if (index === 0 && allowedTrailing.has(token.value)) return true;
    if (token.type === 'identifier' || token.type === 'keyword' || token.value === '::' || token.value === '<' || token.value === '>' || token.value === ',' || token.value === '|' || token.value === '[' || token.value === ']') return true;
    return false;
  });
}

function extractBraceParams(headerTokens, source, language) {
  const openIndex = headerTokens.findIndex((token) => token.value === '(');
  if (openIndex === -1) return { name: 'function', params: [], returnType: '' };
  let depth = 0;
  let closeIndex = -1;
  for (let i = openIndex; i < headerTokens.length; i += 1) {
    if (headerTokens[i].value === '(') depth += 1;
    else if (headerTokens[i].value === ')') {
      depth -= 1;
      if (depth === 0) {
        closeIndex = i;
        break;
      }
    }
  }
  if (closeIndex === -1) return { name: 'function', params: [], returnType: '' };
  const name = headerTokens[openIndex - 1]?.value ?? 'function';
  const paramText = source.slice(headerTokens[openIndex].end, headerTokens[closeIndex].start);
  const prefixText = source.slice(headerTokens[0].start, headerTokens[openIndex - 1].start).trim();
  const params = parseParamList(paramText, language);
  return { name, params, returnType: prefixText };
}

/** Parse a comma-separated parameter list without being fooled by nesting. */
export function parseParamList(raw, language) {
  if (!raw || !raw.trim() || raw.trim() === 'void') return [];
  return splitTopLevel(raw, ',')
    .map((piece) => parseParam(piece, language))
    .filter(Boolean);
}

function parseParam(piece, language) {
  const text = piece.trim();
  if (!text) return null;
  const withoutDefault = splitTopLevelOnce(text, '=');
  const left = withoutDefault.left.trim();
  const defaultText = withoutDefault.right?.trim() ?? null;

  let tokens;
  try {
    tokens = syntaxTokens(left, language);
  } catch {
    tokens = [];
  }
  const identifiers = tokens.filter((token) => token.type === 'identifier');
  if (!identifiers.length) return null;

  let name;
  const isScriptFamily = ['javascript', 'typescript', 'python'].includes(language.id);
  if (isScriptFamily) {
    name = identifiers[0].value;
  } else {
    name = identifiers.at(-1).value;
  }
  name = name.replace(/^\.\.\./, '');

  let type = '';
  const nameToken = tokens.find((token) => token.value === name) || identifiers.find((token) => token.value === name);
  if (nameToken) {
    if (language.family === 'python') {
      const colonIndex = tokens.findIndex((token) => token.value === ':');
      if (colonIndex !== -1) {
        type = left.slice(tokens[colonIndex].end - tokens[0].start).trim();
      }
    } else if (isScriptFamily) {
      const colonIndex = tokens.findIndex((token) => token.value === ':');
      if (colonIndex !== -1) {
        type = left.slice(tokens[colonIndex].end - tokens[0].start).trim();
      }
    } else {
      const tokenIndex = tokens.indexOf(nameToken);
      type = left.slice(0, Math.max(0, tokens[tokenIndex]?.start - tokens[0].start)).trim();
      type = type.replace(/[&*]+$/, '').trim();
    }
  }

  let defaultValue = null;
  if (defaultText) {
    defaultValue = defaultText;
  } else if (/[?:]\s*$/.test(name)) {
    // Optional TypeScript parameters are handled by the tokenizer; no-op.
  }

  return { name, type, defaultValue, raw: text };
}

export function splitTopLevel(text, separator) {
  const parts = [];
  let current = '';
  let depthParen = 0;
  let depthBracket = 0;
  let depthBrace = 0;
  let quote = null;
  let escaped = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      current += ch;
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch;
      current += ch;
      continue;
    }
    if (ch === '(') depthParen += 1;
    else if (ch === ')') depthParen = Math.max(0, depthParen - 1);
    else if (ch === '[') depthBracket += 1;
    else if (ch === ']') depthBracket = Math.max(0, depthBracket - 1);
    else if (ch === '{') depthBrace += 1;
    else if (ch === '}') depthBrace = Math.max(0, depthBrace - 1);
    if (ch === separator && depthParen === 0 && depthBracket === 0 && depthBrace === 0) {
      parts.push(current);
      current = '';
      continue;
    }
    current += ch;
  }
  if (current.trim()) parts.push(current);
  return parts;
}

export function splitTopLevelOnce(text, separator) {
  let depthParen = 0;
  let depthBracket = 0;
  let depthBrace = 0;
  let quote = null;
  let escaped = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch;
      continue;
    }
    if (ch === '(') depthParen += 1;
    else if (ch === ')') depthParen = Math.max(0, depthParen - 1);
    else if (ch === '[') depthBracket += 1;
    else if (ch === ']') depthBracket = Math.max(0, depthBracket - 1);
    else if (ch === '{') depthBrace += 1;
    else if (ch === '}') depthBrace = Math.max(0, depthBrace - 1);
    if (ch === separator && depthParen === 0 && depthBracket === 0 && depthBrace === 0) {
      return { left: text.slice(0, i), right: text.slice(i + 1), found: true };
    }
  }
  return { left: text, right: null, found: false };
}

/* -------------------------------------------------------------------------- */
/* Python: indentation-based structure                                        */
/* -------------------------------------------------------------------------- */

function parsePythonProgram(root, source, language, diagnostics) {
  const lines = buildPythonLines(source, diagnostics);
  const significant = lines.filter((line) => line.code.trim());
  const baseIndent = significant.length ? Math.min(...significant.map((line) => line.indent)) : 0;
  for (const line of lines) line.indent = Math.max(0, line.indent - baseIndent);

  const parser = new PythonParser(lines, source, language, diagnostics);
  const result = parser.parseBlock(0, 0, root.endLine);
  root.body = result.block;
  root.body.startLine = 1;
  root.body.endLine = root.endLine;
}

function buildPythonLines(source, diagnostics) {
  const masked = maskPythonCommentsAndTripleStrings(source);
  const rawLines = source.split('\n');
  const maskedLines = masked.split('\n');
  return rawLines.map((raw, index) => {
    const code = maskedLines[index] ?? '';
    return {
      number: index + 1,
      raw,
      code,
      indent: pythonIndentWidth(raw),
      text: code.trim()
    };
  }).map((line) => ({
    ...line,
    // `code` keeps original spacing for slicing; `text` is what the parser reads.
    code: line.code.replace(/\s+$/, '')
  }));
}

function pythonIndentWidth(line) {
  let width = 0;
  for (const ch of line) {
    if (ch === ' ') width += 1;
    else if (ch === '\t') width += 4 - (width % 4);
    else break;
  }
  return width;
}

/**
 * Replace Python comments and triple-quoted docstrings with spaces while
 * retaining all line breaks and indentation. Strings on a normal code line are
 * preserved so `print("hi")` remains valid.
 */
function maskPythonCommentsAndTripleStrings(source) {
  const chars = source.split('');
  let i = 0;
  let quote = null;
  let triple = false;
  while (i < chars.length) {
    const ch = source[i];
    if (quote) {
      if (ch === '\\') {
        i += 2;
        continue;
      }
      if (triple) {
        if (source.startsWith(quote.repeat(3), i)) {
          chars[i] = ' ';
          chars[i + 1] = ' ';
          chars[i + 2] = ' ';
          i += 3;
          quote = null;
          triple = false;
          continue;
        }
        if (ch !== '\n') chars[i] = ' ';
        i += 1;
        continue;
      }
      if (ch === quote) {
        quote = null;
      } else if (ch === '\n') {
        // Unterminated single-line string: stop at the line break.
        quote = null;
      }
      i += 1;
      continue;
    }
    if (ch === '#') {
      while (i < chars.length && chars[i] !== '\n') {
        chars[i] = ' ';
        i += 1;
      }
      continue;
    }
    if (ch === '"' || ch === "'") {
      if (source.startsWith(ch.repeat(3), i)) {
        chars[i] = ' ';
        chars[i + 1] = ' ';
        chars[i + 2] = ' ';
        i += 3;
        quote = ch;
        triple = true;
        continue;
      }
      quote = ch;
      i += 1;
      continue;
    }
    i += 1;
  }
  return chars.join('');
}

class PythonParser {
  constructor(lines, source, language, diagnostics) {
    this.lines = lines;
    this.source = source;
    this.language = language;
    this.diagnostics = diagnostics;
    this.cursor = 0;
  }

  nextSignificant(index) {
    let i = index;
    while (i < this.lines.length && !this.lines[i].code.trim()) i += 1;
    return i;
  }

  parseBlock(startIndex, indent, fallbackEndLine) {
    const children = [];
    let i = startIndex;
    let endLine = fallbackEndLine;
    while (i < this.lines.length) {
      const line = this.lines[i];
      if (!line.code.trim()) {
        i += 1;
        continue;
      }
      if (line.indent < indent) break;
      if (line.indent > indent) {
        // A malformed or continuation line. Skip it, but preserve a diagnostic.
        this.diagnostics.push({
          severity: 'info',
          message: 'A line with unexpected indentation was skipped.',
          line: line.number
        });
        i += 1;
        continue;
      }
      const text = line.code.trim();
      if (/^(elif\b|else\s*:|else\b|except\b|finally\s*:)/.test(text)) break;
      if (text.startsWith('@')) {
        i = this.nextSignificant(i + 1);
        continue;
      }

      let node = null;
      let nextIndex = i + 1;
      if (/^(async\s+)?def\s+/.test(text)) {
        const result = this.parseFunction(i, indent);
        node = result.node;
        nextIndex = result.nextIndex;
      } else if (/^class\s+/.test(text)) {
        const result = this.parseClass(i, indent);
        node = result.node;
        nextIndex = result.nextIndex;
      } else if (/^if\s+/.test(text)) {
        const result = this.parseIf(i, indent);
        node = result.node;
        nextIndex = result.nextIndex;
      } else if (/^for\s+/.test(text)) {
        const result = this.parseFor(i, indent);
        node = result.node;
        nextIndex = result.nextIndex;
      } else if (/^while\s+/.test(text)) {
        const result = this.parseWhile(i, indent);
        node = result.node;
        nextIndex = result.nextIndex;
      } else if (/^try\s*:/.test(text)) {
        const result = this.parseTry(i, indent);
        node = result.node;
        nextIndex = result.nextIndex;
      } else if (/^(with\s+|match\s+)/.test(text)) {
        const result = this.parseGenericBlock(i, indent);
        node = result.node;
        nextIndex = result.nextIndex;
      } else {
        node = this.makePythonAction(line);
        nextIndex = i + 1;
      }

      if (node) {
        children.push(node);
        endLine = node.endLine;
      }
      if (nextIndex <= i) nextIndex = i + 1;
      i = nextIndex;
    }
    return {
      block: makeBlock(children[0]?.startLine ?? this.lines[startIndex]?.number ?? fallbackEndLine, endLine, children),
      nextIndex: i
    };
  }

  suiteAfter(headerIndex, parentIndent, headerLine) {
    const bodyStart = this.nextSignificant(headerIndex + 1);
    if (bodyStart >= this.lines.length || this.lines[bodyStart].indent <= parentIndent) {
      const emptyLine = Math.min(headerLine + 1, this.lines.at(-1)?.number ?? headerLine);
      return {
        body: makeBlock(emptyLine, emptyLine, []),
        nextIndex: bodyStart
      };
    }
    const bodyIndent = this.lines[bodyStart].indent;
    const result = this.parseBlock(bodyStart, bodyIndent, this.lines[bodyStart].number);
    return { body: result.block, nextIndex: result.nextIndex };
  }

  headerText(line) {
    const trimmed = line.code.trim();
    return trimmed.endsWith(':') ? trimmed.slice(0, -1).trim() : trimmed;
  }

  makePythonAction(line) {
    const text = line.code.trim();
    const first = text.match(/^([A-Za-z_]\w*)/)?.[1] ?? '';
    const kind = classifyPythonActionKeyword(first);
    return {
      type: 'action',
      startLine: line.number,
      endLine: line.number,
      header: text,
      text,
      kind,
      rawFirst: first
    };
  }

  parseFunction(index, indent) {
    const line = this.lines[index];
    const text = line.code.trim();
    const header = this.headerText(line);
    const match = header.match(/^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\((.*)\)\s*(?:->\s*(.+))?$/);
    const name = match?.[1] ?? 'function';
    const params = parseParamList(match?.[2] ?? '', this.language);
    const returnType = match?.[3]?.trim() ?? '';
    const suite = this.suiteAfter(index, indent, line.number);
    return {
      node: {
        type: 'function',
        startLine: line.number,
        endLine: Math.max(suite.body.endLine, line.number),
        header,
        name,
        params,
        returnType,
        body: suite.body,
        keyword: 'def'
      },
      nextIndex: suite.nextIndex
    };
  }

  parseClass(index, indent) {
    const line = this.lines[index];
    const header = this.headerText(line);
    const name = header.match(/^class\s+([A-Za-z_]\w*)/)?.[1] ?? 'Class';
    const suite = this.suiteAfter(index, indent, line.number);
    return {
      node: {
        type: 'class',
        startLine: line.number,
        endLine: Math.max(suite.body.endLine, line.number),
        header,
        name,
        body: suite.body,
        keyword: 'class'
      },
      nextIndex: suite.nextIndex
    };
  }

  parseIf(index, indent, isElif = false) {
    const line = this.lines[index];
    const header = this.headerText(line);
    const condition = isElif
      ? header.replace(/^elif\s+/, '').trim()
      : header.replace(/^if\s+/, '').trim();
    const suite = this.suiteAfter(index, indent, line.number);
    let cursor = suite.nextIndex;
    let alternate = null;

    const next = this.nextSignificant(cursor);
    if (next < this.lines.length && this.lines[next].indent === indent) {
      const nextText = this.lines[next].code.trim();
      if (/^elif\s+/.test(nextText)) {
        const nested = this.parseIf(next, indent, true);
        alternate = makeBlock(nested.node.startLine, nested.node.endLine, [nested.node]);
        cursor = nested.nextIndex;
      } else if (/^else\s*:/.test(nextText)) {
        const elseSuite = this.suiteAfter(next, indent, this.lines[next].number);
        alternate = elseSuite.body;
        alternate.startLine = this.lines[next].number;
        cursor = elseSuite.nextIndex;
      }
    }

    const endLine = Math.max(suite.body.endLine, alternate?.endLine ?? 0, line.number);
    return {
      node: {
        type: 'if',
        startLine: line.number,
        endLine,
        header,
        condition,
        consequent: suite.body,
        alternate,
        hasElse: !!alternate,
        keyword: isElif ? 'elif' : 'if'
      },
      nextIndex: cursor
    };
  }

  parseFor(index, indent) {
    const line = this.lines[index];
    const header = this.headerText(line);
    const suite = this.suiteAfter(index, indent, line.number);
    return {
      node: {
        type: 'for',
        startLine: line.number,
        endLine: Math.max(suite.body.endLine, line.number),
        header,
        loopHeader: header.replace(/^for\s+/, ''),
        body: suite.body,
        keyword: 'for'
      },
      nextIndex: suite.nextIndex
    };
  }

  parseWhile(index, indent) {
    const line = this.lines[index];
    const header = this.headerText(line);
    const condition = header.replace(/^while\s+/, '').trim();
    const suite = this.suiteAfter(index, indent, line.number);
    return {
      node: {
        type: 'while',
        startLine: line.number,
        endLine: Math.max(suite.body.endLine, line.number),
        header,
        condition,
        body: suite.body,
        keyword: 'while'
      },
      nextIndex: suite.nextIndex
    };
  }

  parseTry(index, indent) {
    const line = this.lines[index];
    const startLine = line.number;
    const suite = this.suiteAfter(index, indent, line.number);
    let cursor = suite.nextIndex;
    const handlers = [];
    let lastEnd = suite.body.endLine;
    while (cursor < this.lines.length) {
      const next = this.nextSignificant(cursor);
      if (next >= this.lines.length || this.lines[next].indent !== indent) break;
      const text = this.lines[next].code.trim();
      if (/^(except|else\s*:|finally\s*:)/.test(text)) {
        const hSuite = this.suiteAfter(next, indent, this.lines[next].number);
        handlers.push({
          type: /^finally/.test(text) ? 'finally' : /^else/.test(text) ? 'else' : 'except',
          header: this.headerText(this.lines[next]),
          body: hSuite.body,
          startLine: this.lines[next].number,
          endLine: hSuite.body.endLine
        });
        lastEnd = Math.max(lastEnd, hSuite.body.endLine);
        cursor = hSuite.nextIndex;
        continue;
      }
      break;
    }
    return {
      node: {
        type: 'try',
        startLine,
        endLine: Math.max(lastEnd, startLine),
        header: 'try',
        body: suite.body,
        handlers,
        keyword: 'try'
      },
      nextIndex: cursor
    };
  }

  parseGenericBlock(index, indent) {
    const line = this.lines[index];
    const header = this.headerText(line);
    const suite = this.suiteAfter(index, indent, line.number);
    return {
      node: {
        type: 'block',
        startLine: line.number,
        endLine: Math.max(suite.body.endLine, line.number),
        header,
        body: suite.body
      },
      nextIndex: suite.nextIndex
    };
  }
}

function classifyPythonActionKeyword(word) {
  if (['return', 'break', 'continue', 'raise', 'yield'].includes(word)) return word;
  if (['import', 'from'].includes(word)) return 'import';
  if (['pass'].includes(word)) return 'pass';
  return 'action';
}

/* -------------------------------------------------------------------------- */
/* Shared helpers                                                             */
/* -------------------------------------------------------------------------- */

export function assignNodeIds(root) {
  let counter = 0;
  const seen = new Set();
  const visit = (node) => {
    if (!node || typeof node !== 'object' || seen.has(node)) return;
    seen.add(node);
    if (typeof node.type === 'string') {
      counter += 1;
      node.id = `node-${counter}`;
    }
    if (node.body) visit(node.body);
    if (node.consequent) visit(node.consequent);
    if (node.alternate) visit(node.alternate);
    if (Array.isArray(node.handlers)) node.handlers.forEach((handler) => visit(handler.body));
    if (node.type === 'block') node.children.forEach(visit);
  };
  visit(root);
  return root;
}

/** Visit statement nodes (not block containers) in source order. */
export function walkStatements(node, visitor) {
  if (!node) return;
  if (node.type === 'block') {
    node.children.forEach((child) => walkStatements(child, visitor));
    return;
  }
  if (node.type !== 'program' && node.type !== 'class' && node.type !== 'function') {
    visitor(node);
  }
  if (node.type === 'program' || node.type === 'function' || node.type === 'class' || node.type === 'block') {
    if (node.body) walkStatements(node.body, visitor);
  }
  if (node.consequent) walkStatements(node.consequent, visitor);
  if (node.alternate) walkStatements(node.alternate, visitor);
  if (Array.isArray(node.handlers)) node.handlers.forEach((handler) => walkStatements(handler.body, visitor));
  if (node.type === 'if' || node.type === 'for' || node.type === 'while' || node.type === 'do' || node.type === 'switch') {
    if (node.body) walkStatements(node.body, visitor);
  }
}

export function collectFunctions(root, result = [], seen = new Set()) {
  if (!root || typeof root !== 'object' || seen.has(root)) return result;
  seen.add(root);
  if (root.type === 'function') {
    result.push(root);
  }
  if (root.body) collectFunctions(root.body, result, seen);
  if (root.consequent) collectFunctions(root.consequent, result, seen);
  if (root.alternate) collectFunctions(root.alternate, result, seen);
  if (Array.isArray(root.handlers)) root.handlers.forEach((handler) => collectFunctions(handler.body, result, seen));
  return result;
}

export function nodeContainsLine(node, line) {
  return !!node && line >= node.startLine && line <= (node.endLine ?? node.startLine);
}

export function makeEmptyBlock(line) {
  return makeBlock(line, line, []);
}
