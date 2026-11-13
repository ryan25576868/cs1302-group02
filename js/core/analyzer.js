/**
 * Structural analysis: turns a parsed program into facts the visuals and the
 * beginner guide can use. This layer never executes code.
 */

import { parseProgram, splitTopLevel } from './parser.js';
import { parseExpression, collectIdentifiers } from './expressions.js';
import { highlightLines } from './lexer.js';

export function analyzeSource(source, language) {
  const text = String(source ?? '').replace(/\r\n?/g, '\n');
  const { root, diagnostics, lineCount } = parseProgram(text, language);
  const lines = text.split('\n').map((line, index) => ({
    number: index + 1,
    text: line
  }));

  const analysis = {
    source: text,
    language,
    languageId: language.id,
    root,
    diagnostics,
    lineCount,
    lines,
    highlightedLines: safeHighlightLines(text, language),
    functions: [],
    classes: [],
    assignments: [],
    actionNodes: [],
    metrics: {
      totalLines: lineCount,
      codeLines: 0,
      blankLines: 0,
      commentLines: 0,
      characters: text.length,
      functions: 0,
      classes: 0,
      loops: 0,
      conditions: 0,
      returns: 0,
      assignments: 0,
      maxDepth: 0
    },
    entry: null,
    flowFocus: null,
    parseDiagnostics: diagnostics,
    confidence: 'high'
  };

  const state = {
    assignmentIndex: 0,
    functionCount: 0,
    classCount: 0,
    loopCount: 0,
    ifCount: 0,
    returnCount: 0,
    maxDepth: 0
  };

  annotateContainer(root.body, analysis, language, {
    scopeName: 'Global',
    scopeType: 'global',
    className: null,
    depth: 0
  }, state);

  // Functions and classes were collected while traversing.
  analysis.metrics.functions = analysis.functions.length;
  analysis.metrics.classes = analysis.classes.length;
  analysis.metrics.loops = state.loopCount;
  analysis.metrics.conditions = state.ifCount;
  analysis.metrics.returns = state.returnCount;
  analysis.metrics.assignments = analysis.assignments.length;
  analysis.metrics.maxDepth = state.maxDepth;

  computeLineMetrics(analysis, language);

  // Identify the best starting point for the flow view and the interpreter.
  const mainFunction = analysis.functions.find((fn) => fn.name === 'main') ?? null;
  const topLevelExecutable = root.body.children.filter((child) => isExecutableTopLevel(child));
  let entry;
  if (language.entry === 'main') {
    entry = mainFunction
      ? { kind: 'function', node: mainFunction, name: mainFunction.name, inferred: false }
      : { kind: 'program', node: root, name: 'Program', inferred: true };
  } else if (topLevelExecutable.length > 0 || analysis.functions.length === 0) {
    entry = { kind: 'program', node: root, name: 'Program', inferred: false };
  } else if (mainFunction) {
    entry = { kind: 'function', node: mainFunction, name: mainFunction.name, inferred: false };
  } else {
    entry = { kind: 'function', node: analysis.functions[0], name: analysis.functions[0].name, inferred: true };
  }
  analysis.entry = entry;

  const initialFocus = entry.kind === 'function'
    ? entry.node
    : root;
  analysis.flowFocus = {
    kind: entry.kind,
    node: initialFocus,
    name: initialFocus.type === 'program' ? 'Program' : initialFocus.name
  };

  if (diagnostics.some((diagnostic) => diagnostic.severity === 'warning')) {
    analysis.confidence = 'medium';
  }
  if (analysis.actionNodes.some((node) => node.action?.subtype === 'unknown')) {
    analysis.confidence = analysis.confidence === 'high' ? 'medium' : analysis.confidence;
  }

  // Attach a few presentation facts used by every view.
  analysis.projectTitle = makeProjectTitle(analysis, language);
  analysis.featureSummary = describeFeatures(analysis);
  return analysis;
}

function safeHighlightLines(text, language) {
  try {
    return highlightLines(text, language);
  } catch {
    return text.split('\n');
  }
}

function annotateContainer(block, analysis, language, context, state) {
  if (!block) return;
  for (const child of block.children ?? []) {
    annotateNode(child, analysis, language, context, state);
  }
}

function annotateNode(node, analysis, language, context, state) {
  if (!node) return;
  node.scopeName = context.scopeName;
  node.scopeType = context.scopeType;
  state.maxDepth = Math.max(state.maxDepth, context.depth);

  switch (node.type) {
    case 'function': {
      node.scope = context.className ?? 'Global';
      node.isEntry = false;
      analysis.functions.push(node);
      state.functionCount += 1;
      annotateContainer(node.body, analysis, language, {
        scopeName: context.className ? `${context.className}.${node.name}` : node.name,
        scopeType: 'function',
        className: context.className,
        depth: context.depth + 1
      }, state);
      return;
    }
    case 'class': {
      node.scope = context.className ?? 'Global';
      analysis.classes.push(node);
      state.classCount += 1;
      annotateContainer(node.body, analysis, language, {
        scopeName: `${node.name}`,
        scopeType: 'class',
        className: node.name,
        depth: context.depth + 1
      }, state);
      return;
    }
    case 'if': {
      node.conditionAST = parseExpression(node.condition, language);
      node.scopeName = context.scopeName;
      node.headerLabel = node.keyword === 'elif' ? 'Else if' : 'If';
      state.ifCount += 1;
      annotateContainer(node.consequent, analysis, language, {
        ...context,
        depth: context.depth + 1
      }, state);
      if (node.alternate) {
        annotateContainer(node.alternate, analysis, language, {
          ...context,
          depth: context.depth + 1
        }, state);
      }
      return;
    }
    case 'for': {
      node.loopMeta = analyzeForLoop(node, language);
      node.scopeName = context.scopeName;
      state.loopCount += 1;
      annotateContainer(node.body, analysis, language, {
        ...context,
        depth: context.depth + 1
      }, state);
      return;
    }
    case 'while':
    case 'do': {
      node.conditionAST = parseExpression(node.condition, language);
      node.loopMeta = {
        style: node.type === 'do' ? 'doWhile' : 'while',
        conditionText: node.condition,
        conditionAST: node.conditionAST
      };
      node.scopeName = context.scopeName;
      state.loopCount += 1;
      annotateContainer(node.body, analysis, language, {
        ...context,
        depth: context.depth + 1
      }, state);
      return;
    }
    case 'switch': {
      node.conditionAST = parseExpression(node.condition, language);
      node.scopeName = context.scopeName;
      state.ifCount += 1;
      annotateContainer(node.body, analysis, language, {
        ...context,
        depth: context.depth + 1
      }, state);
      return;
    }
    case 'try': {
      annotateContainer(node.body, analysis, language, {
        ...context,
        depth: context.depth + 1
      }, state);
      for (const handler of node.handlers ?? []) {
        annotateContainer(handler.body, analysis, language, {
          ...context,
          depth: context.depth + 1
        }, state);
      }
      return;
    }
    case 'block': {
      annotateContainer(node, analysis, language, { ...context, depth: context.depth + 1 }, state);
      return;
    }
    case 'action': {
      annotateActionNode(node, analysis, language, context, state);
      return;
    }
    default:
      return;
  }
}

function annotateActionNode(node, analysis, language, context, state) {
  const action = analyseSimpleText(node.text ?? node.header ?? '', language, {
    line: node.startLine,
    kind: node.kind
  });
  node.action = action;
  node.scopeName = context.scopeName;
  node.scopeType = context.scopeType;

  if (action.subtype === 'return' || node.kind === 'return') {
    state.returnCount += 1;
  }

  if (action.subtype === 'declaration' || action.subtype === 'assignment') {
    if (action.assignment) {
      const dependencies = action.expressionAST ? collectIdentifiers(action.expressionAST) : [];
      if (action.operator && action.operator !== '=' && action.targetName) {
        dependencies.push(action.targetName);
      }
      const record = {
        id: `assignment-${++state.assignmentIndex}`,
        nodeId: node.id,
        node,
        line: node.startLine,
        endLine: node.endLine,
        target: action.targetDisplay,
        targetName: action.targetName,
        expressionText: action.expressionText,
        expressionAST: action.expressionAST,
        dependencies,
        operator: action.operator,
        isDeclaration: action.isDeclaration,
        declarationType: action.declarationType,
        scope: context.scopeName,
        scopeType: context.scopeType,
        action
      };
      analysis.assignments.push(record);
      node.assignmentRecord = record;
    }
  }

  analysis.actionNodes.push(node);
}

/** Analyse a single statement, without needing a full parser node. */
export function analyseSimpleText(text, language, options = {}) {
  const trimmed = String(text ?? '').trim();
  const line = options.line ?? 1;
  const base = {
    subtype: 'expression',
    raw: trimmed,
    line
  };
  if (!trimmed) return { ...base, subtype: 'empty' };

  // Imports and environment directives are real statements but not executable.
  if (/^(?:import\b|from\s+\S+\s+import\b|package\b|using\s+namespace\b|#include\b)/.test(trimmed)) {
    return { ...base, subtype: 'import' };
  }
  if (/^(?:\/\/|#|\/\*|\*)/.test(trimmed)) {
    return { ...base, subtype: 'comment' };
  }

  const keyword = trimmed.match(/^([A-Za-z_]\w*)/)?.[1] ?? '';

  if (keyword === 'return' || options.kind === 'return') {
    const expressionText = trimmed.replace(/^return\b/, '').replace(/;$/, '').trim();
    return {
      ...base,
      subtype: 'return',
      expressionText,
      expressionAST: expressionText ? parseExpression(expressionText, language) : null
    };
  }
  if (keyword === 'throw' || keyword === 'raise') {
    const expressionText = trimmed.replace(/^(?:throw|raise)\b/, '').trim();
    return {
      ...base,
      subtype: 'throw',
      expressionText,
      expressionAST: expressionText ? parseExpression(expressionText, language) : null
    };
  }
  if (keyword === 'break') return { ...base, subtype: 'break' };
  if (keyword === 'continue') return { ...base, subtype: 'continue' };
  if (keyword === 'pass') return { ...base, subtype: 'pass' };

  const printResult = detectPrint(trimmed, language);
  if (printResult) {
    return { ...base, ...printResult };
  }

  const assignment = findTopLevelAssignment(trimmed);
  if (assignment) {
    const target = parseAssignmentTarget(assignment.left, language);
    if (target) {
      let expressionText = assignment.right.trim().replace(/;\s*$/, '').trim();
      let expressionAST = null;
      let initializerArray = false;
      if (expressionText) {
        let parseText = expressionText;
        if (language.family === 'clike' && /^\{[\s\S]*\}$/.test(expressionText)) {
          parseText = expressionText.replace(/^\{/, '[').replace(/\}$/, ']');
          initializerArray = true;
        }
        expressionAST = parseExpression(parseText, language);
      }
      const isCompound = assignment.operator !== '=';
      return {
        ...base,
        subtype: target.isDeclaration ? 'declaration' : 'assignment',
        assignment: true,
        targetDisplay: target.targetDisplay,
        targetName: target.targetName,
        targetChain: target.targetChain,
        isDeclaration: target.isDeclaration,
        isUpdate: !target.isDeclaration || isCompound,
        declarationType: target.declarationType,
        operator: assignment.operator,
        expressionText,
        expressionAST,
        initializerArray
      };
    }
  }

  const noInitDeclaration = detectDeclarationWithoutInitializer(trimmed, language);
  if (noInitDeclaration) {
    return {
      ...base,
      subtype: 'declaration',
      assignment: true,
      targetDisplay: noInitDeclaration.name,
      targetName: noInitDeclaration.name,
      targetChain: noInitDeclaration.name,
      isDeclaration: true,
      isUpdate: false,
      declarationType: noInitDeclaration.type,
      operator: null,
      expressionText: null,
      expressionAST: null
    };
  }

  const expressionAST = parseExpression(trimmed.replace(/;\s*$/, ''), language);
  if (expressionAST?.type === 'CallExpression') {
    return {
      ...base,
      subtype: 'call',
      expressionText: trimmed.replace(/;\s*$/, ''),
      expressionAST,
      calleeName: calleeName(expressionAST.callee)
    };
  }
  if (expressionAST?.type === 'UpdateExpression') {
    return {
      ...base,
      subtype: 'update',
      expressionText: trimmed.replace(/;\s*$/, ''),
      expressionAST
    };
  }
  return {
    ...base,
    subtype: 'expression',
    expressionText: trimmed.replace(/;\s*$/, ''),
    expressionAST
  };
}

function calleeName(callee) {
  if (!callee) return '';
  if (callee.type === 'Identifier') return callee.name;
  if (callee.type === 'MemberExpression' && !callee.computed) {
    return `${calleeName(callee.object)}.${callee.property?.name ?? ''}`;
  }
  return '';
}

function detectPrint(text, language) {
  if (language.id === 'cpp' && /^(?:std::)?(?:cout|cerr)\b/.test(text)) {
    return detectCppCout(text);
  }
  const ast = parseExpression(text.replace(/;\s*$/, ''), language);
  if (ast?.type !== 'CallExpression') return null;
  const name = calleeName(ast.callee);
  let printKind = null;
  if (['javascript', 'typescript'].includes(language.id) && ['console.log', 'console.info', 'console.warn', 'console.error'].includes(name)) {
    printKind = 'console';
  } else if (language.id === 'python' && name === 'print') {
    printKind = 'python';
  } else if (language.id === 'java' && ['System.out.println', 'System.out.print', 'System.err.println', 'System.err.print'].includes(name)) {
    printKind = name;
  } else if (language.id === 'c' && ['printf', 'puts', 'putchar'].includes(name)) {
    printKind = name;
  } else if (language.id === 'cpp' && ['printf', 'puts', 'putchar'].includes(name)) {
    printKind = name;
  }
  if (!printKind) return null;
  const addNewline = !['System.out.print', 'System.err.print', 'putchar'].includes(printKind);
  return {
    subtype: 'print',
    expressionText: text,
    print: {
      kind: printKind,
      args: ast.arguments,
      argTexts: splitTopLevel(extractTopLevelCallArguments(text), ','),
      addNewline,
      separator: printKind === 'printf' ? '' : ' ',
      calleeName: name,
      callAST: ast
    }
  };
}

function extractTopLevelCallArguments(text) {
  const open = text.indexOf('(');
  if (open === -1) return '';
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let i = open; i < text.length; i += 1) {
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
    if (ch === '(') depth += 1;
    else if (ch === ')') {
      depth -= 1;
      if (depth === 0) return text.slice(open + 1, i);
    }
  }
  return text.slice(open + 1);
}

function detectCppCout(text) {
  const match = text.match(/^(?:std::)?(cout|cerr)\b([\s\S]*)$/);
  if (!match) return null;
  const rest = match[2].trim();
  if (!rest.startsWith('<<')) return null;
  const segments = splitTopLevelDelimiter(rest, '<<')
    .map((segment) => segment.trim())
    .filter(Boolean);
  const args = [];
  const argTexts = [];
  let addNewline = false;
  for (const segment of segments) {
    if (/^(?:std::)?endl$/.test(segment)) {
      addNewline = true;
      continue;
    }
    args.push(parseExpression(segment, { id: 'cpp', family: 'clike' }));
    argTexts.push(segment);
  }
  return {
    subtype: 'print',
    expressionText: text,
    print: {
      kind: 'cout',
      args,
      argTexts,
      addNewline,
      separator: '',
      calleeName: match[1],
      callAST: null
    }
  };
}

function findTopLevelAssignment(text) {
  let quote = null;
  let escaped = false;
  let paren = 0;
  let bracket = 0;
  let brace = 0;
  const compound = ['>>=', '<<=', '**=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^='];

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
    if (ch === '(') paren += 1;
    else if (ch === ')') paren = Math.max(0, paren - 1);
    else if (ch === '[') bracket += 1;
    else if (ch === ']') bracket = Math.max(0, bracket - 1);
    else if (ch === '{') brace += 1;
    else if (ch === '}') brace = Math.max(0, brace - 1);

    if (paren === 0 && bracket === 0 && brace === 0) {
      const matched = compound.find((operator) => text.startsWith(operator, i));
      if (matched) {
        return {
          operator: matched,
          left: text.slice(0, i).trim(),
          right: text.slice(i + matched.length)
        };
      }
      if (ch === '=') {
        const previous = text[i - 1];
        const next = text[i + 1];
        if (next === '=' || next === '>' || previous === '=' || previous === '!' || previous === '<' || previous === '>') {
          continue;
        }
        return {
          operator: '=',
          left: text.slice(0, i).trim(),
          right: text.slice(i + 1)
        };
      }
    }
  }
  return null;
}

function parseAssignmentTarget(leftRaw, language) {
  let left = leftRaw.trim();
  if (!left) return null;
  let declarationType = '';
  let isDeclaration = false;

  if (/^(?:export\s+)?(?:let|const|var)\b/.test(left)) {
    isDeclaration = true;
    left = left.replace(/^(?:export\s+)?(?:let|const|var)\s+/, '');
  }

  // TypeScript / Python type annotation (strip only a top-level colon).
  const colon = findTopLevelChar(left, ':');
  if (colon !== -1) {
    const before = left.slice(0, colon).trim();
    const after = left.slice(colon + 1).trim();
    if (before && !before.includes('?')) {
      declarationType = declarationType || after;
      left = before + (before.endsWith('?') ? '' : '');
      isDeclaration = isDeclaration || language.id === 'typescript';
    }
  }

  left = left.replace(/\s*!\s*$/, '').trim();

  if (/^[\[{]/.test(left)) {
    return null;
  }

  const chainMatch = left.match(/([A-Za-z_$][\w$]*(?:\s*(?:\[[^\]]*\]|\.[A-Za-z_$][\w$]*))*)\s*$/);
  if (!chainMatch) return null;
  let targetChain = chainMatch[1].replace(/\s+/g, '');
  const prefix = left.slice(0, chainMatch.index).trim();
  const firstIdentifier = targetChain.match(/^[A-Za-z_$][\w$]*/)?.[0] ?? targetChain;

  if (language.family === 'clike') {
    const prefixClean = prefix
      .replace(/\b(?:public|private|protected|static|final|const|volatile|transient|abstract|synchronized|native|strictfp|export|declare|readonly|auto|register|extern|unsigned|signed|long|short)\b/g, ' ')
      .replace(/[&*]/g, ' ')
      .replace(/\[\s*\]/g, ' ')
      .trim();
    if (prefixClean && /[A-Za-z_$]/.test(prefixClean)) {
      isDeclaration = true;
      declarationType = declarationType || prefixClean;
    }
    if (/^\s*(?:const|static|final|public|private|protected)\b/.test(leftRaw) && prefixClean) {
      isDeclaration = true;
    }
  }

  // In a typed declaration such as `double prices[3]`, the brackets describe
  // the storage, not an index being written. Keep the displayed target clean.
  if (isDeclaration && targetChain !== firstIdentifier) {
    targetChain = targetChain.replace(/\[[^\]]*\]$/, '');
  }

  return {
    targetDisplay: targetChain,
    targetName: firstIdentifier,
    targetChain,
    isDeclaration,
    declarationType: cleanType(declarationType)
  };
}

function cleanType(type) {
  return String(type ?? '')
    .replace(/\b(?:public|private|protected|static|final|const|volatile|transient|abstract|readonly|export|declare)\b/g, ' ')
    .replace(/[&*]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function findTopLevelChar(text, target) {
  let quote = null;
  let escaped = false;
  let paren = 0;
  let bracket = 0;
  let brace = 0;
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
    if (ch === '(') paren += 1;
    else if (ch === ')') paren = Math.max(0, paren - 1);
    else if (ch === '[') bracket += 1;
    else if (ch === ']') bracket = Math.max(0, bracket - 1);
    else if (ch === '{') brace += 1;
    else if (ch === '}') brace = Math.max(0, brace - 1);
    if (ch === target && paren === 0 && bracket === 0 && brace === 0) return i;
  }
  return -1;
}

function detectDeclarationWithoutInitializer(text, language) {
  const clean = text.trim().replace(/;$/, '').trim();
  if (!clean || clean.includes('=') || clean.includes('(') || clean.includes('{')) return null;

  if (['javascript', 'typescript'].includes(language.id)) {
    const match = clean.match(/^(?:export\s+)?(?:let|const|var)\s+([A-Za-z_$][\w$]*)\s*(?::\s*([^=]+))?$/);
    if (match) return { name: match[1], type: cleanType(match[2] ?? '') };
    return null;
  }
  if (language.family === 'python') return null;

  const match = clean.match(
    /^(?:(?:const|static|final|volatile|unsigned|signed|long|short|public|private|protected|auto|register|extern|readonly)\s+)*(?:[A-Za-z_$][\w$]*(?:::[A-Za-z_$][\w$]*)*(?:\s*<[^;>]*>)?(?:\s*\[\s*\w*\s*\])?)(?:\s*[*&])?\s+([A-Za-z_$][\w$]*)(?:\s*\[\s*\w*\s*\])?$/
  );
  if (!match) return null;
  const before = clean.slice(0, clean.lastIndexOf(match[1])).trim();
  if (!/[A-Za-z_$]/.test(before)) return null;
  return { name: match[1], type: cleanType(before) };
}

function analyzeForLoop(node, language) {
  const header = node.loopHeader ?? '';
  if (language.family === 'python') {
    const split = findTopLevelWord(header, 'in');
    if (split !== -1) {
      const targetText = header.slice(0, split).trim();
      const iterableText = header.slice(split + 2).trim();
      const target = cleanLoopTarget(targetText);
      return {
        style: 'forIn',
        target,
        targetText,
        iterableText,
        iterableAST: parseExpression(iterableText, language),
        conditionAST: null
      };
    }
    return {
      style: 'forUnsupported',
      raw: header,
      iterableText: header,
      iterableAST: parseExpression(header, language)
    };
  }

  const classicParts = splitTopLevel(header, ';');
  if (classicParts.length >= 3) {
    const [initText, testText, updateText] = [
      classicParts[0].trim(),
      classicParts.slice(1, -1).join(';').trim(),
      classicParts.at(-1).trim()
    ];
    return {
      style: 'classic',
      initText,
      testText,
      updateText,
      initAction: initText ? analyseSimpleText(initText, language) : null,
      conditionAST: testText ? parseExpression(testText, language) : { type: 'Literal', valueType: 'boolean', value: true, raw: 'true' },
      updateAction: updateText ? analyseSimpleText(updateText, language) : null,
      updateAST: updateText ? parseExpression(updateText, language) : null,
      conditionText: testText
    };
  }

  const rangeSplit = language.id === 'javascript' || language.id === 'typescript'
    ? findTopLevelRangeWord(header)
    : findTopLevelChar(header, ':');
  if (rangeSplit !== -1) {
    let keyword = '';
    let splitStart = rangeSplit;
    let splitLength = 1;
    if (language.id === 'javascript' || language.id === 'typescript') {
      keyword = header.slice(rangeSplit.wordStart, rangeSplit.wordEnd);
      splitStart = rangeSplit.wordStart;
      splitLength = rangeSplit.wordEnd - rangeSplit.wordStart;
    }
    const targetText = header.slice(0, splitStart).trim();
    const iterableText = header.slice(splitStart + splitLength).trim();
    return {
      style: keyword === 'in' ? 'forIn' : 'forOf',
      target: cleanLoopTarget(targetText),
      targetText,
      iterableText,
      iterableAST: parseExpression(iterableText, language),
      conditionAST: null
    };
  }

  return {
    style: 'forUnsupported',
    raw: header,
    iterableText: header,
    iterableAST: parseExpression(header, language)
  };
}

function findTopLevelWord(header, word) {
  let depth = 0;
  let quote = null;
  for (let i = 0; i < header.length; i += 1) {
    const ch = header[i];
    if (quote) {
      if (ch === '\\') i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch;
      continue;
    }
    if ('([{'.includes(ch)) depth += 1;
    else if (')]}'.includes(ch)) depth = Math.max(0, depth - 1);
    if (depth === 0 && header.slice(i, i + word.length) === word) {
      const before = header[i - 1];
      const after = header[i + word.length];
      if (!/[A-Za-z_$]/.test(before ?? '') && !/[A-Za-z_$]/.test(after ?? '')) return i;
    }
  }
  return -1;
}

function findTopLevelRangeWord(header) {
  for (const word of ['of', 'in']) {
    const index = findTopLevelWord(header, word);
    if (index !== -1) return { wordStart: index, wordEnd: index + word.length };
  }
  return -1;
}

function cleanLoopTarget(target) {
  let value = String(target ?? '').trim();
  value = value.replace(/^(?:const|let|var)\s+/, '');
  value = value.replace(/^(?:(?:final|const|static)\s+)*[A-Za-z_$][\w$]*(?:(?:::|\.)[A-Za-z_$][\w$]*)*(?:\s*<[^>]*>)?(?:\s*\[\s*\])?(?:\s*[*&]+)?\s+/, '');
  value = value.replace(/^\.\.\./, '');
  return value.trim();
}

function computeLineMetrics(analysis, language) {
  let codeLines = 0;
  let blankLines = 0;
  let commentLines = 0;
  let inBlockComment = false;
  const lineComment = language.lineComment;
  for (const line of analysis.lines) {
    const trimmed = line.text.trim();
    if (!trimmed) {
      blankLines += 1;
      continue;
    }
    if (inBlockComment) {
      commentLines += 1;
      if (trimmed.includes('*/')) inBlockComment = false;
      continue;
    }
    if (language.blockComment && trimmed.startsWith(language.blockComment[0])) {
      commentLines += 1;
      if (!trimmed.includes(language.blockComment[1])) inBlockComment = true;
      continue;
    }
    if (language.family === 'python' && trimmed.startsWith('#')) {
      commentLines += 1;
      continue;
    }
    if (lineComment && trimmed.startsWith(lineComment)) {
      commentLines += 1;
      continue;
    }
    codeLines += 1;
  }
  analysis.metrics.codeLines = codeLines;
  analysis.metrics.blankLines = blankLines;
  analysis.metrics.commentLines = commentLines;
}

function isExecutableTopLevel(node) {
  if (!node) return false;
  if (node.type === 'function' || node.type === 'class') return false;
  if (node.type === 'action') {
    return !['import', 'empty', 'comment'].includes(node.action?.subtype);
  }
  if (node.type === 'block') return node.body?.children?.some(isExecutableTopLevel);
  return ['if', 'for', 'while', 'do', 'switch', 'try'].includes(node.type);
}

function makeProjectTitle(analysis, language) {
  const names = analysis.functions.map((fn) => fn.name).filter((name) => name && name !== 'main');
  if (names.length) return `${language.name} · ${names[0]} and friends`;
  return `${language.name} exploration`;
}

function describeFeatures(analysis) {
  const features = [];
  if (analysis.functions.length) features.push(`${analysis.functions.length} function${analysis.functions.length === 1 ? '' : 's'}`);
  if (analysis.metrics.loops) features.push(`${analysis.metrics.loops} loop${analysis.metrics.loops === 1 ? '' : 's'}`);
  if (analysis.metrics.conditions) features.push(`${analysis.metrics.conditions} decision${analysis.metrics.conditions === 1 ? '' : 's'}`);
  if (!features.length) features.push('straight-line logic');
  return features.join(' · ');
}

export function splitTopLevelDelimiter(text, delimiter) {
  const parts = [];
  let current = '';
  let quote = null;
  let escaped = false;
  let paren = 0;
  let bracket = 0;
  let brace = 0;
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
    if (ch === '(') paren += 1;
    else if (ch === ')') paren = Math.max(0, paren - 1);
    else if (ch === '[') bracket += 1;
    else if (ch === ']') bracket = Math.max(0, bracket - 1);
    else if (ch === '{') brace += 1;
    else if (ch === '}') brace = Math.max(0, brace - 1);
    if (paren === 0 && bracket === 0 && brace === 0 && text.startsWith(delimiter, i)) {
      parts.push(current);
      current = '';
      i += delimiter.length - 1;
      continue;
    }
    current += ch;
  }
  parts.push(current);
  return parts;
}

export function getFlowFoci(analysis) {
  const foci = [];
  if (analysis.entry?.kind === 'program') {
    foci.push({ id: 'program', label: 'Whole program', node: analysis.root, kind: 'program' });
  }
  const functions = [...analysis.functions];
  if (analysis.entry?.kind === 'function') {
    functions.sort((a, b) => {
      if (a === analysis.entry.node) return -1;
      if (b === analysis.entry.node) return 1;
      return a.startLine - b.startLine;
    });
  }
  for (const fn of functions) {
    foci.push({
      id: `function:${fn.id}`,
      label: `${fn.name}(${fn.params.map((param) => param.name).join(', ')})`,
      node: fn,
      kind: 'function'
    });
  }
  if (!foci.length) {
    foci.push({ id: 'program', label: 'Whole program', node: analysis.root, kind: 'program' });
  }
  return foci;
}

export function getFunctionForLine(analysis, line) {
  return analysis.functions
    .filter((fn) => line >= fn.startLine && line <= fn.endLine)
    .sort((a, b) => (a.endLine - a.startLine) - (b.endLine - b.startLine))[0] ?? null;
}
