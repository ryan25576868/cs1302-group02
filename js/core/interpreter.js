/**
 * Prism's safe trace interpreter.
 *
 * It walks the structural tree and evaluates a deliberately small subset of
 * each language. It never calls eval(), never loads code into the browser's
 * engine, and refuses to guess when a condition cannot be evaluated. Every
 * trace is bounded so an accidental infinite loop cannot freeze the page.
 */

import { parseExpression, collectIdentifiers } from './expressions.js';

const MAX_STEPS = 420;
const MAX_LOOP_ITERATIONS = 80;
const MAX_CALL_DEPTH = 24;
const MAX_ARRAY_ITEMS = 500;

const UNKNOWN_TAG = 'unknown';
const UNINITIALIZED_TAG = 'uninitialized';

function unknownValue(text = '', reason = '') {
  return { __prism: UNKNOWN_TAG, text, reason };
}

function uninitializedValue(type = '') {
  return { __prism: UNINITIALIZED_TAG, declaredType: type };
}

function isUnknown(value) {
  return !!value && typeof value === 'object' && value.__prism === UNKNOWN_TAG;
}

function isUninitialized(value) {
  return !!value && typeof value === 'object' && value.__prism === UNINITIALIZED_TAG;
}

function isUserFunction(value) {
  return !!value && typeof value === 'object' && value.__prism === 'function';
}

function isBuiltin(value) {
  return !!value && typeof value === 'object' && value.__prism === 'builtin';
}

class ReturnSignal {
  constructor(value) {
    this.value = value;
  }
}
class BreakSignal {}
class ContinueSignal {}
class UnsupportedSignal extends Error {
  constructor(message, line) {
    super(message);
    this.line = line;
  }
}
class TraceLimitSignal extends Error {
  constructor(message, line) {
    super(message);
    this.line = line;
  }
}

class Environment {
  constructor(parent = null, name = 'Global', kind = 'global') {
    this.parent = parent;
    this.name = name;
    this.kind = kind;
    this.bindings = new Map();
  }

  define(name, value, meta = {}) {
    const existing = this.bindings.get(name);
    const binding = {
      name,
      value,
      hidden: meta.hidden ?? false,
      scope: this.name,
      scopeKind: this.kind,
      order: existing?.order ?? meta.order ?? nextBindingOrder(),
      declaredType: meta.declaredType ?? existing?.declaredType ?? '',
      line: meta.line ?? existing?.line ?? null,
      kind: meta.kind ?? existing?.kind ?? 'variable'
    };
    this.bindings.set(name, binding);
    return binding;
  }

  find(name) {
    if (this.bindings.has(name)) return { env: this, binding: this.bindings.get(name) };
    return this.parent?.find(name) ?? null;
  }

  get(name) {
    return this.find(name)?.binding?.value;
  }

  has(name) {
    return !!this.find(name);
  }

  assign(name, value, meta = {}) {
    if (meta.isDeclaration) {
      return this.define(name, value, meta);
    }
    const found = this.find(name);
    if (!found || found.binding.hidden) {
      return this.define(name, value, meta);
    }
    found.binding.value = value;
    if (meta.declaredType) found.binding.declaredType = meta.declaredType;
    if (meta.line) found.binding.line = meta.line;
    return found.binding;
  }

  visibleBindings() {
    const result = [];
    const seen = new Set();
    let env = this;
    while (env) {
      for (const [name, binding] of env.bindings) {
        if (seen.has(name)) continue;
        seen.add(name);
        if (!binding.hidden) result.push(binding);
      }
      env = env.parent;
    }
    return result.sort((a, b) => a.order - b.order);
  }
}

let bindingCounter = 0;
function nextBindingOrder() {
  bindingCounter += 1;
  return bindingCounter;
}

/* -------------------------------------------------------------------------- */
/* Public entry point                                                         */
/* -------------------------------------------------------------------------- */

export function simulate(analysis, options = {}) {
  const interpreter = new Interpreter(analysis, options);
  return interpreter.run();
}

class Interpreter {
  constructor(analysis, options) {
    this.analysis = analysis;
    this.language = analysis.language;
    this.options = options;
    this.steps = [];
    this.events = [];
    this.output = '';
    this.warnings = [];
    this.warningKeys = new Set();
    this.frames = [];
    this.stepsLimit = options.maxSteps ?? MAX_STEPS;
    this.loopLimit = options.maxLoopIterations ?? MAX_LOOP_ITERATIONS;
    this.callLimit = options.maxCallDepth ?? MAX_CALL_DEPTH;
    this.complete = true;
    this.stoppedReason = null;
    this.currentLine = 1;
    this.globalEnv = new Environment(null, 'Global', 'global');
    this.entryEnv = null;
    this.lastSnapshot = new Map();
    this.entryName = analysis.entry?.name ?? 'Program';
    this.functionCallCount = 0;
    this.loopIterationCount = 0;
  }

  run() {
    installBuiltins(this.globalEnv);
    this.registerFunctions();
    this.emit({
      line: this.analysis.entry?.kind === 'function' ? this.analysis.entry.node.startLine : firstExecutableLine(this.analysis),
      kind: 'start',
      title: this.analysis.entry?.kind === 'function' ? `Start ${this.entryName}()` : 'Program starts',
      detail:
        'This is a safe simulated run. Prism follows the code locally; your browser never executes it.',
      env: this.globalEnv
    });

    try {
      if (this.analysis.entry.kind === 'function') {
        this.invokeEntryFunction(this.analysis.entry.node);
      } else {
        this.executeBlock(this.analysis.root.body, this.globalEnv);
      }
      this.emit({
        line: lastCodeLine(this.analysis),
        kind: 'end',
        title: 'Run complete',
        detail: this.output
          ? 'The program finished. The final output is shown in the terminal.'
          : 'The program finished without printing anything.',
        env: this.entryEnv ?? this.globalEnv,
        force: true
      });
    } catch (error) {
      if (error instanceof UnsupportedSignal) {
        this.markIncomplete(error.message, error.line);
      } else if (error instanceof TraceLimitSignal) {
        this.markIncomplete(error.message, error.line);
      } else if (error instanceof ReturnSignal) {
        this.markIncomplete('The program returned before reaching the end.', this.currentLine);
      } else if (error instanceof BreakSignal || error instanceof ContinueSignal) {
        this.markIncomplete('A break or continue appeared outside a loop.', this.currentLine);
      } else {
        this.markIncomplete(
          `The simulated run stopped at line ${this.currentLine}. ${cleanErrorMessage(error)}`,
          this.currentLine
        );
      }
      if (error?.line) this.currentLine = error.line;
      this.emit({
        line: this.currentLine,
        kind: 'stopped',
        title: 'Trace paused',
        detail: 'Some parts of this program are outside the safe interpreter’s supported subset. The diagrams and guide still work.',
        env: this.entryEnv ?? this.globalEnv,
        force: true
      });
    }

    const lastStateEnv = this.entryEnv ?? this.globalEnv;
    const finalVars = snapshotEnvironment(lastStateEnv, this.language, new Map());
    return {
      steps: this.steps,
      events: this.events,
      output: this.output,
      warnings: this.warnings,
      complete: this.complete && this.warnings.length === 0,
      stoppedReason: this.stoppedReason,
      entryName: this.entryName,
      functionCalls: this.functionCallCount,
      iterations: this.loopIterationCount,
      finalVars,
      callStackSupported: true,
      interpreter: 'Prism safe trace'
    };
  }

  registerFunctions() {
    for (const fn of this.analysis.functions) {
      this.globalEnv.define(fn.name, {
        __prism: 'function',
        node: fn,
        closure: this.globalEnv
      }, { hidden: true, kind: 'function' });
    }
  }

  invokeEntryFunction(fn) {
    if (!fn) {
      throw new UnsupportedSignal('No entry function was found. Add a main() function or some top-level code.', 1);
    }
    const args = [];
    for (let index = 0; index < fn.params.length; index += 1) {
      const param = fn.params[index];
      if (index === 0 && isMainArgsParameter(param) && this.language.entry === 'main') {
        args.push([]);
      } else {
        args.push(undefined);
      }
    }
    this.callUserFunction(fn, args, this.globalEnv, {
      callLine: fn.startLine,
      isEntry: true
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Steps and state capture                                                */
  /* ---------------------------------------------------------------------- */

  emit({ line, endLine = line, kind = 'step', title, detail, env, extra = null, force = false }) {
    if (!force && this.steps.length >= this.stepsLimit) {
      throw new TraceLimitSignal(
        `The trace reached its ${this.stepsLimit}-step limit. Narrow the code to follow every detail.`,
        line
      );
    }
    const safeLine = Math.max(1, Math.min(Number(line) || 1, this.analysis.lineCount));
    const safeEnd = Math.max(safeLine, Math.min(Number(endLine) || safeLine, this.analysis.lineCount));
    const previousOutput = this.steps.at(-1)?.output ?? '';
    const vars = snapshotEnvironment(env ?? this.globalEnv, this.language, this.lastSnapshot);
    const callStack = this.frames.map((frame) => ({ name: frame.name, line: frame.line }));
    const code = this.analysis.lines
      .slice(safeLine - 1, Math.min(this.analysis.lineCount, safeEnd))
      .map((item) => item.text)
      .join('\n');
    const step = {
      index: this.steps.length,
      line: safeLine,
      endLine: safeEnd,
      kind,
      title,
      detail,
      vars,
      output: this.output,
      outputDelta: this.output.slice(previousOutput.length),
      callStack,
      scope: this.frames.at(-1)?.name ?? 'Global',
      code,
      extra
    };
    this.steps.push(step);
    this.lastSnapshot = new Map(vars.map((variable) => [variable.name, `${variable.type}:${variable.display}`]));
    return step;
  }

  markIncomplete(message, line) {
    this.complete = false;
    this.stoppedReason = message;
    const key = `${line}:${message}`;
    if (!this.warningKeys.has(key)) {
      this.warningKeys.add(key);
      this.warnings.push({ line, message });
    }
  }

  warn(message, line = this.currentLine, markIncomplete = true) {
    if (markIncomplete) {
      this.complete = false;
    }
    const key = `${line}:${message}`;
    if (this.warningKeys.has(key)) return;
    this.warningKeys.add(key);
    this.warnings.push({ line, message });
  }

  /* ---------------------------------------------------------------------- */
  /* Statements                                                             */
  /* ---------------------------------------------------------------------- */

  executeBlock(block, env) {
    for (const node of block?.children ?? []) {
      this.executeStatement(node, env);
    }
  }

  executeStatement(node, env) {
    if (!node) return;
    this.currentLine = node.startLine;

    switch (node.type) {
      case 'function':
        // Registered up-front so calls work regardless of declaration order.
        return;
      case 'class':
      case 'import':
        return;
      case 'action':
        this.executeAction(node, env);
        return;
      case 'if':
        this.executeIf(node, env);
        return;
      case 'for':
        this.executeFor(node, env);
        return;
      case 'while':
        this.executeWhile(node, env);
        return;
      case 'do':
        this.executeDoWhile(node, env);
        return;
      case 'switch':
        throw new UnsupportedSignal('switch statements are not supported by Live Trace yet. The other views show the full structure.', node.startLine);
      case 'try':
        throw new UnsupportedSignal('try / catch is not supported by Live Trace yet. The other views show the full structure.', node.startLine);
      case 'block':
        this.executeBlock(node.body, env);
        return;
      default:
        this.warn(`A ${node.type} statement is not supported by Live Trace.`, node.startLine);
        return;
    }
  }

  executeAction(node, env) {
    const action = node.action;
    if (!action) return;
    switch (action.subtype) {
      case 'import':
      case 'comment':
      case 'empty':
      case 'pass':
        return;
      case 'declaration':
      case 'assignment':
        this.performAssignment(action, env, node);
        return;
      case 'print':
        this.performPrint(action, env, node);
        return;
      case 'return': {
        let value = undefined;
        if (action.expressionAST) {
          value = this.evaluate(action.expressionAST, env);
        }
        this.emit({
          line: node.startLine,
          endLine: node.endLine,
          kind: 'return',
          title: value === undefined ? 'Return from this function' : `Return ${formatValue(value, this.language)}`,
          detail:
            'A return hands this value back to the code that called the function and stops the function immediately.',
          env
        });
        throw new ReturnSignal(value);
      }
      case 'break':
        this.emit({
          line: node.startLine,
          kind: 'break',
          title: 'Leave the loop',
          detail: 'break jumps out of the nearest loop right away.',
          env
        });
        throw new BreakSignal();
      case 'continue':
        this.emit({
          line: node.startLine,
          kind: 'continue',
          title: 'Skip to the next iteration',
          detail: 'continue jumps to the next loop check instead of finishing this pass.',
          env
        });
        throw new ContinueSignal();
      case 'throw': {
        const value = action.expressionAST ? this.evaluate(action.expressionAST, env) : undefined;
        throw new UnsupportedSignal(`A thrown error interrupted the trace${value !== undefined ? `: ${formatValue(value, this.language)}` : '.'}`, node.startLine);
      }
      case 'call':
        this.executeCallAction(action, env, node);
        return;
      case 'update':
        this.executeUpdateAction(action, env, node);
        return;
      case 'expression':
      default:
        if (action.expressionAST) {
          this.evaluate(action.expressionAST, env);
        } else if (action.raw) {
          this.warn('This statement is outside the trace interpreter’s supported subset.', node.startLine);
        }
        return;
    }
  }

  performAssignment(action, env, node, options = {}) {
    const emitStep = options.emitStep !== false;
    const silentEvent = options.recordEvent !== false;
    const line = node?.startLine ?? action.line ?? this.currentLine;
    let expressionValue;
    let expressionDisplay = action.expressionText ?? '';

    if (action.expressionAST) {
      expressionValue = this.evaluate(action.expressionAST, env);
    } else {
      expressionValue = uninitializedValue(action.declarationType);
    }

    let value = expressionValue;
    let beforeValue;
    if (action.operator && action.operator !== '=') {
      const current = this.readTarget(action.targetChain ?? action.targetName, env, { quiet: true });
      beforeValue = current;
      value = applyBinaryOperator(
        action.operator.slice(0, -1),
        current,
        expressionValue,
        this.language,
        (message) => this.warn(message, line)
      );
    } else if (!action.isDeclaration) {
      beforeValue = this.readTarget(action.targetChain ?? action.targetName, env, { quiet: true });
    }

    this.writeTarget(action, value, env, line);

    const afterValue = this.readTarget(action.targetChain ?? action.targetName, env);
    const display = formatValue(afterValue, this.language);
    const previousDisplay = beforeValue === undefined ? null : formatValue(beforeValue, this.language);
    const title = action.isDeclaration
      ? `Create ${action.targetDisplay ?? action.targetName}`
      : action.operator && action.operator !== '='
        ? `Update ${action.targetDisplay ?? action.targetName}`
        : `Set ${action.targetDisplay ?? action.targetName}`;
    const detail = buildAssignmentDetail(action, beforeValue, afterValue, display, previousDisplay, this.language);

    const dependencies = action.expressionAST ? collectIdentifiers(action.expressionAST) : [];
    if (action.operator && action.operator !== '=' && action.targetName) {
      dependencies.push(action.targetName);
    }
    if (emitStep) {
      const step = this.emit({
        line,
        endLine: node?.endLine ?? line,
        kind: 'assign',
        title,
        detail,
        env,
        extra: {
          target: action.targetDisplay ?? action.targetName,
          value: display
        }
      });
      if (silentEvent) {
        this.recordEvent({
          kind: 'assignment',
          line,
          target: action.targetDisplay ?? action.targetName,
          name: action.targetName,
          expressionText: action.expressionText,
          operator: action.operator,
          value: display,
          valueType: typeOfValue(afterValue),
          scope: this.frames.at(-1)?.name ?? 'Global',
          dependencies,
          stepIndex: step.index
        });
      }
    } else if (silentEvent) {
      this.recordEvent({
        kind: 'assignment',
        line,
        target: action.targetDisplay ?? action.targetName,
        name: action.targetName,
        expressionText: action.expressionText,
        operator: action.operator,
        value: display,
        valueType: typeOfValue(afterValue),
        scope: this.frames.at(-1)?.name ?? 'Global',
        dependencies,
        stepIndex: Math.max(0, this.steps.length - 1),
        silent: true
      });
    }

    return { value: afterValue, display, beforeValue };
  }

  executeUpdateAction(action, env, node) {
    if (!action.expressionAST) return;
    this.evaluate(action.expressionAST, env);
    this.emit({
      line: node.startLine,
      kind: 'update',
      title: 'Update a value',
      detail: 'The value was increased or decreased using the ++ or -- shorthand.',
      env
    });
  }

  executeCallAction(action, env, node) {
    const beforeCalls = this.functionCallCount;
    const result = this.evaluate(action.expressionAST, env);
    if (this.functionCallCount === beforeCalls) {
      this.emit({
        line: node.startLine,
        endLine: node.endLine,
        kind: 'call',
        title: `Call ${action.calleeName ?? 'a function'}`,
        detail: result === undefined ? 'The call finished without a return value.' : `The call returned ${formatValue(result, this.language)}.`,
        env
      });
    }
  }

  executeIf(node, env) {
    const value = this.evaluate(node.conditionAST, env);
    if (isUnknown(value)) {
      this.warn(`Could not evaluate the condition “${node.condition}”. The trace stopped rather than guessing.`, node.startLine, false);
      throw new UnsupportedSignal(`Could not evaluate the condition “${node.condition}”.`, node.startLine);
    }
    const truthy = toBoolean(value);
    this.emit({
      line: node.startLine,
      kind: 'condition',
      title: `If check: ${truncateCode(node.condition, 56)} → ${truthy ? 'true' : 'false'}`,
      detail: truthy
        ? 'The condition is true, so the code inside the if branch runs.'
        : node.alternate
          ? 'The condition is false, so the else branch runs.'
          : 'The condition is false, so the if branch is skipped.',
      env,
      extra: { condition: node.condition, truthy }
    });
    if (truthy) {
      this.executeBlock(node.consequent, env);
    } else if (node.alternate) {
      this.executeBlock(node.alternate, env);
    }
  }

  executeFor(node, env) {
    const meta = node.loopMeta;
    if (!meta) {
      throw new UnsupportedSignal('This loop could not be read by the trace interpreter.', node.startLine);
    }
    if (meta.style === 'classic') {
      this.executeClassicFor(node, meta, env);
      return;
    }
    if (meta.style === 'forOf' || meta.style === 'forIn') {
      this.executeRangeFor(node, meta, env);
      return;
    }
    throw new UnsupportedSignal('This for-loop form is not supported by Live Trace yet.', node.startLine);
  }

  executeClassicFor(node, meta, env) {
    if (meta.initAction) {
      this.performAssignmentOrFragment(meta.initAction, env, node, { emitStep: false });
    }
    let iterations = 0;
    while (true) {
      const condition = meta.conditionAST ? this.evaluate(meta.conditionAST, env) : true;
      if (isUnknown(condition)) {
        throw new UnsupportedSignal(`Could not evaluate the loop condition “${meta.testText || 'the condition'}”.`, node.startLine);
      }
      const truthy = toBoolean(condition);
      this.emit({
        line: node.startLine,
        kind: 'loop-check',
        title: `Loop check: ${truncateCode(meta.testText || 'repeat', 48)} → ${truthy ? 'true' : 'false'}`,
        detail: truthy
          ? `The condition is true, so the loop body runs again (iteration ${iterations + 1}).`
          : 'The loop condition is now false. The loop ends and the code after it continues.',
        env
      });
      if (!truthy) break;
      iterations += 1;
      this.loopIterationCount += 1;
      if (iterations > this.loopLimit) {
        throw new TraceLimitSignal(
          `The loop ran more than ${this.loopLimit} times. The trace stopped to keep the page responsive.`,
          node.startLine
        );
      }
      try {
        this.executeBlock(node.body, env);
      } catch (signal) {
        if (signal instanceof BreakSignal) break;
        if (!(signal instanceof ContinueSignal)) throw signal;
      }
      if (meta.updateAction) {
        this.performAssignmentOrFragment(meta.updateAction, env, node, { emitStep: false });
      }
    }
  }

  executeRangeFor(node, meta, env) {
    const iterable = meta.iterableAST ? this.evaluate(meta.iterableAST, env) : unknownValue();
    if (isUnknown(iterable)) {
      throw new UnsupportedSignal(`Could not evaluate what this loop should iterate over (“${meta.iterableText}”).`, node.startLine);
    }
    const isIndexLoop = meta.style === 'forIn' && ['javascript', 'typescript'].includes(this.language.id);
    const values = toIterable(iterable, isIndexLoop ? 'keys' : 'values', this.language);
    if (!values) {
      throw new UnsupportedSignal(`“${meta.iterableText}” is not a collection this trace can iterate over.`, node.startLine);
    }
    if (!values.length) {
      this.emit({
        line: node.startLine,
        kind: 'loop-check',
        title: 'The collection is empty',
        detail: 'The loop body is skipped because there is nothing to iterate over.',
        env
      });
      return;
    }
    const target = meta.target || 'item';
    for (let index = 0; index < values.length; index += 1) {
      this.loopIterationCount += 1;
      if (index >= this.loopLimit) {
        throw new TraceLimitSignal(
          `The loop ran more than ${this.loopLimit} times. The trace stopped to keep the page responsive.`,
          node.startLine
        );
      }
      env.assign(target, values[index], { isDeclaration: false, line: node.startLine });
      const step = this.emit({
        line: node.startLine,
        kind: 'iteration',
        title: `Iteration ${index + 1} of ${values.length}: ${target} = ${formatValue(values[index], this.language)}`,
        detail: `The loop picks the value at position ${index + 1} from ${meta.iterableText} and stores it in ${target}.`,
        env,
        extra: { iteration: index + 1, target, value: formatValue(values[index], this.language) }
      });
      this.recordEvent({
        kind: 'loop-target',
        line: node.startLine,
        target,
        name: target,
        expressionText: meta.iterableText,
        operator: null,
        value: formatValue(values[index], this.language),
        valueType: typeOfValue(values[index]),
        scope: this.frames.at(-1)?.name ?? 'Global',
        dependencies: meta.iterableAST ? collectIdentifiers(meta.iterableAST) : [],
        stepIndex: step.index
      });
      try {
        this.executeBlock(node.body, env);
      } catch (signal) {
        if (signal instanceof BreakSignal) break;
        if (!(signal instanceof ContinueSignal)) throw signal;
      }
    }
  }

  executeWhile(node, env) {
    let iterations = 0;
    while (true) {
      const condition = this.evaluate(node.conditionAST, env);
      if (isUnknown(condition)) {
        throw new UnsupportedSignal(`Could not evaluate the while condition “${node.condition}”.`, node.startLine);
      }
      const truthy = toBoolean(condition);
      this.emit({
        line: node.startLine,
        kind: 'loop-check',
        title: `While check: ${truncateCode(node.condition, 48)} → ${truthy ? 'true' : 'false'}`,
        detail: truthy
          ? `The condition is true, so the loop body runs again (iteration ${iterations + 1}).`
          : 'The loop condition is false. The loop ends here.',
        env
      });
      if (!truthy) break;
      iterations += 1;
      this.loopIterationCount += 1;
      if (iterations > this.loopLimit) {
        throw new TraceLimitSignal(
          `The loop ran more than ${this.loopLimit} times. The trace stopped to keep the page responsive.`,
          node.startLine
        );
      }
      try {
        this.executeBlock(node.body, env);
      } catch (signal) {
        if (signal instanceof BreakSignal) break;
        if (!(signal instanceof ContinueSignal)) throw signal;
      }
    }
  }

  executeDoWhile(node, env) {
    let iterations = 0;
    while (true) {
      iterations += 1;
      this.loopIterationCount += 1;
      if (iterations > this.loopLimit) {
        throw new TraceLimitSignal('This do/while loop ran too many times.', node.startLine);
      }
      try {
        this.executeBlock(node.body, env);
      } catch (signal) {
        if (signal instanceof BreakSignal) break;
        if (!(signal instanceof ContinueSignal)) throw signal;
      }
      const condition = this.evaluate(node.conditionAST, env);
      if (isUnknown(condition)) throw new UnsupportedSignal('Could not evaluate the do/while condition.', node.startLine);
      const truthy = toBoolean(condition);
      this.emit({
        line: node.startLine,
        kind: 'loop-check',
        title: `Repeat? ${truncateCode(node.condition, 48)} → ${truthy ? 'true' : 'false'}`,
        detail: truthy ? 'The do/while condition is true, so the body runs once more.' : 'The condition is false, so this do/while loop ends.',
        env
      });
      if (!truthy) break;
    }
  }

  performPrint(action, env, node) {
    const print = action.print;
    if (!print) return;
    let text = '';
    let hadUnknown = false;
    if (print.kind === 'printf') {
      const values = print.args.map((arg) => this.evaluate(arg, env));
      if (values.some(isUnknown)) hadUnknown = true;
      text = formatPrintf(values, this.language);
    } else if (print.kind === 'cout') {
      const parts = [];
      for (const arg of print.args) {
        const value = this.evaluate(arg, env);
        if (isUnknown(value)) hadUnknown = true;
        parts.push(formatForPrint(value, this.language));
      }
      text = parts.join('') + (print.addNewline ? '\n' : '');
    } else if (print.kind === 'puts') {
      const values = print.args.map((arg) => this.evaluate(arg, env));
      if (values.some(isUnknown)) hadUnknown = true;
      text = `${formatForPrint(values[0] ?? '', this.language)}\n`;
    } else if (print.kind === 'putchar') {
      const values = print.args.map((arg) => this.evaluate(arg, env));
      const value = values[0];
      if (isUnknown(value)) hadUnknown = true;
      text = typeof value === 'number' ? String.fromCharCode(value) : String(formatForPrint(value, this.language));
    } else {
      const values = print.args.map((arg) => this.evaluate(arg, env));
      if (values.some(isUnknown)) hadUnknown = true;
      text = values.map((value) => formatForPrint(value, this.language)).join(print.separator ?? ' ');
      if (print.addNewline) text += '\n';
    }
    if (hadUnknown) {
      this.warn('One printed value could not be evaluated. It is shown as ?.', node.startLine);
    }
    this.output += text;
    const preview = text.replace(/\n$/, '') || '(blank line)';
    this.emit({
      line: node.startLine,
      endLine: node.endLine,
      kind: 'print',
      title: `Print: ${truncateCode(preview, 64)}`,
      detail: 'This text was added to the program’s output. Output appears in the order the print statements run.',
      env,
      extra: { printed: text }
    });
  }

  performAssignmentOrFragment(action, env, node, options) {
    if (!action) return;
    if (action.subtype === 'declaration' || action.subtype === 'assignment') {
      this.performAssignment(action, env, node, options);
      return;
    }
    if (action.subtype === 'update') {
      if (action.expressionAST) this.evaluate(action.expressionAST, env);
      else if (action.expressionText) this.evaluate(parseExpression(action.expressionText, this.language), env);
      return;
    }
    if (action.subtype === 'expression' && action.expressionAST) {
      this.evaluate(action.expressionAST, env);
    }
  }

  readTarget(target, env, options = {}) {
    const parsed = typeof target === 'string' ? parseExpression(target, this.language) : target;
    if (!parsed || parsed.type === 'RawExpression') {
      const binding = env.find(target);
      return binding?.binding?.value;
    }
    if (options.quiet && parsed.type === 'Identifier') {
      return env.find(parsed.name)?.binding?.value;
    }
    return this.evaluate(parsed, env);
  }

  writeTarget(action, value, env, line) {
    const target = action.targetChain ?? action.targetName;
    const parsed = parseExpression(target, this.language);
    const meta = {
      isDeclaration: !!action.isDeclaration,
      declaredType: action.declarationType,
      line,
      kind: 'variable'
    };
    if (!parsed || parsed.type === 'RawExpression' || parsed.type === 'Identifier') {
      const name = parsed?.name ?? action.targetName;
      env.assign(name, value, meta);
      return;
    }
    if (parsed.type === 'MemberExpression') {
      const object = this.evaluate(parsed.object, env);
      if (isUnknown(object) || object == null) {
        this.warn(`Could not find the value being updated by “${target}”.`, line);
        return;
      }
      const key = parsed.computed ? this.evaluate(parsed.property, env) : parsed.property.name;
      if (isUnknown(key)) return;
      if (Array.isArray(object)) {
        const index = Number(key);
        object[index] = value;
      } else if (typeof object === 'object') {
        object[String(key)] = value;
      }
      return;
    }
    env.assign(action.targetName, value, meta);
  }

  recordEvent(event) {
    this.events.push({
      ...event,
      index: this.events.length,
      stepIndex: event.stepIndex ?? Math.max(0, this.steps.length - 1)
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Expressions                                                            */
  /* ---------------------------------------------------------------------- */

  evaluate(node, env) {
    if (!node) return undefined;
    try {
      switch (node.type) {
        case 'Literal':
          if (node.valueType === 'template') {
            return this.evaluateTemplate(node, env);
          }
          return node.value;
        case 'Identifier': {
          if (node.name === 'NaN') return NaN;
          if (node.name === 'Infinity') return Infinity;
          if (!env.has(node.name)) {
            const message = `Could not find a value named “${node.name}”.`;
            this.warn(message, this.currentLine);
            return unknownValue(node.name, message);
          }
          return env.get(node.name);
        }
        case 'ArrayExpression': {
          const values = node.elements.map((element) => this.evaluate(element, env));
          return values;
        }
        case 'ObjectExpression': {
          const object = {};
          for (const property of node.properties) {
            object[property.key] = this.evaluate(property.value, env);
          }
          return object;
        }
        case 'UnaryExpression':
          return this.evaluateUnary(node, env);
        case 'UpdateExpression':
          return this.evaluateUpdate(node, env);
        case 'BinaryExpression':
        case 'LogicalExpression':
          return this.evaluateBinary(node, env);
        case 'ConditionalExpression': {
          const test = this.evaluate(node.test, env);
          if (isUnknown(test)) return test;
          return toBoolean(test) ? this.evaluate(node.consequent, env) : this.evaluate(node.alternate, env);
        }
        case 'AssignmentExpression':
          return this.evaluateAssignmentExpression(node, env);
        case 'CallExpression':
          return this.evaluateCall(node, env);
        case 'MemberExpression':
          return this.evaluateMember(node, env);
        case 'RawExpression': {
          this.warn(`The expression “${truncateCode(node.text, 60)}” is outside the supported subset.`, this.currentLine);
          return unknownValue(node.text, 'Unsupported expression');
        }
        default:
          this.warn(`Unsupported expression type: ${node.type}.`, this.currentLine);
          return unknownValue('', 'Unsupported expression');
      }
    } catch (error) {
      if (error instanceof ReturnSignal || error instanceof BreakSignal || error instanceof ContinueSignal || error instanceof UnsupportedSignal || error instanceof TraceLimitSignal) {
        throw error;
      }
      this.warn(`The expression could not be evaluated: ${cleanErrorMessage(error)}`, this.currentLine);
      return unknownValue('', cleanErrorMessage(error));
    }
  }

  evaluateTemplate(node, env) {
    if (!node.parts) return String(node.value ?? '');
    let result = '';
    for (const part of node.parts) {
      if (part.type === 'text') result += part.value;
      else {
        const value = this.evaluate(part.ast, env);
        result += formatForPrint(value, this.language);
      }
    }
    return result;
  }

  evaluateUnary(node, env) {
    const argument = this.evaluate(node.argument, env);
    if (isUnknown(argument) || isUninitialized(argument)) return unknownValue();
    switch (node.operator) {
      case '!':
      case 'not':
        return !toBoolean(argument);
      case '-':
        return -toNumber(argument);
      case '+':
        return toNumber(argument);
      case '~':
        return ~toNumber(argument);
      case 'typeof':
        return jsTypeof(argument);
      case 'void':
        return undefined;
      default:
        return unknownValue();
    }
  }

  evaluateUpdate(node, env) {
    const current = this.evaluate(node.argument, env);
    if (isUnknown(current)) return current;
    const delta = node.operator === '++' ? 1 : -1;
    const next = toNumber(current) + delta;
    this.assignExpressionTarget(node.argument, next, env);
    return node.prefix ? next : toNumber(current);
  }

  evaluateBinary(node, env) {
    const operator = node.operator;
    if (node.type === 'LogicalExpression') {
      const left = this.evaluate(node.left, env);
      if (isUnknown(left)) return left;
      if (operator === '&&' || operator === 'and') {
        return toBoolean(left) ? this.evaluate(node.right, env) : left;
      }
      if (operator === '||' || operator === 'or') {
        return toBoolean(left) ? left : this.evaluate(node.right, env);
      }
      if (operator === '??') {
        return left === null || left === undefined ? this.evaluate(node.right, env) : left;
      }
    }

    const left = this.evaluate(node.left, env);
    const right = this.evaluate(node.right, env);
    if (isUnknown(left) || isUnknown(right)) return unknownValue();
    return applyBinaryOperator(operator, left, right, this.language, (message) => this.warn(message, this.currentLine));
  }

  evaluateAssignmentExpression(node, env) {
    const value = this.evaluate(node.right, env);
    if (node.operator === '=') {
      this.assignExpressionTarget(node.left, value, env);
      return value;
    }
    const current = this.evaluate(node.left, env);
    const result = applyBinaryOperator(node.operator.slice(0, -1), current, value, this.language, (message) => this.warn(message, this.currentLine));
    this.assignExpressionTarget(node.left, result, env);
    return result;
  }

  assignExpressionTarget(node, value, env) {
    if (node.type === 'Identifier') {
      env.assign(node.name, value, { isDeclaration: false, line: this.currentLine });
      return;
    }
    if (node.type === 'MemberExpression') {
      const object = this.evaluate(node.object, env);
      if (isUnknown(object) || object == null) return;
      const key = node.computed ? this.evaluate(node.property, env) : node.property.name;
      if (isUnknown(key)) return;
      if (Array.isArray(object)) object[Number(key)] = value;
      else if (typeof object === 'object') object[String(key)] = value;
    }
  }

  evaluateMember(node, env) {
    const object = this.evaluate(node.object, env);
    if (isUnknown(object) || isUninitialized(object)) return unknownValue();
    const key = node.computed ? this.evaluate(node.property, env) : node.property.name;
    if (isUnknown(key)) return unknownValue();
    if (object == null) return unknownValue();
    if (Array.isArray(object) || typeof object === 'string') {
      if (key === 'length' || key === 'length()') return object.length;
      if (key === 'size') return unknownValue();
      const index = Number(key);
      if (Number.isInteger(index)) return object[index];
    }
    if (typeof object === 'object') {
      return Object.prototype.hasOwnProperty.call(object, key) ? object[key] : undefined;
    }
    return undefined;
  }

  evaluateCall(node, env) {
    // Member methods need their receiver, so handle them before evaluating the
    // callee as a plain value.
    if (node.callee?.type === 'MemberExpression') {
      return this.evaluateMethodCall(node, env);
    }
    const callee = this.evaluate(node.callee, env);
    const args = node.arguments.map((argument) => this.evaluate(argument, env));
    if (isUserFunction(callee)) {
      return this.callUserFunction(callee.node, args, env, {
        callLine: this.currentLine,
        argTexts: node.arguments.map(expressionSource)
      });
    }
    if (isBuiltin(callee)) {
      return this.callBuiltin(callee.name, args);
    }
    if (isUnknown(callee)) return callee;
    this.warn('This function call is not available in the local trace.', this.currentLine);
    return unknownValue(expressionSource(node.callee), 'Unknown function');
  }

  evaluateMethodCall(node, env) {
    const callee = node.callee;
    const object = this.evaluate(callee.object, env);
    if (isUnknown(object) || isUninitialized(object)) return unknownValue();
    const method = callee.computed ? this.evaluate(callee.property, env) : callee.property.name;
    if (isUnknown(method)) return unknownValue();
    const args = node.arguments.map((argument) => this.evaluate(argument, env));

    if (callee.object.type === 'Identifier' && callee.object.name === 'Math') {
      return this.callMathMethod(method, args);
    }
    if (object === Math) {
      return this.callMathMethod(method, args);
    }
    if (Array.isArray(object)) {
      switch (method) {
        case 'push':
          object.push(...args);
          return object.length;
        case 'append':
        case 'add':
          object.push(...args);
          return null;
        case 'pop':
          return object.pop();
        case 'shift':
          return object.shift();
        case 'unshift':
          object.unshift(...args);
          return object.length;
        case 'join':
          return object.map((value) => formatForPrint(value, this.language)).join(args[0] ?? ',');
        case 'slice':
          return object.slice(toNumber(args[0] ?? 0), args[1] === undefined ? undefined : toNumber(args[1]));
        case 'indexOf':
          return object.findIndex((value) => looseEqual(value, args[0]));
        case 'includes':
          return object.some((value) => looseEqual(value, args[0]));
        case 'reverse':
          object.reverse();
          return object;
        case 'sort':
          object.sort();
          return object;
        case 'size':
          return object.length;
        default:
          break;
      }
    }
    if (typeof object === 'string') {
      switch (method) {
        case 'toUpperCase':
        case 'upper':
          return object.toUpperCase();
        case 'toLowerCase':
        case 'lower':
          return object.toLowerCase();
        case 'trim':
        case 'strip':
          return object.trim();
        case 'split':
          return object.split(String(args[0] ?? ''));
        case 'includes':
          return object.includes(String(args[0] ?? ''));
        case 'startsWith':
          return object.startsWith(String(args[0] ?? ''));
        case 'endsWith':
          return object.endsWith(String(args[0] ?? ''));
        case 'charAt':
          return object.charAt(toNumber(args[0] ?? 0));
        case 'replace':
          return object.replace(String(args[0] ?? ''), String(args[1] ?? ''));
        case 'toFixed':
          return Number(object).toFixed(toNumber(args[0] ?? 0));
        case 'size':
          return object.length;
        case 'length':
          return object.length;
        default:
          break;
      }
    }
    if (typeof object === 'number') {
      if (method === 'toFixed') return Number(object).toFixed(toNumber(args[0] ?? 0));
      if (method === 'toString') return String(object);
    }
    if (typeof object === 'object' && object !== null) {
      if (method === 'keys') return Object.keys(object);
      if (method === 'has') return Object.prototype.hasOwnProperty.call(object, args[0]);
      if (method === 'get') return object[args[0]];
    }
    this.warn(`The method “${String(method)}” is not supported in Live Trace.`, this.currentLine);
    return unknownValue('', 'Unsupported method');
  }

  callMathMethod(method, args) {
    const a = toNumber(args[0]);
    const b = toNumber(args[1]);
    const functions = {
      round: () => Math.round(a),
      floor: () => Math.floor(a),
      ceil: () => Math.ceil(a),
      abs: () => Math.abs(a),
      max: () => Math.max(...args.map(toNumber)),
      min: () => Math.min(...args.map(toNumber)),
      pow: () => a ** b,
      sqrt: () => Math.sqrt(a),
      random: () => Math.random()
    };
    return functions[method] ? functions[method]() : unknownValue('', 'Unsupported Math method');
  }

  callBuiltin(name, args) {
    const language = this.language;
    switch (name) {
      case 'len':
        return Array.isArray(args[0]) || typeof args[0] === 'string' ? args[0].length : unknownValue();
      case 'range': {
        const numbers = args.map((arg) => toNumber(arg));
        let start = 0;
        let stop = numbers[0] ?? 0;
        let step = 1;
        if (numbers.length >= 2) {
          start = numbers[0];
          stop = numbers[1];
          step = numbers[2] ?? 1;
        }
        if (!step) return [];
        const values = [];
        if (step > 0) {
          for (let value = start; value < stop && values.length < MAX_ARRAY_ITEMS; value += step) values.push(value);
        } else {
          for (let value = start; value > stop && values.length < MAX_ARRAY_ITEMS; value += step) values.push(value);
        }
        return values;
      }
      case 'abs':
        return Math.abs(toNumber(args[0]));
      case 'round': {
        const digits = args.length > 1 ? toNumber(args[1]) : 0;
        const factor = 10 ** digits;
        return Math.round(toNumber(args[0]) * factor) / factor;
      }
      case 'min':
        return Math.min(...args.map(toNumber));
      case 'max':
        return Math.max(...args.map(toNumber));
      case 'sum':
        return args[0]?.reduce?.((total, value) => total + toNumber(value), 0) ?? 0;
      case 'str':
      case 'String':
        return formatForPrint(args[0], language);
      case 'int':
      case 'Number':
      case 'parseInt':
        return Math.trunc(toNumber(args[0]));
      case 'float':
      case 'parseFloat':
        return toNumber(args[0]);
      case 'bool':
      case 'Boolean':
        return toBoolean(args[0]);
      case 'isNaN':
        return Number.isNaN(toNumber(args[0]));
      default:
        this.warn(`The built-in function “${name}” is not supported in Live Trace.`, this.currentLine);
        return unknownValue('', 'Unsupported builtin');
    }
  }

  callUserFunction(fn, args, callEnv, options = {}) {
    if (this.frames.length >= this.callLimit) {
      throw new TraceLimitSignal(
        `The call stack reached ${this.callLimit} levels. The trace stopped to keep the page responsive.`,
        options.callLine ?? fn.startLine
      );
    }
    this.functionCallCount += 1;
    const argDisplays = args.map((value) => formatValue(value, this.language));
    if (!options.isEntry) {
      this.emit({
        line: options.callLine ?? this.currentLine,
        kind: 'call',
        title: `Call ${fn.name}(${truncateCode(argDisplays.join(', '), 34)})`,
        detail: `Control jumps into ${fn.name}. When it returns, the caller continues from this line.`,
        env: callEnv,
        extra: { callee: fn.name, args: argDisplays }
      });
    }

    const fnEnv = new Environment(fn.closure ?? this.globalEnv, fn.name, 'function');
    if (options.isEntry) this.entryEnv = fnEnv;
    this.frames.push({ name: fn.name, line: fn.startLine });
    const paramEvents = [];
    fn.params.forEach((param, index) => {
      let value = index < args.length ? args[index] : undefined;
      if (value === undefined && param.defaultValue) {
        value = this.evaluate(parseExpression(param.defaultValue, this.language), fnEnv);
      }
      if (value === undefined && options.isEntry && index === 0 && isMainArgsParameter(param)) {
        value = [];
      }
      fnEnv.define(param.name, value, {
        hidden: false,
        declaredType: param.type,
        line: fn.startLine,
        kind: 'parameter'
      });
      paramEvents.push({
        param: param.name,
        value: formatValue(value, this.language),
        type: typeOfValue(value)
      });
    });

    const entryStep = this.emit({
      line: fn.startLine,
      endLine: fn.startLine,
      kind: 'function-entry',
      title: `${fn.name} starts`,
      detail: fn.params.length
        ? fn.params.map((param, index) => `${param.name} receives ${formatValue(index < args.length ? args[index] : undefined, this.language)}`).join(' · ')
        : 'This function has no parameters. It begins with an empty local workspace.',
      env: fnEnv,
      extra: { params: paramEvents }
    });
    for (const paramEvent of paramEvents) {
      this.recordEvent({
        kind: 'parameter',
        line: fn.startLine,
        target: paramEvent.param,
        name: paramEvent.param,
        expressionText: null,
        operator: null,
        value: paramEvent.value,
        valueType: paramEvent.type,
        scope: fn.name,
        dependencies: [],
        stepIndex: entryStep.index
      });
    }

    let returned = false;
    let result;
    let pendingError = null;
    try {
      this.executeBlock(fn.body, fnEnv);
    } catch (signal) {
      if (signal instanceof ReturnSignal) {
        returned = true;
        result = signal.value;
      } else {
        pendingError = signal;
      }
    }

    if (!returned && !pendingError) {
      this.emit({
        line: fn.endLine,
        kind: 'return',
        title: `${fn.name} returns`,
        detail: 'The function reached its end without an explicit return, so the caller receives undefined / no value.',
        env: fnEnv
      });
    }

    this.frames.pop();
    if (pendingError) throw pendingError;
    return result;
  }
}

/* -------------------------------------------------------------------------- */
/* Values and formatting                                                      */
/* -------------------------------------------------------------------------- */

function installBuiltins(env) {
  const builtinNames = ['len', 'range', 'abs', 'round', 'min', 'max', 'sum', 'str', 'int', 'float', 'bool', 'String', 'Number', 'Boolean', 'parseInt', 'parseFloat', 'isNaN'];
  for (const name of builtinNames) {
    env.define(name, { __prism: 'builtin', name }, { hidden: true, kind: 'builtin' });
  }
  env.define('Math', { __prism: 'builtinObject', name: 'Math' }, { hidden: true, kind: 'builtin' });
}

export function formatValue(value, language = {}) {
  const seen = new Set();
  const format = (current, depth) => {
    if (isUnknown(current)) return '?';
    if (isUninitialized(current)) return '—';
    if (isUserFunction(current)) return `<function ${current.node?.name ?? ''}>`;
    if (isBuiltin(current)) return `<built-in ${current.name}>`;
    if (current === null) return language.id === 'python' ? 'None' : 'null';
    if (current === undefined) return language.id === 'python' ? 'None' : 'undefined';
    if (typeof current === 'number') return formatNumber(current);
    if (typeof current === 'string') return `"${escapeForDisplay(current)}"`;
    if (typeof current === 'boolean') return language.id === 'python' ? (current ? 'True' : 'False') : String(current);
    if (Array.isArray(current)) {
      if (seen.has(current)) return '[…]';
      seen.add(current);
      if (depth > 3) return '[…]';
      const items = current.slice(0, 16).map((item) => format(item, depth + 1));
      if (current.length > 16) items.push('…');
      seen.delete(current);
      return `[${items.join(', ')}]`;
    }
    if (typeof current === 'object') {
      if (seen.has(current)) return '{…}';
      seen.add(current);
      if (depth > 3) return '{…}';
      const keys = Object.keys(current).slice(0, 12);
      const body = keys.map((key) => `${key}: ${format(current[key], depth + 1)}`);
      if (Object.keys(current).length > 12) body.push('…');
      seen.delete(current);
      return `{${body.join(', ')}}`;
    }
    return String(current);
  };
  return format(value, 0);
}

function formatNumber(number) {
  if (!Number.isFinite(number)) return String(number);
  if (Number.isInteger(number)) return String(number);
  const rounded = Math.round(number * 1e10) / 1e10;
  return String(rounded);
}

function escapeForDisplay(value) {
  return String(value).replaceAll('\\', '\\\\').replaceAll('"', '\\"').replaceAll('\n', '\\n').replaceAll('\t', '\\t');
}

function formatForPrint(value, language = {}) {
  if (isUnknown(value)) return '?';
  if (isUninitialized(value)) return '—';
  if (typeof value === 'string') return value;
  return formatValue(value, language);
}

function formatPrintf(values) {
  if (!values.length) return '';
  const format = formatForPrint(values[0]);
  const args = values.slice(1);
  let argIndex = 0;
  return format.replace(/%([-+ 0#]*)(\d+)?(?:\.(\d+))?([diufFeEgGxXosc%])/g, (match, flags, width, precision, spec) => {
    if (spec === '%') return '%';
    const value = args[argIndex];
    argIndex += 1;
    if (value === undefined || isUnknown(value)) return '?';
    let rendered;
    switch (spec) {
      case 'd':
      case 'i':
        rendered = String(Math.trunc(toNumber(value)));
        break;
      case 'f':
      case 'F': {
        const digits = precision === undefined ? 6 : Number(precision);
        rendered = Number(value).toFixed(digits);
        break;
      }
      case 'e':
      case 'E':
        rendered = Number(value).toExponential(precision === undefined ? 6 : Number(precision));
        if (spec === 'E') rendered = rendered.toUpperCase();
        break;
      case 'g':
      case 'G':
        rendered = Number(value).toPrecision(precision === undefined ? 6 : Number(precision));
        if (spec === 'G') rendered = rendered.toUpperCase();
        break;
      case 'x':
        rendered = Math.trunc(toNumber(value)).toString(16);
        break;
      case 'X':
        rendered = Math.trunc(toNumber(value)).toString(16).toUpperCase();
        break;
      case 'o':
        rendered = Math.trunc(toNumber(value)).toString(8);
        break;
      case 'c':
        rendered = typeof value === 'number' ? String.fromCharCode(value) : String(value).charAt(0);
        break;
      case 's':
      default:
        rendered = formatForPrint(value);
        break;
    }
    if (width) {
      const targetWidth = Number(width);
      if (rendered.length < targetWidth) {
        const pad = flags.includes('0') && !flags.includes('-') ? '0' : ' ';
        rendered = flags.includes('-') ? rendered.padEnd(targetWidth, ' ') : rendered.padStart(targetWidth, pad);
      }
    }
    return rendered;
  });
}

function typeOfValue(value) {
  if (isUnknown(value)) return 'unknown';
  if (isUninitialized(value)) return 'uninitialized';
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  if (Array.isArray(value)) return 'array';
  if (isUserFunction(value) || isBuiltin(value)) return 'function';
  return typeof value;
}

function snapshotEnvironment(env, language, previousSnapshot) {
  const bindings = env.visibleBindings();
  return bindings.map((binding) => {
    const display = formatValue(binding.value, language);
    const type = typeOfValue(binding.value);
    const key = `${type}:${display}`;
    return {
      name: binding.name,
      display,
      type,
      scope: binding.scope,
      changed: previousSnapshot.get(binding.name) !== key
    };
  });
}

function toBoolean(value) {
  if (isUnknown(value) || isUninitialized(value)) return false;
  if (Array.isArray(value)) return value.length > 0;
  return Boolean(value);
}

function toNumber(value) {
  if (isUnknown(value) || isUninitialized(value)) return NaN;
  if (typeof value === 'number') return value;
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (value === null) return 0;
  if (value === undefined) return NaN;
  if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) return Number(value);
  return NaN;
}

function applyBinaryOperator(operator, left, right, language, warn) {
  if (isUnknown(left) || isUnknown(right) || isUninitialized(left) || isUninitialized(right)) {
    return unknownValue();
  }
  switch (operator) {
    case '+':
      if (typeof left === 'string' || typeof right === 'string') {
        if (language.id === 'python' && !(typeof left === 'string' && typeof right === 'string')) {
          warn?.('Python does not allow adding a string and a number directly. Use str(...) first.');
          return unknownValue();
        }
        return formatForPrint(left, language) + formatForPrint(right, language);
      }
      return toNumber(left) + toNumber(right);
    case '-':
      return toNumber(left) - toNumber(right);
    case '*':
      return toNumber(left) * toNumber(right);
    case '/':
      return toNumber(left) / toNumber(right);
    case '//':
      return Math.floor(toNumber(left) / toNumber(right));
    case '%':
      return toNumber(left) % toNumber(right);
    case '**':
      return toNumber(left) ** toNumber(right);
    case '===':
    case '==':
    case 'is':
      return operator === '==' ? looseEqual(left, right) : strictEqual(left, right);
    case '!==':
    case '!=':
      return operator === '!=' ? !looseEqual(left, right) : !strictEqual(left, right);
    case '<':
      return left < right;
    case '<=':
      return left <= right;
    case '>':
      return left > right;
    case '>=':
      return left >= right;
    case 'and':
    case '&&':
      return left;
    case 'or':
    case '||':
      return left;
    case 'in':
      if (Array.isArray(right)) return right.some((value) => looseEqual(value, left));
      if (typeof right === 'string') return right.includes(String(left));
      if (right && typeof right === 'object') return Object.prototype.hasOwnProperty.call(right, String(left));
      return false;
    case '&':
      return toNumber(left) & toNumber(right);
    case '|':
      return toNumber(left) | toNumber(right);
    case '^':
      return toNumber(left) ^ toNumber(right);
    case '<<':
      return toNumber(left) << toNumber(right);
    case '>>':
      return toNumber(left) >> toNumber(right);
    default:
      warn?.(`The operator “${operator}” is not supported in Live Trace.`);
      return unknownValue('', 'Unsupported operator');
  }
}

function strictEqual(left, right) {
  if (typeof left === 'number' && typeof right === 'number') return Object.is(left, right);
  return left === right;
}

function looseEqual(left, right) {
  if (left === right) return true;
  if (left == null || right == null) return left == null && right == null;
  if (typeof left === 'boolean') return looseEqual(Number(left), right);
  if (typeof right === 'boolean') return looseEqual(left, Number(right));
  if ((typeof left === 'number' && typeof right === 'string') || (typeof left === 'string' && typeof right === 'number')) {
    return Number(left) === Number(right);
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((value, index) => looseEqual(value, right[index]));
  }
  return false;
}

function toIterable(value, style) {
  if (Array.isArray(value)) {
    if (style === 'keys') return value.map((_, index) => index);
    return value.slice();
  }
  if (typeof value === 'string') {
    if (style === 'keys') return [...value].map((_, index) => index);
    return [...value];
  }
  if (value && typeof value === 'object') {
    if (style === 'keys' || style === 'values') return Object.keys(value);
    return null;
  }
  return null;
}

function isMainArgsParameter(param) {
  return /args|argv/i.test(param?.name ?? '') || /\[\]/.test(param?.type ?? '');
}

function expressionSource(node) {
  if (!node) return '';
  switch (node.type) {
    case 'Identifier': return node.name;
    case 'Literal': return node.raw ?? String(node.value);
    case 'MemberExpression': return `${expressionSource(node.object)}.${expressionSource(node.property)}`;
    case 'CallExpression': return `${expressionSource(node.callee)}(…)`;
    case 'BinaryExpression':
    case 'LogicalExpression': return `${expressionSource(node.left)} ${node.operator} ${expressionSource(node.right)}`;
    case 'UnaryExpression': return `${node.operator}${expressionSource(node.argument)}`;
    default: return node.text ?? '';
  }
}

function buildAssignmentDetail(action, beforeValue, afterValue, display, previousDisplay, language) {
  const target = action.targetDisplay ?? action.targetName ?? 'the variable';
  const rhs = truncateCode(action.expressionText ?? 'nothing', 54);
  if (action.isDeclaration) {
    return `The new variable ${target} is created with ${display}. Its value is ${typeOfValue(afterValue)}.`;
  }
  if (action.operator && action.operator !== '=') {
    return `The old value ${previousDisplay ?? '—'} was updated using ${action.operator} ${rhs}. ${target} is now ${display}.`;
  }
  if (beforeValue !== undefined && previousDisplay !== null) {
    return `The right side (${rhs}) is evaluated and stored in ${target}. It changed from ${previousDisplay} to ${display}.`;
  }
  return `The right side (${rhs}) is evaluated and stored in ${target}, which now holds ${display}.`;
}

function truncateCode(value, limit = 60) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function cleanErrorMessage(error) {
  const message = error instanceof Error ? error.message : String(error);
  return message.length > 180 ? `${message.slice(0, 177)}…` : message;
}

function jsTypeof(value) {
  if (value === null) return 'object';
  if (Array.isArray(value)) return 'object';
  if (isUnknown(value)) return 'unknown';
  return typeof value;
}

function firstExecutableLine(analysis) {
  if (analysis.entry?.kind === 'function' && analysis.entry.node) {
    return analysis.entry.node.startLine;
  }
  const firstTopLevel = findFirstExecutableTopLevel(analysis.root?.body?.children ?? []);
  if (firstTopLevel) return firstTopLevel.startLine;
  const candidate = analysis.actionNodes
    .map((node) => node.startLine)
    .filter((line) => Number.isFinite(line))
    .sort((a, b) => a - b)[0];
  return candidate ?? 1;
}

function findFirstExecutableTopLevel(nodes) {
  for (const node of nodes) {
    if (!node) continue;
    if (node.type === 'function' || node.type === 'class') continue;
    if (node.type === 'action') {
      if (['import', 'comment', 'empty', 'pass'].includes(node.action?.subtype)) continue;
      return node;
    }
    if (['if', 'for', 'while', 'do', 'switch', 'try', 'block'].includes(node.type)) return node;
  }
  return null;
}

function lastCodeLine(analysis) {
  const lines = analysis.lines;
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (lines[i].text.trim()) return lines[i].number;
  }
  return 1;
}
