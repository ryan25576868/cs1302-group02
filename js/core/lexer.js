/**
 * A forgiving lexer used by both the structural parser and the code views.
 * It never throws on malformed input; anything unexpected becomes plain text.
 */

const MULTI_CHAR_OPERATORS = [
  '>>>=', '===', '!==', '>>>', '**=', '<<=', '>>=', '...', '??=',
  '=>', '==', '!=', '<=', '>=', '&&', '||', '++', '--', '+=', '-=',
  '*=', '/=', '%=', '&=', '|=', '^=', '<<', '>>', '**', '//', '??',
  '?.', '::', '->', ':='
];

const SINGLE_CHAR_OPERATORS = '+-*/%=<>!&|^~?:';
const PUNCTUATION = '(){}[];,';
const STRING_PREFIXES = new Set(['f', 'r', 'b', 'u', 'fr', 'rf', 'br', 'rb', 'ur']);

function isDigit(ch) {
  return ch >= '0' && ch <= '9';
}

function isIdentifierStart(ch) {
  return !!ch && ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch === '_' || ch === '$');
}

function isIdentifierPart(ch) {
  return isIdentifierStart(ch) || isDigit(ch);
}

function countNewlines(text) {
  let count = 0;
  let lastBreak = -1;
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === '\n') {
      count += 1;
      lastBreak = i;
    }
  }
  return { count, lastBreak };
}

function advancePosition(state, text) {
  const { count, lastBreak } = countNewlines(text);
  if (count === 0) {
    state.column += text.length;
    return;
  }
  state.line += count;
  state.column = text.length - lastBreak;
}

function normaliseNewlines(source) {
  return String(source ?? '').replace(/\r\n?/g, '\n');
}

/**
 * Tokenize source into a complete token stream, including whitespace.
 * Token shape: { type, value, start, end, line, column, endLine }
 */
export function lex(source, language) {
  const text = normaliseNewlines(source);
  const tokens = [];
  const keywordSet = new Set(language?.keywords ?? []);
  const literalSet = new Set(language?.literals ?? []);
  const lineComment = language?.lineComment ?? '//';
  const blockComment = language?.blockComment ?? null;
  const isC = language?.id === 'c' || language?.id === 'cpp';
  const state = { line: 1, column: 1 };
  let i = 0;

  const push = (type, start, startLine, startColumn) => {
    const value = text.slice(start, i);
    tokens.push({
      type,
      value,
      start,
      end: i,
      line: startLine,
      column: startColumn,
      endLine: state.line
    });
    advancePosition(state, value);
  };

  while (i < text.length) {
    const start = i;
    const startLine = state.line;
    const startColumn = state.column;
    const ch = text[i];

    // Preprocessor directives in C and C++ get their own colour and are
    // ignored by the language parser.
    if (isC && ch === '#' && isAtLineStart(text, i)) {
      while (i < text.length && text[i] !== '\n') i += 1;
      push('meta', start, startLine, startColumn);
      continue;
    }

    // Whitespace (newlines included; the editor relies on exact whitespace).
    if (/\s/.test(ch)) {
      i += 1;
      while (i < text.length && /\s/.test(text[i])) i += 1;
      push('whitespace', start, startLine, startColumn);
      continue;
    }

    // Line comments.
    if (lineComment && text.startsWith(lineComment, i)) {
      i += lineComment.length;
      while (i < text.length && text[i] !== '\n') i += 1;
      push('comment', start, startLine, startColumn);
      continue;
    }

    // Block comments.
    if (blockComment && text.startsWith(blockComment[0], i)) {
      i += blockComment[0].length;
      while (i < text.length) {
        if (text.startsWith(blockComment[1], i)) {
          i += blockComment[1].length;
          break;
        }
        i += 1;
      }
      push('comment', start, startLine, startColumn);
      continue;
    }

    // Python and JavaScript string prefixes such as f"..." or r'...'.
    if (isIdentifierStart(ch)) {
      const prefixMatch = text.slice(i).match(/^([rRbBuUfF]{1,2})(["'])/);
      if (prefixMatch && language?.family === 'python') {
        const prefixLength = prefixMatch[1].length;
        const quote = prefixMatch[2];
        i += prefixLength;
        i = scanString(text, i, quote);
        push('string', start, startLine, startColumn);
        continue;
      }
    }

    // Strings and template literals.
    if (ch === '"' || ch === "'" || ch === '`') {
      i = scanString(text, i, ch);
      push('string', start, startLine, startColumn);
      continue;
    }

    // Numbers (hex/binary/float and numeric separators).
    if (isDigit(ch) || (ch === '.' && isDigit(text[i + 1]))) {
      i = scanNumber(text, i);
      push('number', start, startLine, startColumn);
      continue;
    }

    // Identifiers, keywords, and literals.
    if (isIdentifierStart(ch)) {
      i += 1;
      while (i < text.length && isIdentifierPart(text[i])) i += 1;
      const word = text.slice(start, i);
      const type = literalSet.has(word) ? 'literal' : keywordSet.has(word) ? 'keyword' : 'identifier';
      push(type, start, startLine, startColumn);
      continue;
    }

    // Operators (longest match first).
    const operator = MULTI_CHAR_OPERATORS.find((candidate) => text.startsWith(candidate, i));
    if (operator) {
      i += operator.length;
      push('operator', start, startLine, startColumn);
      continue;
    }
    if (SINGLE_CHAR_OPERATORS.includes(ch)) {
      i += 1;
      push('operator', start, startLine, startColumn);
      continue;
    }
    if (PUNCTUATION.includes(ch)) {
      i += 1;
      push('punctuation', start, startLine, startColumn);
      continue;
    }

    // Unknown character: keep it visible, never crash.
    i += 1;
    push('plain', start, startLine, startColumn);
  }

  annotateTokens(tokens);
  return tokens;
}

function scanString(text, startQuoteIndex, quote) {
  let i = startQuoteIndex + 1;
  const isTriple = text.startsWith(quote.repeat(3), startQuoteIndex);
  const closing = isTriple ? quote.repeat(3) : quote;
  if (isTriple) i = startQuoteIndex + 3;
  while (i < text.length) {
    if (text[i] === '\\') {
      i += 2;
      continue;
    }
    if (text.startsWith(closing, i)) {
      return i + closing.length;
    }
    if (!isTriple && text[i] === '\n') {
      // Recover from an unterminated single-line string.
      return i;
    }
    i += 1;
  }
  return text.length;
}

function scanNumber(text, start) {
  let i = start;
  if (text[i] === '0' && /[xXbBoO]/.test(text[i + 1] ?? '')) {
    i += 2;
    while (i < text.length && /[0-9a-fA-F_]/.test(text[i])) i += 1;
    return i;
  }
  while (i < text.length && /[\d_]/.test(text[i])) i += 1;
  if (text[i] === '.') {
    i += 1;
    while (i < text.length && /[\d_]/.test(text[i])) i += 1;
  }
  if (/[eE]/.test(text[i] ?? '')) {
    const save = i;
    i += 1;
    if (/[+-]/.test(text[i] ?? '')) i += 1;
    if (!isDigit(text[i] ?? '')) {
      i = save;
    } else {
      while (i < text.length && /[\d_]/.test(text[i])) i += 1;
    }
  }
  // Type suffixes in C/C++ and Java.
  while (i < text.length && /[fFlLdDmMuU]/.test(text[i])) i += 1;
  return i;
}

function isAtLineStart(text, index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (text[i] === '\n') return true;
    if (!/\s/.test(text[i])) return false;
  }
  return true;
}

function annotateTokens(tokens) {
  const significant = [];
  for (let i = 0; i < tokens.length; i += 1) {
    if (tokens[i].type !== 'whitespace' && tokens[i].type !== 'comment' && tokens[i].type !== 'meta') {
      significant.push(i);
    }
  }
  const order = new Map(significant.map((tokenIndex, position) => [tokenIndex, position]));
  for (let position = 0; position < significant.length; position += 1) {
    const tokenIndex = significant[position];
    const token = tokens[tokenIndex];
    if (token.type !== 'identifier') continue;
    const previous = tokens[significant[position - 1]];
    const next = tokens[significant[position + 1]];
    if (next?.value === '(') {
      token.role = 'call';
    } else if (previous?.value === '.') {
      token.role = 'property';
    } else if (previous?.value === 'def' || previous?.value === 'function' || previous?.value === 'class') {
      token.role = 'definition';
    }
    // Keep the order map alive for future extensions without throwing.
    void order;
  }
}

/** Tokens the parser cares about: no whitespace, comments, or directives. */
export function syntaxTokens(source, language) {
  return lex(source, language).filter(
    (token) => token.type !== 'whitespace' && token.type !== 'comment' && token.type !== 'meta'
  );
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function tokenClass(token) {
  if (token.type === 'keyword') return 'tok-keyword';
  if (token.type === 'literal') return 'tok-literal';
  if (token.type === 'string') return 'tok-string';
  if (token.type === 'number') return 'tok-number';
  if (token.type === 'comment') return 'tok-comment';
  if (token.type === 'meta') return 'tok-meta';
  if (token.type === 'operator') return 'tok-operator';
  if (token.type === 'punctuation') return 'tok-punctuation';
  if (token.type === 'identifier') {
    if (token.role === 'call') return 'tok-call';
    if (token.role === 'property') return 'tok-property';
    if (token.role === 'definition') return 'tok-definition';
  }
  return '';
}

/** Complete syntax-highlighted HTML. Whitespace is preserved by the caller. */
export function highlightHTML(source, language) {
  const tokens = lex(source, language);
  return tokens
    .map((token) => {
      const content = escapeHtml(token.value);
      const className = tokenClass(token);
      return className ? `<span class="${className}">${content}</span>` : content;
    })
    .join('');
}

/**
 * Split highlighted output into lines. Used by the read-only source pane so
 * line highlighting remains exact even with block comments.
 */
export function highlightLines(source, language) {
  const text = normaliseNewlines(source);
  const tokens = lex(text, language);
  const lines = [''];
  const append = (html) => {
    lines[lines.length - 1] += html;
  };

  for (const token of tokens) {
    const className = tokenClass(token);
    const parts = token.value.split('\n');
    parts.forEach((part, index) => {
      if (index > 0) lines.push('');
      if (!part) return;
      const html = escapeHtml(part);
      append(className ? `<span class="${className}">${html}</span>` : html);
    });
  }
  return lines;
}

export function lineNumberOf(source, index) {
  let line = 1;
  const limit = Math.max(0, Math.min(index, source.length));
  for (let i = 0; i < limit; i += 1) {
    if (source[i] === '\n') line += 1;
  }
  return line;
}
