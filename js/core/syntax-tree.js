/**
 * Convert Prism's structural tree into a friendly, syntax-tree-shaped diagram.
 * It is an educational tree rather than a compiler AST, but it keeps the same
 * useful nesting: declarations contain bodies, conditions contain tests, and
 * expressions branch into their operands.
 */

import { splitTopLevel } from './parser.js';

const MAX_NODES = 180;

export function buildSyntaxTree(analysis) {
  let counter = 0;
  let truncated = false;

  const create = (type, label, options = {}) => {
    counter += 1;
    return {
      id: options.id ?? `syntax-${counter}`,
      type,
      label: label ?? '',
      line: options.line ?? null,
      endLine: options.endLine ?? options.line ?? null,
      category: options.category ?? categoryForType(type),
      children: [],
      meta: options.meta ?? '',
      collapsed: false
    };
  };

  const addStatement = (parent, node) => {
    if (counter >= MAX_NODES) {
      truncated = true;
      return;
    }
    const display = statementToDisplay(node);
    if (!display) return;
    parent.children.push(display);
  };

  const addStatements = (parent, block) => {
    for (const child of block?.children ?? []) {
      if (counter >= MAX_NODES) {
        truncated = true;
        if (!parent.children.some((item) => item.id === 'truncated')) {
          parent.children.push(create('MoreStatements', '… more statements', {
            category: 'muted',
            id: 'truncated',
            meta: 'The tree is capped for readability'
          }));
        }
        return;
      }
      addStatement(parent, child);
    }
  };

  function statementToDisplay(node) {
    if (!node) return null;
    switch (node.type) {
      case 'program': {
        const display = create('Program', analysis.language.name, {
          line: 1,
          category: 'root',
          id: 'syntax-program',
          meta: `${analysis.metrics.totalLines} lines`
        });
        addStatements(display, node.body);
        return display;
      }
      case 'class': {
        const display = create(node.keyword === 'interface' ? 'InterfaceDeclaration' : 'ClassDeclaration', node.name, {
          line: node.startLine,
          category: 'structure',
          meta: node.keyword ? `${node.keyword} body` : 'class body'
        });
        addStatements(display, node.body);
        return display;
      }
      case 'function': {
        const paramList = node.params.map((param) => param.name).join(', ');
        const display = create('FunctionDeclaration', `${node.name}(${paramList})`, {
          line: node.startLine,
          category: 'function',
          meta: node.params.length ? `${node.params.length} parameter${node.params.length === 1 ? '' : 's'}` : 'no parameters'
        });
        if (node.params.length) {
          const params = create('Parameters', 'Parameters', {
            line: node.startLine,
            category: 'function',
            meta: `${node.params.length}`
          });
          for (const param of node.params) {
            params.children.push(create('Parameter', paramLabel(param), {
              line: node.startLine,
              category: 'function'
            }));
          }
          display.children.push(params);
        }
        const body = create('Block', 'Body', {
          line: node.body?.startLine ?? node.startLine,
          category: 'block',
          meta: `${node.body?.children?.length ?? 0} statements`
        });
        addStatements(body, node.body);
        display.children.push(body);
        return display;
      }
      case 'if': {
        const display = create(node.keyword === 'elif' ? 'ElifStatement' : 'IfStatement', shorten(node.condition, 64), {
          line: node.startLine,
          category: 'control',
          meta: node.alternate ? 'two possible paths' : 'one guarded path'
        });
        display.children.push(expressionNode(node.conditionAST, 'Test'));
        const thenBlock = create('Block', 'Then branch', {
          line: node.consequent?.startLine ?? node.startLine,
          category: 'control',
          meta: `${node.consequent?.children?.length ?? 0} statements`
        });
        addStatements(thenBlock, node.consequent);
        display.children.push(thenBlock);
        if (node.alternate) {
          const elseBlock = create('Block', 'Else branch', {
            line: node.alternate.startLine,
            category: 'control',
            meta: `${node.alternate.children?.length ?? 0} statements`
          });
          addStatements(elseBlock, node.alternate);
          display.children.push(elseBlock);
        }
        return display;
      }
      case 'for': {
        const meta = node.loopMeta;
        const type = meta?.style === 'forOf' ? 'ForOfStatement' : meta?.style === 'forIn' ? 'ForInStatement' : 'ForStatement';
        const display = create(type, shorten(node.loopHeader ?? node.header, 66), {
          line: node.startLine,
          category: 'control',
          meta: 'loop'
        });
        if (meta?.style === 'classic') {
          if (meta.initText) display.children.push(create('Init', meta.initText, { line: node.startLine, category: 'expression' }));
          if (meta.testText) display.children.push(expressionNode(meta.conditionAST, 'Test'));
          if (meta.updateText) display.children.push(create('Update', meta.updateText, { line: node.startLine, category: 'expression' }));
        } else {
          if (meta?.target) display.children.push(create('Target', meta.target, { line: node.startLine, category: 'expression' }));
          if (meta?.iterableText) display.children.push(expressionNode(meta.iterableAST, 'Iterable'));
        }
        const body = create('Block', 'Loop body', {
          line: node.body?.startLine ?? node.startLine,
          category: 'control',
          meta: `${node.body?.children?.length ?? 0} statements`
        });
        addStatements(body, node.body);
        display.children.push(body);
        return display;
      }
      case 'while':
      case 'do': {
        const display = create(node.type === 'do' ? 'DoWhileStatement' : 'WhileStatement', shorten(node.condition, 66), {
          line: node.startLine,
          category: 'control',
          meta: node.type === 'do' ? 'check after each pass' : 'check before each pass'
        });
        display.children.push(expressionNode(node.conditionAST, 'Test'));
        const body = create('Block', 'Loop body', {
          line: node.body?.startLine ?? node.startLine,
          category: 'control',
          meta: `${node.body?.children?.length ?? 0} statements`
        });
        addStatements(body, node.body);
        display.children.push(body);
        return display;
      }
      case 'switch': {
        const display = create('SwitchStatement', shorten(node.condition, 58), {
          line: node.startLine,
          category: 'control',
          meta: 'multiple cases'
        });
        addStatements(display, node.body);
        return display;
      }
      case 'try': {
        const display = create('TryStatement', 'try', { line: node.startLine, category: 'control', meta: 'protected code' });
        const body = create('Block', 'Try block', { line: node.body.startLine, category: 'control' });
        addStatements(body, node.body);
        display.children.push(body);
        for (const handler of node.handlers ?? []) {
          const handlerNode = create('CatchClause', handler.header ?? handler.type, {
            line: handler.startLine,
            category: 'control',
            meta: handler.type
          });
          addStatements(handlerNode, handler.body);
          display.children.push(handlerNode);
        }
        return display;
      }
      case 'action':
        return actionToDisplay(node);
      default:
        return create(uppercaseType(node.type), node.header ?? '', {
          line: node.startLine,
          category: 'muted'
        });
    }
  }

  function actionToDisplay(node) {
    const action = node.action;
    if (!action) return null;
    switch (action.subtype) {
      case 'import':
        return create('ImportDeclaration', shorten(node.text, 64), {
          line: node.startLine,
          category: 'structure'
        });
      case 'declaration': {
        const display = create('VariableDeclaration', shorten(node.text, 68), {
          line: node.startLine,
          category: 'declaration',
          meta: action.declarationType || 'new name'
        });
        if (action.expressionAST) {
          display.children.push(expressionNode(action.expressionAST, 'Initializer'));
        }
        return display;
      }
      case 'assignment': {
        const display = create('Assignment', shorten(node.text, 68), {
          line: node.startLine,
          category: 'declaration',
          meta: action.operator
        });
        if (action.expressionAST) display.children.push(expressionNode(action.expressionAST, 'Value'));
        return display;
      }
      case 'print': {
        const display = create('PrintStatement', shorten(node.text, 68), {
          line: node.startLine,
          category: 'output',
          meta: 'writes to output'
        });
        for (const arg of action.print?.args ?? []) {
          display.children.push(expressionNode(arg));
        }
        return display;
      }
      case 'return': {
        const display = create('ReturnStatement', shorten(node.text, 68), {
          line: node.startLine,
          category: 'return'
        });
        if (action.expressionAST) display.children.push(expressionNode(action.expressionAST, 'Value'));
        return display;
      }
      case 'break':
      case 'continue':
        return create(action.subtype === 'break' ? 'BreakStatement' : 'ContinueStatement', action.subtype, {
          line: node.startLine,
          category: 'control'
        });
      case 'call': {
        const display = create('ExpressionStatement', shorten(node.text, 68), {
          line: node.startLine,
          category: 'expression'
        });
        display.children.push(expressionNode(action.expressionAST));
        return display;
      }
      default: {
        const display = create('ExpressionStatement', shorten(action.expressionText ?? node.text, 68), {
          line: node.startLine,
          category: 'expression'
        });
        if (action.expressionAST) display.children.push(expressionNode(action.expressionAST));
        return display;
      }
    }
  }

  function expressionNode(ast, overrideType = null, depth = 0) {
    if (!ast) {
      return create(overrideType ?? 'Empty', '—', { category: 'muted' });
    }
    if (depth > 5) {
      return create(overrideType ?? 'Expression', shorten(prettyExpression(ast), 52), { category: 'expression' });
    }
    switch (ast.type) {
      case 'Literal': {
        const label = ast.valueType === 'template'
          ? shorten(ast.raw ?? ast.value, 48)
          : ast.valueType === 'string'
            ? `"${shorten(ast.value, 44)}"`
            : String(ast.value);
        return create(overrideType ?? 'Literal', label, {
          category: 'literal',
          meta: ast.valueType
        });
      }
      case 'Identifier':
        return create(overrideType ?? 'Identifier', ast.name, { category: 'expression' });
      case 'BinaryExpression':
      case 'LogicalExpression': {
        const display = create(overrideType ?? (ast.type === 'LogicalExpression' ? 'LogicalExpression' : 'BinaryExpression'), ast.operator, {
          category: 'expression',
          meta: operatorKind(ast.operator)
        });
        display.children.push(expressionNode(ast.left, 'Left', depth + 1));
        display.children.push(expressionNode(ast.right, 'Right', depth + 1));
        return display;
      }
      case 'UnaryExpression': {
        const display = create(overrideType ?? 'UnaryExpression', ast.operator, { category: 'expression' });
        display.children.push(expressionNode(ast.argument, 'Operand', depth + 1));
        return display;
      }
      case 'UpdateExpression': {
        const display = create(overrideType ?? 'UpdateExpression', `${ast.prefix ? '' : ''}${ast.operator}`, { category: 'expression' });
        display.children.push(expressionNode(ast.argument, 'Target', depth + 1));
        return display;
      }
      case 'AssignmentExpression': {
        const display = create(overrideType ?? 'AssignmentExpression', ast.operator, { category: 'expression' });
        display.children.push(expressionNode(ast.left, 'Target', depth + 1));
        display.children.push(expressionNode(ast.right, 'Value', depth + 1));
        return display;
      }
      case 'CallExpression': {
        const display = create(overrideType ?? 'CallExpression', shorten(expressionLabel(ast), 54), {
          category: 'call',
          meta: `${ast.arguments.length} argument${ast.arguments.length === 1 ? '' : 's'}`
        });
        for (const argument of ast.arguments.slice(0, 5)) {
          display.children.push(expressionNode(argument, 'Argument', depth + 1));
        }
        return display;
      }
      case 'MemberExpression': {
        const display = create(overrideType ?? 'MemberExpression', memberLabel(ast), {
          category: 'expression',
          meta: ast.computed ? 'computed access' : 'property access'
        });
        display.children.push(expressionNode(ast.object, 'Object', depth + 1));
        if (ast.computed) display.children.push(expressionNode(ast.property, 'Index', depth + 1));
        return display;
      }
      case 'ArrayExpression': {
        const display = create(overrideType ?? 'ArrayExpression', `[${ast.elements.length} items]`, {
          category: 'literal',
          meta: 'collection'
        });
        for (const element of ast.elements.slice(0, 6)) {
          display.children.push(expressionNode(element, 'Item', depth + 1));
        }
        return display;
      }
      case 'ObjectExpression': {
        const display = create(overrideType ?? 'ObjectExpression', `{${ast.properties.length} properties}`, {
          category: 'literal',
          meta: 'key / value pairs'
        });
        for (const property of ast.properties.slice(0, 5)) {
          const propertyNode = create('Property', property.key, { category: 'expression' });
          propertyNode.children.push(expressionNode(property.value, 'Value', depth + 1));
          display.children.push(propertyNode);
        }
        return display;
      }
      case 'ConditionalExpression': {
        const display = create(overrideType ?? 'ConditionalExpression', 'condition ? yes : no', {
          category: 'expression',
          meta: 'ternary'
        });
        display.children.push(expressionNode(ast.test, 'Test', depth + 1));
        display.children.push(expressionNode(ast.consequent, 'Then', depth + 1));
        display.children.push(expressionNode(ast.alternate, 'Else', depth + 1));
        return display;
      }
      case 'RawExpression':
        return create(overrideType ?? 'UnparsedExpression', shorten(ast.text, 56), {
          category: 'muted',
          meta: 'shown as written'
        });
      default:
        return create(overrideType ?? uppercaseType(ast.type), shorten(prettyExpression(ast), 52), {
          category: 'expression'
        });
    }
  }

  const rootDisplay = statementToDisplay(analysis.root);
  assignCollapseCounts(rootDisplay);
  return {
    root: rootDisplay,
    count: counter,
    truncated
  };
}

function assignCollapseCounts(node) {
  if (!node) return 0;
  let total = 1;
  for (const child of node.children) total += assignCollapseCounts(child);
  node.descendantCount = total - 1;
  return total;
}

function categoryForType(type) {
  if (['Program', 'ClassDeclaration', 'InterfaceDeclaration', 'ImportDeclaration'].includes(type)) return 'structure';
  if (['FunctionDeclaration', 'Parameter', 'Parameters'].includes(type)) return 'function';
  if (['IfStatement', 'ForStatement', 'ForOfStatement', 'ForInStatement', 'WhileStatement', 'DoWhileStatement'].includes(type)) return 'control';
  if (['VariableDeclaration', 'Assignment'].includes(type)) return 'declaration';
  return 'expression';
}

function paramLabel(param) {
  const parts = [param.name];
  if (param.type) parts.push(`: ${param.type}`);
  if (param.defaultValue) parts.push(`= ${param.defaultValue}`);
  return parts.join(' ');
}

function uppercaseType(type) {
  return String(type ?? 'Node')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^./, (letter) => letter.toUpperCase());
}

function operatorKind(operator) {
  if (['+', '-', '*', '/', '%', '**'].includes(operator)) return 'arithmetic';
  if (['<', '>', '<=', '>=', '==', '===', '!=', '!=='].includes(operator)) return 'comparison';
  if (['&&', '||', 'and', 'or'].includes(operator)) return 'logic';
  return 'operator';
}

function expressionLabel(ast) {
  if (!ast) return 'call';
  if (ast.callee?.type === 'Identifier') {
    return `${ast.callee.name}(${ast.arguments.map(argumentLabel).join(', ')})`;
  }
  if (ast.callee?.type === 'MemberExpression') {
    return `${memberLabel(ast.callee)}(…)`;
  }
  return prettyExpression(ast);
}

function memberLabel(ast) {
  const object = ast.object?.type === 'Identifier' ? ast.object.name : '…';
  if (ast.computed) return `${object}[…]`;
  return `${object}.${ast.property?.name ?? ''}`;
}

function argumentLabel(ast) {
  if (!ast) return '…';
  if (ast.type === 'Literal') {
    if (ast.valueType === 'string') return `"${shorten(ast.value, 20)}"`;
    return String(ast.value);
  }
  if (ast.type === 'Identifier') return ast.name;
  if (ast.type === 'BinaryExpression') return '…';
  return '…';
}

function prettyExpression(ast) {
  if (!ast) return '';
  switch (ast.type) {
    case 'Literal': return ast.raw ?? String(ast.value);
    case 'Identifier': return ast.name;
    case 'MemberExpression': return memberLabel(ast);
    case 'CallExpression': return expressionLabel(ast);
    case 'BinaryExpression':
    case 'LogicalExpression': return `${prettyExpression(ast.left)} ${ast.operator} ${prettyExpression(ast.right)}`;
    case 'UnaryExpression': return `${ast.operator}${prettyExpression(ast.argument)}`;
    case 'ArrayExpression': return `[${ast.elements.map(prettyExpression).join(', ')}]`;
    case 'ObjectExpression': return `{${ast.properties.map((property) => `${property.key}: ${prettyExpression(property.value)}`).join(', ')}}`;
    default: return ast.text ?? '';
  }
}

function shorten(value, limit) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}
