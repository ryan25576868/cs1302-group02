/**
 * A small, language-tolerant expression parser.
 *
 * Prism does not need a compiler-grade AST. It needs a safe, predictable tree
 * it can inspect, draw, and evaluate for common beginner expressions. Anything
 * outside that supported subset becomes a RawExpression and is never executed.
 */

const OPERATORS = [
  '===', '!==', '>>>', '**=', '<<=', '>>=', '...', '??=', '=>', '==', '!=',
  '<=', '>=', '&&', '||', '++', '--', '+=', '-=', '*=', '/=', '%=', '&=',
  '|=', '^=', '<<', '>>', '**', '//', '??', '?.', '::', '->', ':=',
  '+', '-', '*', '/', '%', '<', '>', '=', '!', '&', '|', '^', '~', '?', ':'
];

const PYTHON_WORD_OPERATORS = new Set(['and', 'or', 'not', 'in', 'is']);

const PRECEDENCE = {
  '||': 2,
  'or': 2,
  '??': 3,
  '&&': 4,
  'and': 4,
  '|': 5,
  '^': 6,
  '&': 7,
  '==': 8,
  '!=': 8,
  '===': 8,
  '!==': 8,
  'is': 8,
  'in': 8,
  '<': 9,
  '<=': 9,
  '>': 9,
  '>=': 9,
  '<<': 10,
  '>>': 10,
  '+': 11,
  '-': 11,
  '*': 12,
  '/': 12,
  '//': 12,
  '%': 12,
  '**': 13
};

const ASSIGNMENT_OPERATORS = new Set(['=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>=', '**=']);

function isDigit(ch) {
  return ch >= '0' && ch <= '9';
}

function isIdentStart(ch) {
  return !!ch && ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch === '_' || ch === '$');
}

function isIdentPart(ch) {
  return isIdentStart(ch) || isDigit(ch);
}

class ExpressionParseError extends Error {}

export function tokenizeExpression(text, language = {}) {
  const tokens = [];
  let i = 0;
  const input = String(text ?? '');
  const isPython = language.family === 'python';

  while (i < input.length) {
    const ch = input[i];
    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }

    // Strings (including Python f-strings and JS template literals).
    const prefixMatch = input.slice(i).match(/^([rRbBuUfF]{1,2})(["'])/);
    if (prefixMatch) {
      const prefix = prefixMatch[1].toLowerCase();
      const quote = prefixMatch[2];
      const start = i;
      i += prefix.length;
      const result = readQuotedString(input, i, quote);
      const raw = input.slice(start, result.end);
      tokens.push({
        type: 'string',
        raw,
        prefix,
        quote,
        content: result.content,
        template: prefix.includes('f'),
        start,
        end: result.end
      });
      i = result.end;
      continue;
    }

    if (ch === '"' || ch === "'" || ch === '`') {
      const start = i;
      const result = readQuotedString(input, i, ch);
      tokens.push({
        type: 'string',
        raw: input.slice(start, result.end),
        prefix: '',
        quote: ch,
        content: result.content,
        template: ch === '`',
        start,
        end: result.end
      });
      i = result.end;
      continue;
    }

    if (isDigit(ch) || (ch === '.' && isDigit(input[i + 1]))) {
      const start = i;
      while (i < input.length && /[\d_]/.test(input[i])) i += 1;
      if (input[i] === '.' && isDigit(input[i + 1] ?? '')) {
        i += 1;
        while (i < input.length && /[\d_]/.test(input[i])) i += 1;
      }
      if (/[eE]/.test(input[i] ?? '')) {
        const save = i;
        i += 1;
        if (/[+-]/.test(input[i] ?? '')) i += 1;
        if (!isDigit(input[i] ?? '')) {
          i = save;
        } else {
          while (i < input.length && /[\d_]/.test(input[i])) i += 1;
        }
      }
      while (i < input.length && /[fFlLdDuU]/.test(input[i])) i += 1;
      const raw = input.slice(start, i);
      const clean = raw.replaceAll('_', '').replace(/[fFlLdDuU]$/, '');
      tokens.push({ type: 'number', raw, value: Number(clean), start, end: i });
      continue;
    }

    if (isIdentStart(ch)) {
      const start = i;
      i += 1;
      while (i < input.length && isIdentPart(input[i])) i += 1;
      const raw = input.slice(start, i);
      if (isPython && PYTHON_WORD_OPERATORS.has(raw)) {
        tokens.push({ type: 'operator', raw, start, end: i });
      } else if (raw === 'not' && isPython) {
        tokens.push({ type: 'operator', raw, start, end: i });
      } else {
        tokens.push({ type: 'identifier', raw, start, end: i });
      }
      continue;
    }

    const operator = OPERATORS.find((candidate) => input.startsWith(candidate, i));
    if (operator) {
      tokens.push({ type: 'operator', raw: operator, start: i, end: i + operator.length });
      i += operator.length;
      continue;
    }

    if ('()[]{}.,;'.includes(ch)) {
      tokens.push({ type: 'punctuation', raw: ch, start: i, end: i + 1 });
      i += 1;
      continue;
    }

    throw new ExpressionParseError(`Unexpected character: ${ch}`);
  }

  tokens.push({ type: 'eof', raw: '', start: i, end: i });
  return tokens;
}

function readQuotedString(input, quoteIndex, quote) {
  const triple = input.startsWith(quote.repeat(3), quoteIndex);
  const closing = triple ? quote.repeat(3) : quote;
  let i = quoteIndex + closing.length;
  let content = '';
  while (i < input.length) {
    if (input[i] === '\\') {
      content += input.slice(i, i + 2);
      i += 2;
      continue;
    }
    if (input.startsWith(closing, i)) {
      return { content, end: i + closing.length };
    }
    if (!triple && input[i] === '\n') {
      return { content, end: i };
    }
    content += input[i];
    i += 1;
  }
  return { content, end: input.length };
}

function decodeEscapes(value) {
  let result = '';
  for (let i = 0; i < value.length; i += 1) {
    const ch = value[i];
    if (ch !== '\\' || i === value.length - 1) {
      result += ch;
      continue;
    }
    const next = value[i + 1];
    const escapes = {
      n: '\n', t: '\t', r: '\r', '\\': '\\', '"': '"', "'": "'", '`': '`', 0: '\0'
    };
    if (next === 'u' && /^[0-9a-fA-F]{4}$/.test(value.slice(i + 2, i + 6))) {
      result += String.fromCharCode(parseInt(value.slice(i + 2, i + 6), 16));
      i += 5;
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(escapes, next)) {
      result += escapes[next];
      i += 1;
      continue;
    }
    result += next;
    i += 1;
  }
  return result;
}

function parseStringParts(content, braces) {
  const parts = [];
  let text = '';
  let i = 0;
  const open = braces === '${' ? '${' : '{';
  while (i < content.length) {
    if (content[i] === '\\') {
      text += content.slice(i, i + 2);
      i += 2;
      continue;
    }
    if (content.startsWith(open, i)) {
      if (text) {
        parts.push({ type: 'text', value: decodeEscapes(text) });
        text = '';
      }
      const closeChar = '}';
      let depth = 1;
      let j = i + open.length;
      let expressionText = '';
      while (j < content.length && depth > 0) {
        const current = content[j];
        if (current === '{') depth += 1;
        else if (current === '}') depth -= 1;
        if (depth > 0) expressionText += current;
        j += 1;
      }
      const parsed = parseExpression(expressionText, {});
      parts.push({ type: 'expression', ast: parsed });
      i = j;
      continue;
    }
    text += content[i];
    i += 1;
  }
  if (text) parts.push({ type: 'text', value: decodeEscapes(text) });
  return parts;
}

export function parseExpression(text, language = {}) {
  const source = String(text ?? '').trim();
  if (!source) {
    return { type: 'RawExpression', text: '', reason: 'empty' };
  }
  try {
    const tokens = tokenizeExpression(source, language);
    const parser = new PrattParser(tokens, source, language);
    const ast = parser.parse(0);
    if (parser.peek().type !== 'eof') {
      throw new ExpressionParseError('Unexpected trailing input');
    }
    return ast;
  } catch (error) {
    return {
      type: 'RawExpression',
      text: source,
      reason: error instanceof Error ? error.message : 'Unsupported expression'
    };
  }
}

class PrattParser {
  constructor(tokens, source, language) {
    this.tokens = tokens;
    this.source = source;
    this.language = language;
    this.index = 0;
  }

  peek(offset = 0) {
    return this.tokens[Math.min(this.index + offset, this.tokens.length - 1)];
  }

  next() {
    const token = this.peek();
    this.index += 1;
    return token;
  }

  match(raw) {
    if (this.peek().raw === raw) {
      this.index += 1;
      return true;
    }
    return false;
  }

  expect(raw) {
    if (!this.match(raw)) {
      throw new ExpressionParseError(`Expected ${raw}`);
    }
  }

  parse(minPrecedence = 0) {
    let left = this.parsePrefix();
    left = this.parsePostfix(left);

    while (true) {
      const token = this.peek();
      if (token.type === 'eof') break;

      // Assignment expressions bind to the right and have the lowest priority.
      if (token.type === 'operator' && ASSIGNMENT_OPERATORS.has(token.raw) && minPrecedence <= 1) {
        this.next();
        const right = this.parse(1);
        left = {
          type: 'AssignmentExpression',
          operator: token.raw,
          left,
          right
        };
        continue;
      }

      // Ternary conditional (JavaScript / Java / C-family).
      if (token.raw === '?' && minPrecedence <= 2) {
        this.next();
        const consequent = this.parse(0);
        this.expect(':');
        const alternate = this.parse(2);
        left = {
          type: 'ConditionalExpression',
          test: left,
          consequent,
          alternate
        };
        continue;
      }

      const operator = token.raw;
      const precedence = PRECEDENCE[operator];
      if (!precedence || precedence < minPrecedence) break;
      this.next();
      const rightAssociative = operator === '**';
      const right = this.parse(rightAssociative ? precedence : precedence + 1);
      const logical = ['&&', '||', 'and', 'or', '??'].includes(operator);
      left = {
        type: logical ? 'LogicalExpression' : 'BinaryExpression',
        operator,
        left,
        right
      };
    }

    return left;
  }

  parsePrefix() {
    const token = this.peek();

    if (token.type === 'number') {
      this.next();
      return { type: 'Literal', valueType: 'number', value: token.value, raw: token.raw };
    }

    if (token.type === 'string') {
      this.next();
      if (token.template) {
        return {
          type: 'Literal',
          valueType: 'template',
          value: token.content,
          raw: token.raw,
          prefix: token.prefix,
          templateStyle: token.prefix.includes('f') ? 'brace' : 'dollar',
          parts: safeTemplateParts(token.content, token.prefix.includes('f') ? '{' : '${')
        };
      }
      return {
        type: 'Literal',
        valueType: 'string',
        value: decodeEscapes(token.content),
        raw: token.raw
      };
    }

    if (token.type === 'identifier') {
      this.next();
      if (token.raw === 'true' || token.raw === 'True') {
        return { type: 'Literal', valueType: 'boolean', value: true, raw: token.raw };
      }
      if (token.raw === 'false' || token.raw === 'False') {
        return { type: 'Literal', valueType: 'boolean', value: false, raw: token.raw };
      }
      if (['null', 'None', 'nil', 'NULL', 'nullptr'].includes(token.raw)) {
        return { type: 'Literal', valueType: 'null', value: null, raw: token.raw };
      }
      if (token.raw === 'undefined') {
        return { type: 'Literal', valueType: 'undefined', value: undefined, raw: token.raw };
      }
      return { type: 'Identifier', name: token.raw };
    }

    if (token.type === 'operator') {
      if (['!', 'not', '-', '+', '~', 'typeof', 'void', 'await'].includes(token.raw)) {
        this.next();
        const argument = this.parse(14);
        return {
          type: 'UnaryExpression',
          operator: token.raw === 'not' ? '!' : token.raw,
          argument,
          rawOperator: token.raw
        };
      }
      if (token.raw === 'new') {
        this.next();
        return this.parsePrefix();
      }
      if (token.raw === '++' || token.raw === '--') {
        this.next();
        const argument = this.parse(14);
        return { type: 'UpdateExpression', operator: token.raw, argument, prefix: true };
      }
      throw new ExpressionParseError(`Unexpected operator ${token.raw}`);
    }

    if (token.raw === '(') {
      this.next();
      const expression = this.parse(0);
      this.expect(')');
      return expression;
    }

    if (token.raw === '[') {
      this.next();
      const elements = [];
      while (!this.match(']')) {
        if (this.peek().type === 'eof') throw new ExpressionParseError('Unclosed array');
        if (this.match(',')) continue;
        elements.push(this.parse(0));
        if (!this.match(',')) {
          this.expect(']');
          break;
        }
      }
      return { type: 'ArrayExpression', elements };
    }

    if (token.raw === '{') {
      this.next();
      const properties = [];
      while (!this.match('}')) {
        if (this.peek().type === 'eof') throw new ExpressionParseError('Unclosed object');
        if (this.match(',')) continue;
        const keyToken = this.next();
        let key;
        if (keyToken.type === 'string') key = decodeEscapes(keyToken.content);
        else key = keyToken.raw;
        if (this.match(':')) {
          properties.push({ key, value: this.parse(0) });
        } else {
          properties.push({ key, value: { type: 'Identifier', name: key } });
        }
        if (!this.match(',')) {
          this.expect('}');
          break;
        }
      }
      return { type: 'ObjectExpression', properties };
    }

    throw new ExpressionParseError(`Unexpected token ${token.raw || token.type}`);
  }

  parsePostfix(base) {
    let expression = base;
    while (true) {
      const token = this.peek();
      if (token.raw === '(') {
        this.next();
        const args = [];
        while (!this.match(')')) {
          if (this.peek().type === 'eof') throw new ExpressionParseError('Unclosed call');
          if (this.match(',')) continue;
          // Keyword arguments (Python) are accepted, but only the value is kept.
          if (this.peek().type === 'identifier' && this.peek(1).raw === '=') {
            this.next();
            this.next();
          }
          args.push(this.parse(0));
          if (!this.match(',')) {
            this.expect(')');
            break;
          }
        }
        expression = { type: 'CallExpression', callee: expression, arguments: args };
        continue;
      }
      if (token.raw === '.' || token.raw === '?.') {
        this.next();
        const property = this.next();
        if (property.type !== 'identifier' && property.type !== 'keyword') {
          throw new ExpressionParseError('Expected a property name');
        }
        expression = {
          type: 'MemberExpression',
          object: expression,
          property: { type: 'Identifier', name: property.raw },
          computed: false,
          optional: token.raw === '?.'
        };
        continue;
      }
      if (token.raw === '[') {
        this.next();
        const property = this.parse(0);
        this.expect(']');
        expression = {
          type: 'MemberExpression',
          object: expression,
          property,
          computed: true
        };
        continue;
      }
      if (token.raw === '++' || token.raw === '--') {
        this.next();
        expression = {
          type: 'UpdateExpression',
          operator: token.raw,
          argument: expression,
          prefix: false
        };
        continue;
      }
      break;
    }
    return expression;
  }
}

function safeTemplateParts(content, braceStyle) {
  try {
    return parseStringParts(content, braceStyle);
  } catch {
    return [{ type: 'text', value: content }];
  }
}

/** Walk every child expression node. */
export function walkExpression(node, visitor) {
  if (!node || typeof node !== 'object') return;
  visitor(node);
  switch (node.type) {
    case 'UnaryExpression':
    case 'UpdateExpression':
      walkExpression(node.argument, visitor);
      break;
    case 'BinaryExpression':
    case 'LogicalExpression':
    case 'AssignmentExpression':
      walkExpression(node.left, visitor);
      walkExpression(node.right, visitor);
      break;
    case 'ConditionalExpression':
      walkExpression(node.test, visitor);
      walkExpression(node.consequent, visitor);
      walkExpression(node.alternate, visitor);
      break;
    case 'CallExpression':
      walkExpression(node.callee, visitor);
      node.arguments.forEach((argument) => walkExpression(argument, visitor));
      break;
    case 'MemberExpression':
      walkExpression(node.object, visitor);
      if (node.computed) walkExpression(node.property, visitor);
      break;
    case 'ArrayExpression':
      node.elements.forEach((element) => walkExpression(element, visitor));
      break;
    case 'ObjectExpression':
      node.properties.forEach((property) => walkExpression(property.value, visitor));
      break;
    case 'Literal':
      if (node.valueType === 'template' && Array.isArray(node.parts)) {
        node.parts.forEach((part) => {
          if (part.type === 'expression') walkExpression(part.ast, visitor);
        });
      }
      break;
    default:
      break;
  }
}

export function collectIdentifiers(node) {
  const names = new Set();
  walkExpression(node, (child) => {
    if (child.type === 'Identifier') names.add(child.name);
  });
  return [...names];
}

export function describeOperator(operator) {
  const words = {
    '+': 'adds', '-': 'subtracts', '*': 'multiplies', '/': 'divides',
    '%': 'finds the remainder of', '**': 'raises to a power', '//': 'divides and rounds down',
    '==': 'checks equality with', '===': 'strictly checks equality with',
    '!=': 'checks difference from', '!==': 'strictly checks difference from',
    '>': 'checks greater than', '<': 'checks less than',
    '>=': 'checks greater than or equal to', '<=': 'checks less than or equal to',
    '&&': 'combines two conditions', '||': 'offers an alternative',
    'and': 'combines two conditions', 'or': 'offers an alternative',
    '!': 'flips', 'not': 'flips'
  };
  return words[operator] ?? operator;
}

export function isSupportedExpression(ast) {
  return !!ast && ast.type !== 'RawExpression';
}
