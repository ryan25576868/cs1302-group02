/**
 * Local guide writer.
 *
 * The goal is to be genuinely useful without a model: explain the program's
 * shape, walk through the actual sample run, annotate meaningful lines, and
 * define the concepts that appear in this specific piece of code.
 */

const MAX_LINE_NOTES = 90;

export function buildGuide(analysis, trace) {
  const language = analysis.language;
  const completeTrace = trace && trace.complete;
  const stats = buildTraceStats(trace);
  const walkthrough = buildWalkthrough(analysis, trace, stats);
  const lineNotes = buildLineNotes(analysis, trace, stats);
  const concepts = buildConcepts(analysis, trace);
  const watchOuts = buildWatchOuts(analysis, trace);
  const quiz = buildQuiz(analysis, trace, stats);
  const summary = buildSummary(analysis, trace);
  const overview = buildOverview(analysis, trace, stats, summary);
  const allText = [
    summary,
    ...overview.paragraphs,
    overview.mentalModel.body,
    ...walkthrough.flatMap((step) => [step.title, step.body, ...(step.points ?? [])]),
    ...lineNotes.map((note) => note.note),
    ...concepts.flatMap((concept) => [concept.term, concept.definition, concept.inThisCode]),
    ...watchOuts.flatMap((item) => [item.title, item.body]),
    ...quiz.flatMap((item) => [item.question, item.answer])
  ].join(' ');
  const wordCount = allText.split(/\s+/).filter(Boolean).length;

  return {
    version: 1,
    author: 'local',
    headline: `How this ${language.name} program works`,
    sourceLineCount: analysis.lineCount,
    summary,
    overview,
    walkthrough,
    lineNotes,
    concepts,
    watchOuts,
    quiz,
    traceNote: trace
      ? {
          complete: !!completeTrace,
          output: trace.output,
          warnings: trace.warnings,
          stoppedReason: trace.stoppedReason
        }
      : null,
    readingMinutes: Math.max(1, Math.round(wordCount / 210)),
    wordCount
  };
}

/* -------------------------------------------------------------------------- */
/* Summary and overview                                                       */
/* -------------------------------------------------------------------------- */

function buildSummary(analysis, trace) {
  const language = analysis.language;
  const loop = findFirstExecutionLoop(analysis);
  const helper = findHelperCalledByLoop(analysis, loop);
  const accumulator = findAccumulator(analysis, loop);
  const print = findFirstExecutionPrint(analysis);
  const iterable = simpleIterableName(loop);
  const languageName = language.name;
  let firstPerson;

  const ending = print ? 'and prints the finished result' : 'and leaves the result in its variables';
  if (helper && accumulator && iterable) {
    firstPerson = `sends every value from \`${iterable}\` through the helper \`${helper.name}\`, adds each returned value to \`${accumulator}\`, ${ending}`;
  } else if (helper && accumulator) {
    firstPerson = `uses the helper \`${helper.name}\` on each loop pass, adds each returned value to \`${accumulator}\`, ${ending}`;
  } else if (loop && accumulator && iterable) {
    firstPerson = `walks through \`${iterable}\`, updates \`${accumulator}\` with each value, ${ending}`;
  } else if (helper && loop) {
    firstPerson = `uses the helper \`${helper.name}\` inside a loop, ${print ? 'then prints the result' : 'then keeps the result'}`;
  } else if (helper) {
    firstPerson = `defines the reusable helper \`${helper.name}\` and then uses it to produce a result`;
  } else if (loop) {
    firstPerson = `repeats a block of work${iterable ? ` for each value in \`${iterable}\`` : ''}${print ? ' and then prints a result' : ''}`;
  } else if (print) {
    firstPerson = `moves through its statements from top to bottom and prints a result`;
  } else {
    firstPerson = `moves through its statements from top to bottom`;
  }

  const output = trace?.complete && trace.output?.trim()
    ? ` In the sample run it outputs \`${previewOutput(trace.output, 64)}\`.`
    : '';
  return `This ${languageName} program ${firstPerson}.${output}`;
}

function buildOverview(analysis, trace, stats, summary) {
  const language = analysis.language;
  const loop = findFirstExecutionLoop(analysis);
  const helper = findHelperCalledByLoop(analysis, loop);
  const accumulator = findAccumulator(analysis, loop);
  const print = findFirstExecutionPrint(analysis);
  const firstAssignment = analysis.assignments[0];
  const entry = analysis.entry;
  const paragraphs = [];

  const entryText = entry?.kind === 'function'
    ? `It begins in \`${entry.name}()\`, which is where execution starts for ${language.name}.`
    : 'It runs from the top of the file to the bottom, skipping function definitions until they are called.';
  const shortOutput = trace?.complete && trace.output
    ? `The sample run prints \`${previewOutput(trace.output, 80)}\`.`
    : 'There is no completed sample output for this run.';
  paragraphs.push(`${entryText} ${shortOutput}`);

  if (helper && loop) {
    paragraphs.push(
      `The key idea is reuse. \`${helper.name}\` packages the repeated decision or calculation once, while the loop handles the repetition. Each pass asks the helper for a result${accumulator ? ` and folds it into \`${accumulator}\`` : ''}, so the running state stays in one place instead of being scattered across the program.`
    );
  } else if (loop) {
    paragraphs.push(
      `The key idea is repetition. The loop ${loop.type === 'for' ? 'sets up a repeatable pass through the data' : 're-checks a condition before every pass'}, so the same instructions can handle more than one value without being copied by hand.`
    );
  } else if (helper) {
    paragraphs.push(
      `The key idea is separation. \`${helper.name}\` holds one reusable job, and the rest of the program can call it whenever that job is needed.`
    );
  } else {
    paragraphs.push(
      'This is a short, linear program. Because there are no functions or loops in the main path, the quickest way to understand it is to read the statements in order and track the values in each variable.'
    );
  }

  if (firstAssignment) {
    paragraphs.push(
      `A useful reading order is: start with the values stored at line ${firstAssignment.line}, then follow the control flow${loop ? ` through the loop at line ${loop.startLine}` : ''}, and finish at the output${print ? ` on line ${print.startLine}` : ''}. The Line by line tab turns that route into a close reading with actual sample values where the trace has them.`
    );
  } else if (print) {
    paragraphs.push(
      `The output statement on line ${print.startLine} is the best anchor for understanding the program: trace backwards through the values that feed it.`
    );
  }

  if (trace && !trace.complete) {
    paragraphs.push(
      'Note: the local trace stopped before the end of this program. The structure below is still reliable, but value-specific claims are deliberately limited.'
    );
  }

  const mentalModel = buildMentalModel(analysis, loop, helper, accumulator);
  const shape = [
    `${analysis.functions.length} function${analysis.functions.length === 1 ? '' : 's'}`,
    `${analysis.metrics.loops} loop${analysis.metrics.loops === 1 ? '' : 's'}`,
    `${analysis.metrics.conditions} decision${analysis.metrics.conditions === 1 ? '' : 's'}`
  ].join(' · ');

  return {
    paragraphs,
    mentalModel,
    glance: [
      { label: 'Language', value: language.name, hint: language.tagline },
      {
        label: 'Entry point',
        value: entry?.kind === 'function' ? `${entry.name}()` : 'Top-level code',
        hint: entry?.kind === 'function' ? 'Execution starts here' : 'Runs from the first line'
      },
      { label: 'Shape', value: shape, hint: `${analysis.metrics.totalLines} lines in total` },
      {
        label: 'Sample output',
        value: trace?.complete && trace.output ? previewOutput(trace.output, 42) : 'No output',
        hint: trace?.complete ? 'From the local simulated run' : 'Trace not complete',
        mono: true
      }
    ]
  };
}

function buildMentalModel(analysis, loop, helper, accumulator) {
  if (helper && loop) {
    return {
      title: 'A tiny machine on a conveyor belt',
      body: `Think of \`${helper.name}\` as a small machine: values go in, a rule is applied, and a new value comes out. The loop is the conveyor belt that feeds it one item at a time${accumulator ? `, while \`${accumulator}\` is the tray where every result is collected` : ''}. The helper does not need to know where the items came from, and the loop does not need to know how the rule works.`
    };
  }
  if (loop && accumulator) {
    return {
      title: 'A running tally',
      body: `Imagine keeping a score on a notepad. The loop visits each value, adds it to the number already written in \`${accumulator}\`, and writes the new total back down. The notepad is updated after every pass, not replaced at the end.`
    };
  }
  if (loop) {
    return {
      title: 'A repeatable checklist',
      body: 'A loop is a checklist that runs the same instructions again and again. The condition is the question that decides whether there is another pass to do.'
    };
  }
  if (helper) {
    return {
      title: 'A recipe you can reuse',
      body: `A function is a named set of instructions. Instead of copying the recipe into every part of the program, you call \`${helper.name}\` and it follows the same steps each time.`
    };
  }
  const firstCondition = findFirstAnyNode(analysis.root, ['if']);
  if (firstCondition) {
    return {
      title: 'A fork in the road',
      body: 'A condition is a fork in the road. The program asks a yes-or-no question, then chooses one route through the code based on the answer.'
    };
  }
  return {
    title: 'A list of instructions',
    body: 'Read this program like a recipe: one instruction at a time, top to bottom. Each statement changes the workspace slightly before the next one begins.'
  };
}

/* -------------------------------------------------------------------------- */
/* Walkthrough                                                                */
/* -------------------------------------------------------------------------- */

function buildWalkthrough(analysis, trace, stats) {
  const steps = [];
  const entry = analysis.entry;

  if (entry?.kind === 'function') {
    const helpers = analysis.functions.filter((fn) => fn !== entry.node).slice(0, 3);
    for (const helper of helpers) {
      steps.push(functionStep(helper, analysis, trace, stats));
    }
    steps.push({
      title: `Execution takes the stage in ${entry.name}()`,
      body: `The entry point receives control here. Everything below this line is part of the program’s main run${analysis.classes.length ? `, inside the container class \`${analysis.classes[0].name}\`` : ''}.`,
      lines: [entry.node.startLine],
      badge: 'ENTRY',
      points: entry.node.params.length
        ? [`Inputs: ${entry.node.params.map((param) => `\`${param.name}\``).join(', ')}`]
        : []
    });
    appendBodySteps(entry.node.body.children, analysis, trace, stats, steps);
  } else {
    appendBodySteps(analysis.root.body.children, analysis, trace, stats, steps);
  }

  if (!steps.length) {
    steps.push({
      title: 'There is not much executable code yet',
      body: 'This snippet mainly contains declarations or definitions. Add a statement that changes a value or prints something, and the walkthrough will have more to follow.',
      lines: [1],
      badge: 'OVERVIEW'
    });
  }

  if (trace?.output?.trim()) {
    const alreadyExplainsOutput = steps.some((step) => step.output);
    if (!alreadyExplainsOutput) {
      steps.push({
        title: 'The program prints its result',
        body: 'The completed run produced the following output:',
        output: trace.output,
        lines: [],
        badge: 'OUTPUT'
      });
    }
  }

  return steps.slice(0, 12);
}

function appendBodySteps(nodes, analysis, trace, stats, steps) {
  let pendingSetup = null;
  const flushSetup = () => {
    if (!pendingSetup) return;
    if (pendingSetup.points.length) steps.push(pendingSetup);
    pendingSetup = null;
  };

  for (const node of nodes ?? []) {
    if (!node) continue;
    if (node.type === 'action' && ['declaration', 'assignment'].includes(node.action?.subtype)) {
      if (!pendingSetup) {
        pendingSetup = {
          title: 'The starting values are put in place',
          body: 'Before the interesting work begins, the program stores the data it will need in named variables.',
          lines: [],
          badge: 'SETUP',
          points: []
        };
      }
      pendingSetup.lines.push(node.startLine);
      pendingSetup.points.push(assignmentPoint(node, analysis, trace));
      continue;
    }

    flushSetup();
    if (node.type === 'function') {
      steps.push(functionStep(node, analysis, trace, stats));
      continue;
    }
    if (node.type === 'class') {
      steps.push({
        title: `The class \`${node.name}\` groups the code`,
        body: 'A class is a container for related data and behavior. In this program it mainly acts as a home for the methods that follow.',
        lines: [node.startLine],
        badge: 'STRUCTURE'
      });
      continue;
    }
    if (node.type === 'for' || node.type === 'while' || node.type === 'do') {
      steps.push(loopStep(node, analysis, trace, stats));
      continue;
    }
    if (node.type === 'if') {
      steps.push(ifStep(node, trace, stats));
      continue;
    }
    if (node.type === 'switch' || node.type === 'try') {
      steps.push({
        title: 'A structured block groups several outcomes',
        body: 'This part of the program is outside the trace interpreter’s subset, so the guide describes its structure without inventing runtime values. The Syntax Tree view shows every nested statement.',
        lines: [node.startLine],
        badge: 'STRUCTURE'
      });
      continue;
    }
    if (node.type === 'action') {
      const action = node.action;
      if (!action || ['import', 'comment', 'empty', 'pass'].includes(action.subtype)) continue;
      if (action.subtype === 'print') {
        const printed = printedAtLine(stats, node.startLine);
        steps.push({
          title: 'The result is sent to the output',
          body: printed
            ? 'The print statement turns the values into text and adds it to the program’s output.'
            : 'This line writes to the output when the program reaches it.',
          output: printed || undefined,
          lines: [node.startLine],
          badge: 'OUTPUT'
        });
        continue;
      }
      if (action.subtype === 'return') {
        steps.push({
          title: 'The function hands back a result',
          body: 'Returning stops the current function immediately and sends a value back to the caller. Any later lines in that function are skipped on this path.',
          lines: [node.startLine],
          badge: 'RETURN'
        });
        continue;
      }
      if (action.subtype === 'call') {
        steps.push({
          title: 'A helper is called',
          body: `The program pauses at the call to \`${action.calleeName ?? 'a function'}\`, runs that function’s body, then continues with the returned value.`,
          lines: [node.startLine],
          badge: 'CALL'
        });
      }
    }
  }
  flushSetup();
}

function assignmentPoint(node, analysis, trace) {
  const action = node.action;
  const target = action.targetDisplay ?? action.targetName ?? 'value';
  const event = trace?.events?.find((item) => item.line === node.startLine && item.target === target);
  const shownValue = event?.value ?? inlineExpressionPreview(action.expressionAST);
  const typeHint = describeValueShape(action.expressionAST);
  const verb = action.isDeclaration ? 'starts as' : 'becomes';
  if (!action.expressionText) {
    return `\`${target}\` is declared here but only receives a value later.`;
  }
  const sameAsValue = action.expressionAST?.type === 'ArrayExpression'
    || (action.expressionText && shownValue && shorten(action.expressionText, 60) === String(shownValue).replace(/^"|"$/g, ''));
  const expression = action.expressionText && !sameAsValue ? ` from \`${shorten(action.expressionText, 50)}\`` : '';
  return `\`${target}\` ${verb} \`${shownValue}\`${typeHint ? ` (${typeHint})` : ''}${expression}.`;
}

function functionStep(fn, analysis, trace, stats) {
  const callCount = stats.functionCalls.get(fn.name) ?? 0;
  const params = fn.params.map((param) => `\`${param.name}\``).join(', ');
  const callsText = callCount
    ? `The sample run enters it ${callCount} time${callCount === 1 ? '' : 's'}.`
    : 'It is defined here and runs only if something calls it.';
  const returnText = describeReturns(fn);
  const received = [];
  const seenParams = new Set();
  for (const event of trace?.events ?? []) {
    if (event.kind !== 'parameter' || event.scope !== fn.name || seenParams.has(event.target)) continue;
    seenParams.add(event.target);
    received.push(`On the first call, \`${event.target}\` receives \`${event.value}\`.`);
  }
  return {
    title: `The reusable helper: ${fn.name}()`,
    body: `This is a named block of instructions${params ? ` that expects ${params}` : ''}. ${returnText} ${callsText}`,
    lines: [fn.startLine],
    badge: 'HELPER',
    points: [
      params ? `Inputs: ${params}` : 'It has no parameters.',
      ...received.slice(0, 3)
    ]
  };
}

function loopStep(node, analysis, trace, stats) {
  const meta = node.loopMeta;
  const iterationPoints = buildIterationPoints(node, trace, stats);
  let body;
  let points = [];
  if (node.type === 'for' && meta?.style === 'forOf') {
    body = `This loop visits each value in \`${meta.iterableText}\` and stores the current value in \`${meta.target}\`. The body runs once per item, so the same instructions adapt to every value in the collection.`;
  } else if (node.type === 'for' && meta?.style === 'forIn' && meta.target) {
    const isIndexOf = ['javascript', 'typescript', 'c', 'cpp', 'java'].includes(analysis.language.id);
    body = isIndexOf
      ? `This loop walks through the positions in \`${meta.iterableText}\`; on each pass \`${meta.target}\` receives the next index, which can then be used to look up the matching value.`
      : `This loop visits each item in \`${meta.iterableText}\` and stores it in \`${meta.target}\` for that pass.`;
  } else if (meta?.style === 'classic') {
    body = `This is a classic three-part loop. It sets up a counter${meta.initText ? ` with \`${meta.initText}\`` : ''}, checks \`${meta.testText}\` before each pass, and updates the counter with \`${meta.updateText}\` afterwards. The condition is the gate: true means one more pass.`;
  } else if (node.type === 'while') {
    body = `Before every pass, the program asks whether \`${node.condition}\` is true. While the answer stays true, the body repeats. When it becomes false, execution continues after the loop.`;
  } else if (node.type === 'do') {
    body = 'A do/while loop runs its body first and only checks the condition afterwards. That guarantees at least one pass.';
  } else {
    body = 'This loop repeats its body until its stopping condition is met.';
  }

  const bodySummary = summarizeBlock(node.body);
  if (bodySummary) points.push(`Inside the body: ${bodySummary}`);
  points = points.concat(iterationPoints);
  const iterations = stats.loopPasses.get(node.startLine) ?? 0;
  if (iterations && !iterationPoints.length) {
    points.push(`The sample run completed ${iterations} pass${iterations === 1 ? '' : 'es'}.`);
  }
  return {
    title: node.type === 'for'
      ? `The loop handles the repetition`
      : 'A condition controls the repetition',
    body,
    lines: [node.startLine],
    badge: 'LOOP',
    points
  };
}

function ifStep(node, trace, stats) {
  const outcomes = stats.conditionOutcomes.get(node.startLine) ?? [];
  const last = outcomes.at(-1);
  return {
    title: 'A decision picks a route',
    body: `The program asks whether \`${node.condition}\` is true. If it is, the if branch runs; ${node.alternate ? 'otherwise the else branch runs' : 'otherwise the branch is skipped'}.`,
    lines: [node.startLine],
    badge: 'DECISION',
    points: outcomes.length
      ? [`In the sample run this check evaluated to \`${String(last).toLowerCase()}\`.`]
      : []
  };
}

function buildIterationPoints(node, trace, stats) {
  if (!trace?.steps?.length) return [];
  const markerSteps = [];
  for (const step of trace.steps) {
    if (step.line !== node.startLine) continue;
    if (step.kind === 'iteration') markerSteps.push(step);
    else if (step.kind === 'loop-check' && /→ true$/.test(step.title)) markerSteps.push(step);
  }
  if (!markerSteps.length) return [];
  const points = [];
  for (let i = 0; i < markerSteps.length && i < 4; i += 1) {
    const marker = markerSteps[i];
    const next = markerSteps[i + 1];
    const events = trace.events.filter((event) => {
      if (!['assignment', 'loop-target'].includes(event.kind)) return false;
      if (event.stepIndex < marker.index) return false;
      if (next && event.stepIndex >= next.index) return false;
      if (event.line < node.body.startLine || event.line > node.body.endLine) return false;
      return true;
    });
    const bits = [];
    const targetEvent = events.find((event) => event.kind === 'loop-target');
    if (targetEvent) bits.push(`\`${targetEvent.target} = ${targetEvent.value}\``);
    const changed = dedupe(events.filter((event) => event.kind === 'assignment').map((event) => `${event.target} = ${event.value}`));
    if (changed.length) bits.push(changed.slice(0, 2).map((piece) => `\`${piece}\``).join(', '));
    if (bits.length) {
      points.push(`Pass ${i + 1}: ${bits.join(' → ')}.`);
    } else {
      const vars = marker.vars?.slice(-2).map((variable) => `\`${variable.name} = ${variable.display}\``) ?? [];
      if (vars.length) points.push(`Pass ${i + 1}: ${vars.join(', ')}.`);
    }
  }
  if (markerSteps.length > 4) {
    points.push(`…and ${markerSteps.length - 4} more pass${markerSteps.length - 4 === 1 ? '' : 'es'}.`);
  }
  return points;
}

function summarizeBlock(block) {
  const parts = [];
  for (const node of block?.children ?? []) {
    if (node.type === 'action') {
      const action = node.action;
      if (!action) continue;
      if (['declaration', 'assignment'].includes(action.subtype)) {
        parts.push(`${action.operator && action.operator !== '=' ? 'updates' : 'sets'} \`${action.targetDisplay ?? action.targetName}\``);
      } else if (action.subtype === 'print') {
        parts.push('prints a value');
      } else if (action.subtype === 'return') {
        parts.push('returns a value');
      } else if (action.subtype === 'call') {
        parts.push(`calls \`${action.calleeName ?? 'a function'}\``);
      } else if (action.subtype === 'break') {
        parts.push('leaves the loop early');
      } else if (action.subtype === 'continue') {
        parts.push('skips to the next pass');
      }
    } else if (node.type === 'if') {
      parts.push(`decides whether \`${shorten(node.condition, 34)}\``);
    } else if (node.type === 'for' || node.type === 'while') {
      parts.push('runs a nested loop');
    }
  }
  if (!parts.length) return '';
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase() + parts[0].slice(1) + '.';
  return parts.join(', then ') + '.';
}

/* -------------------------------------------------------------------------- */
/* Line-by-line notes                                                         */
/* -------------------------------------------------------------------------- */

function buildLineNotes(analysis, trace, stats) {
  const notes = [];
  const seen = new Set();

  const addNote = (line, note, tone, endLine = line, synthetic = false) => {
    if (!Number.isFinite(line) || line < 1 || line > analysis.lineCount) return;
    if (seen.has(line)) return;
    const text = String(note ?? '').trim();
    if (!text) return;
    seen.add(line);
    notes.push({
      line,
      endLine,
      code: (analysis.lines[line - 1]?.text ?? '').trim(),
      note: text,
      tone,
      synthetic
    });
  };

  const visit = (node) => {
    if (!node) return;
    if (node.type === 'program') {
      visit(node.body);
      return;
    }
    if (node.type === 'function') {
      addNote(node.startLine, noteForFunction(node, analysis, trace, stats), 'function', node.startLine);
      visit(node.body);
      return;
    }
    if (node.type === 'class') {
      addNote(
        node.startLine,
        `Declares the class \`${node.name}\`. A class keeps related methods and data together; the methods still run only when called.`,
        'structure',
        node.startLine
      );
      visit(node.body);
      return;
    }
    if (node.type === 'if') {
      addNote(node.startLine, noteForIf(node, trace, stats), 'decision', node.startLine);
      if (node.alternate?.startLine && node.alternate.startLine !== node.startLine) {
        const altLine = analysis.lines[node.alternate.startLine - 1]?.text ?? '';
        if (/\belse\b|\belif\b/.test(altLine)) {
          addNote(node.alternate.startLine, noteForElse(node), 'decision', node.alternate.startLine, true);
        }
      }
      visit(node.consequent);
      visit(node.alternate);
      return;
    }
    if (node.type === 'for' || node.type === 'while' || node.type === 'do') {
      addNote(node.startLine, noteForLoop(node, analysis, trace, stats), 'loop', node.startLine);
      visit(node.body);
      return;
    }
    if (node.type === 'switch') {
      addNote(node.startLine, `Checks \`${node.condition}\` and chooses one of several labelled cases. Each case can fall through to the next unless it breaks.`, 'decision', node.startLine);
      visit(node.body);
      return;
    }
    if (node.type === 'try') {
      addNote(node.startLine, 'Sets up protected code. If something goes wrong here, the matching catch block can respond instead of letting the error escape.', 'structure', node.startLine);
      visit(node.body);
      node.handlers?.forEach((handler) => visit(handler.body));
      return;
    }
    if (node.type === 'block') {
      node.children?.forEach(visit);
      return;
    }
    if (node.type === 'action') {
      const action = node.action;
      if (!action) return;
      if (['comment', 'empty', 'pass'].includes(action.subtype)) return;
      addNote(node.startLine, noteForAction(node, analysis, trace, stats), toneForAction(action), node.endLine);
    }
  };

  visit(analysis.root);
  notes.sort((a, b) => a.line - b.line);
  if (notes.length > MAX_LINE_NOTES) {
    return notes.slice(0, MAX_LINE_NOTES).concat([{
      line: notes[MAX_LINE_NOTES].line,
      endLine: notes[notes.length - 1].line,
      code: '',
      note: `…and ${notes.length - MAX_LINE_NOTES} more annotated lines. The Syntax Tree view contains the complete structure.`,
      tone: 'structure',
      synthetic: true
    }]);
  }
  return notes;
}

function noteForFunction(node, analysis, trace, stats) {
  const params = node.params.map((param) => `\`${param.name}\``).join(', ');
  const callCount = stats.functionCalls.get(node.name) ?? 0;
  const returns = collectReturns(node.body);
  const parts = [];
  const isEntry = analysis.entry?.kind === 'function' && analysis.entry.node === node;
  if (isEntry) {
    parts.push(
      `Defines \`${node.name}\`, the entry point where this ${analysis.language.name} program starts${params ? `, with ${params} supplied by the runtime` : ''}.`
    );
  } else {
    parts.push(
      `Defines the reusable function \`${node.name}\`${params ? `, which expects ${params}` : ''}. The body is stored for later and runs when a call reaches it.`
    );
  }
  if (returns.length === 1) {
    parts.push(`It sends back \`${shorten(returns[0].expression, 42) || 'a result'}\`.`);
  } else if (returns.length > 1) {
    const expressions = dedupe(returns.map((item) => shorten(item.expression, 34)).filter(Boolean));
    parts.push(`It can return ${expressions.slice(0, 3).map((expression) => `\`${expression}\``).join(' or ')} depending on which branch is taken.`);
  }
  if (callCount) parts.push(`The sample run calls it ${callCount} time${callCount === 1 ? '' : 's'}.`);
  return parts.join(' ');
}

function noteForIf(node, trace, stats) {
  const outcomes = stats.conditionOutcomes.get(node.startLine) ?? [];
  const parts = [
    `Asks “\`${shorten(node.condition, 58)}\`?” and runs the indented or braced block only when the answer is true.`
  ];
  const branchSummary = summarizeBlock(node.consequent);
  if (branchSummary) parts.push(`The true branch ${branchSummary.charAt(0).toLowerCase()}${branchSummary.slice(1)}`);
  if (node.alternate) parts.push('If the answer is false, the alternative branch handles it.');
  if (outcomes.length) {
    parts.push(`In the sample run this check was ${outcomes.map((value) => `\`${String(value).toLowerCase()}\``).join(', then ')}.`);
  }
  return parts.join(' ');
}

function noteForElse() {
  return 'The fallback route. This branch runs when the matching if condition was false, so the program has an alternative path instead of stopping.';
}

function noteForLoop(node, analysis, trace, stats) {
  const meta = node.loopMeta;
  const passes = stats.loopPasses.get(node.startLine) ?? 0;
  const parts = [];
  if (node.type === 'for' && meta?.style === 'forOf') {
    parts.push(`Starts a for…of loop over \`${meta.iterableText}\`. On each pass, \`${meta.target}\` holds the next value.`);
  } else if (node.type === 'for' && meta?.style === 'forIn') {
    parts.push(`Starts a for…in loop over \`${meta.iterableText}\`. The loop variable \`${meta.target}\` takes the next key, index, or item depending on the language.`);
  } else if (meta?.style === 'classic') {
    parts.push(`Starts a counted loop. The setup runs once, the condition \`${shorten(meta.testText, 38)}\` is checked before each pass, and \`${shorten(meta.updateText, 28)}\` advances the counter.`);
  } else if (node.type === 'while') {
    parts.push(`Repeats while \`${shorten(node.condition, 44)}\` stays true. The condition is evaluated before every pass.`);
  } else if (node.type === 'do') {
    parts.push('Runs the body once before checking the condition, so this loop always has at least one pass.');
  } else {
    parts.push('Starts a loop that repeats until its stopping condition is reached.');
  }
  const summary = summarizeBlock(node.body);
  if (summary) parts.push(`Each pass ${summary.charAt(0).toLowerCase()}${summary.slice(1)}`);
  if (passes) parts.push(`In the sample run the loop completed ${passes} pass${passes === 1 ? '' : 'es'}.`);
  return parts.join(' ');
}

function noteForAction(node, analysis, trace, stats) {
  const action = node.action;
  const lineEvents = stats.assignmentsByLine.get(node.startLine) ?? [];
  if (action.subtype === 'import') {
    return 'Brings in outside tools or names. An import does not calculate anything itself; it makes other code available under a shorter name.';
  }
  if (action.subtype === 'declaration' || action.subtype === 'assignment') {
    return noteForAssignment(node, action, lineEvents);
  }
  if (action.subtype === 'print') {
    const printed = printedAtLine(stats, node.startLine);
    return printed
      ? `Writes the requested values to the output. The exact text added here in the sample run was \`${shorten(visibleWhitespace(printed), 64)}\`.`
      : 'Writes the requested values to the output. The values are evaluated first, then converted into printable text.';
  }
  if (action.subtype === 'return') {
    const values = stats.returnsByLine.get(node.startLine) ?? [];
    const unique = dedupe(values);
    return `Ends this function immediately and sends a result back to the caller.${
      unique.length ? ` The sample run returned ${unique.slice(0, 3).map((value) => `\`${value}\``).join(', ')}${unique.length > 3 ? ', …' : ''} from this line.` : ''
    }`;
  }
  if (action.subtype === 'call') {
    return `Calls \`${action.calleeName ?? 'a function'}\`. The arguments are evaluated, the called code runs, and execution returns here with a result (or no value at all).`;
  }
  if (action.subtype === 'break') {
    return 'Leaves the nearest loop immediately. Execution resumes after the loop, not with the next pass.';
  }
  if (action.subtype === 'continue') {
    return 'Skips the rest of the current loop body and jumps to the next iteration check.';
  }
  if (action.subtype === 'update') {
    return 'Changes the value by one using the increment or decrement shorthand. This is a compact way to write `value = value + 1` or `value = value - 1`.';
  }
  if (action.subtype === 'throw') {
    return 'Raises an error. Unlike a return, a thrown error travels outward until some error handler catches it.';
  }
  return action.expressionText
    ? `Evaluates \`${shorten(action.expressionText, 52)}\`. If the result is not stored or printed, it only matters for its side effects.`
    : 'A structural statement with no stored value.';
}

function noteForAssignment(node, action, lineEvents) {
  const target = action.targetDisplay ?? action.targetName ?? 'the variable';
  const valueNotes = dedupe(lineEvents.map((event) => `${event.target} = ${event.value}`));
  const parts = [];
  if (action.isDeclaration) {
    parts.push(`Creates \`${target}\` in the current scope${action.declarationType ? ` as ${action.declarationType}` : ''}.`);
  }
  if (action.operator && action.operator !== '=') {
    parts.push(
      `This is an update, not a fresh declaration: the current \`${action.targetName}\` is read, the right-hand side is applied, and the result is written back.`
    );
  } else if (action.expressionText) {
    parts.push(`The right-hand side \`${shorten(action.expressionText, 54)}\` is calculated first, then stored under \`${target}\`.`);
  } else {
    parts.push('The variable is declared without an initial value, so its value is not ready until a later assignment.');
  }
  if (action.expressionAST?.type === 'ArrayExpression') {
    parts.push(`The brackets create an array with ${action.expressionAST.elements.length} item${action.expressionAST.elements.length === 1 ? '' : 's'}; arrays keep values in order and index them starting from 0.`);
  }
  if (lineEvents.length && action.expressionText) {
    if (lineEvents.length === 1) {
      parts.push(`In the sample run this became \`${valueNotes[0]}\`.`);
    } else {
      parts.push(`In the sample run this line executed ${lineEvents.length} times; the recorded values were ${valueNotes.slice(0, 4).map((value) => `\`${value}\``).join(', ')}${valueNotes.length > 4 ? ', …' : ''}.`);
    }
  }
  return parts.join(' ');
}

function toneForAction(action) {
  switch (action.subtype) {
    case 'print': return 'output';
    case 'return':
    case 'break':
    case 'continue':
    case 'throw': return 'return';
    case 'call': return 'call';
    case 'import': return 'structure';
    default: return 'assignment';
  }
}

function collectReturns(root) {
  const results = [];
  const seen = new Set();
  const visit = (node) => {
    if (!node || seen.has(node)) return;
    seen.add(node);
    if (node.type === 'function' && node !== root) return;
    if (node.type === 'action' && node.action?.subtype === 'return') {
      results.push({ line: node.startLine, expression: node.action.expressionText ?? '' });
    }
    if (node.type === 'block') {
      node.children?.forEach(visit);
      return;
    }
    if (node.body?.children) node.body.children.forEach(visit);
    if (node.consequent) visit(node.consequent);
    if (node.alternate) visit(node.alternate);
    node.handlers?.forEach((handler) => visit(handler.body));
  };
  visit(root);
  return results;
}

/* -------------------------------------------------------------------------- */
/* Concepts, pitfalls, quiz                                                   */
/* -------------------------------------------------------------------------- */

function buildConcepts(analysis, trace) {
  const concepts = [];
  const firstFunction = analysis.functions[0];
  const firstLoop = findFirstAnyNode(analysis.root, ['for', 'while', 'do']);
  const firstIf = findFirstAnyNode(analysis.root, ['if']);
  const firstReturn = findFirstAction(analysis, ['return']);
  const firstPrint = findFirstAction(analysis, ['print']);
  const firstAssignment = analysis.assignments[0];
  const arrayNode = analysis.actionNodes.find((node) => node.action?.expressionAST?.type === 'ArrayExpression');
  const typedNode = ['typescript', 'java', 'cpp', 'c'].includes(analysis.language.id)
    ? analysis.actionNodes.find((node) => node.action?.declarationType) ?? analysis.functions.find((fn) => fn.returnType)
    : null;

  if (firstFunction) {
    concepts.push({
      term: 'Function',
      definition: 'A reusable block of instructions with a name. Defining it only prepares the recipe; the code inside runs when the function is called.',
      inThisCode: `\`${firstFunction.name}\` is defined once and called from the main flow, so the same logic does not need to be copied.`,
      line: firstFunction.startLine
    });
    if (firstFunction.params.length) {
      concepts.push({
        term: 'Parameters & arguments',
        definition: 'Parameters are the named inputs a function expects. Arguments are the actual values supplied by a particular call.',
        inThisCode: `\`${firstFunction.name}\` expects ${firstFunction.params.map((param) => `\`${param.name}\``).join(', ')}; each call fills those slots with concrete values.`,
        line: firstFunction.startLine
      });
    }
  }
  if (firstLoop) {
    concepts.push({
      term: 'Loop',
      definition: 'A loop repeats a block of code. It needs a starting point, a stopping condition, and a way to make progress; otherwise it can run forever.',
      inThisCode: firstLoop.type === 'for'
        ? `A \`for\` loop handles the repetition here, so one written body can process every item instead of being copied by hand.`
        : `A \`while\` loop re-checks its condition before each pass.`,
      line: firstLoop.startLine
    });
  }
  if (firstIf) {
    concepts.push({
      term: 'Condition',
      definition: 'A condition is a yes-or-no question. The program follows one path when the answer is true and another when it is false.',
      inThisCode: `The check on \`${shorten(firstIf.condition, 44)}\` decides which branch runs.`,
      line: firstIf.startLine
    });
  }
  if (firstAssignment) {
    concepts.push({
      term: 'Variables & assignment',
      definition: 'A variable is a named container for a value. Assignment stores or replaces the value; a declaration introduces the name in the first place.',
      inThisCode: `\`${firstAssignment.target}\` is the first named value stored here. A later assignment can replace what is inside without changing the name.`,
      line: firstAssignment.line
    });
  }
  if (arrayNode) {
    concepts.push({
      term: 'Array / list',
      definition: 'An ordered collection of values. Items are accessed by position, and most languages count that position from 0.',
      inThisCode: `The brackets on line ${arrayNode.startLine} create a collection; the loop can then visit its items one by one.`,
      line: arrayNode.startLine
    });
  }
  if (firstReturn) {
    concepts.push({
      term: 'Return value',
      definition: 'A return ends the current function and hands a value back to the caller. Code after the return in that function does not run on that path.',
      inThisCode: `The return on line ${firstReturn.startLine} feeds the caller with the result it needs to continue.`,
      line: firstReturn.startLine
    });
  }
  if (firstPrint) {
    concepts.push({
      term: 'Output',
      definition: 'Printing turns values into visible text. It does not change the values; it reports them to a terminal or console.',
      inThisCode: `The output statement on line ${firstPrint.startLine} is how the program communicates its final result to you.`,
      line: firstPrint.startLine
    });
  }
  if (typedNode) {
    concepts.push({
      term: 'Type annotations',
      definition: 'A type annotation is a label that states what kind of value a name is allowed to hold. Types make intent clearer and help tools catch mistakes.',
      inThisCode: 'The code labels some values with types, but those labels do not perform the calculation; they describe what shape the value should have.',
      line: typedNode.startLine
    });
  }
  if (analysis.classes.length) {
    concepts.push({
      term: 'Class',
      definition: 'A class groups related data and methods into one named container. A program instantiates or uses it to organise behaviour.',
      inThisCode: `\`${analysis.classes[0].name}\` is the container for the methods that make up this program.`,
      line: analysis.classes[0].startLine
    });
  }
  if (analysis.language.family === 'python') {
    concepts.push({
      term: 'Indentation as structure',
      definition: 'Python uses leading spaces to show which lines belong inside a function, loop, or condition. The indentation is part of the syntax, not decoration.',
      inThisCode: 'The deeper-indented lines are the repeated or conditional part of the program.',
      line: firstLoop?.startLine ?? firstFunction?.startLine ?? 1
    });
  }
  if (trace?.complete && trace.output) {
    concepts.push({
      term: 'Program state',
      definition: 'The state is the collection of current variable values at a moment in the run. Each assignment changes the state a little.',
      inThisCode: 'Use Live Trace to see the state change step by step instead of trying to hold every value in your head at once.',
      line: 1
    });
  }
  return concepts.slice(0, 9);
}

function buildWatchOuts(analysis, trace) {
  const items = [];
  const language = analysis.language;
  const firstLoop = findFirstAnyNode(analysis.root, ['for', 'while', 'do']);
  const firstFunction = analysis.functions[0];
  const source = analysis.source;

  if (firstLoop && /[<>]=?/.test(firstLoop.loopMeta?.testText ?? firstLoop.condition ?? '')) {
    const condition = firstLoop.loopMeta?.testText ?? firstLoop.condition ?? '';
    const usesLength = firstLoop.loopMeta?.iterableText?.includes('length') || firstLoop.loopMeta?.style === 'classic' && /length/.test(condition);
    items.push({
      title: 'The loop boundary decides how many passes happen',
      body: `The condition \`${shorten(condition, 44)}\` is checked once per pass. Changing \`<\` to \`<=\` lets the loop run one extra time; that is a common source of off-by-one bugs${usesLength ? ', especially when the right side is an array’s length' : ''}.`
    });
  }

  if (firstFunction && collectReturns(firstFunction.body).some((item) => item.expression)) {
    items.push({
      title: 'A return exits immediately',
      body: `When a \`return\` runs inside \`${firstFunction.name}\`, the function stops there. Statements after it in the same function do not run on that path, even if they look like the “main” ending.`
    });
  }

  if (language.id === 'python') {
    items.push({
      title: 'Spaces are syntax in Python',
      body: 'If a line is indented by the wrong amount, Python can put it in the wrong block or reject the program. Use a consistent number of spaces — four per level is the usual choice.'
    });
  }

  if (['javascript', 'typescript'].includes(language.id) && /(^|[^=!])==([^=]|$)|!=/.test(source.replace(/===|!==/g, ''))) {
    items.push({
      title: 'Loose equality can hide type surprises',
      body: 'JavaScript’s `==` converts types before comparing, while `===` compares type and value together. For predictable beginner code, prefer `===` and `!==` unless loose conversion is intentional.'
    });
  }

  if (['c', 'cpp', 'java'].includes(language.id) && analysis.assignments.some((assignment) => !assignment.expressionText)) {
    items.push({
      title: 'A declared variable is not automatically useful',
      body: 'This program contains a declaration without an initial value. In C and C++ such a variable can hold an unpredictable leftover value until it is assigned, so never read it first. Java gives fields defaults but still requires local variables to be assigned before use.'
    });
  }

  if (analysis.actionNodes.some((node) => node.action?.expressionAST?.type === 'ArrayExpression') && firstLoop) {
    items.push({
      title: 'Array positions start at zero',
      body: 'The first item sits at index 0, not 1. A loop that starts at 1 therefore skips the first item; a loop that goes one past the last index reads outside the array.'
    });
  }

  if (!items.length) {
    items.push({
      title: 'Read the value, not just the instruction',
      body: 'The most common beginner mistake is reading a line in isolation. Before each assignment, ask what value the variable held on the previous line; the effect of the line depends on that starting point.'
    });
    items.push({
      title: 'The sample run is one scenario',
      body: 'The trace uses the values written in this code. Different input values can take different branches, so the sample explains this particular path rather than every possible path.'
    });
  }

  if (items.length < 2) {
    items.push({
      title: 'Watch the state between lines',
      body: 'A program does not remember the code; it remembers the current values. Use Live Trace when you are unsure what a variable contains at a particular moment.'
    });
  }
  return items.slice(0, 3);
}

function buildQuiz(analysis, trace, stats) {
  const quiz = [];
  if (trace?.complete && trace.output?.trim()) {
    quiz.push({
      question: 'What exact text did this run print?',
      answer: `\`${previewOutput(trace.output, 140)}\``
    });
  }
  const loop = findFirstExecutionLoop(analysis);
  if (loop) {
    const passes = stats.loopPasses.get(loop.startLine) ?? 0;
    if (passes) {
      quiz.push({
        question: `How many times did the loop on line ${loop.startLine} run in the sample?`,
        answer: `${passes} time${passes === 1 ? '' : 's'}. ${loop.loopMeta?.testText ? `The condition \`${loop.loopMeta.testText}\` stayed true for exactly that many passes.` : 'Count the trace’s iteration markers to confirm it.'}`
      });
    }
  }
  const accumulator = findAccumulator(analysis, loop);
  if (accumulator) {
    const finalValue = trace?.finalVars?.find((variable) => variable.name === accumulator)?.display;
    quiz.push({
      question: `Why does \`${accumulator}\` change on multiple lines or multiple times?`,
      answer: finalValue
        ? `It is the running value. Each pass updates it using the previous value, so it grows rather than being reset. The sample ends with \`${accumulator} = ${finalValue}\`.`
        : 'It is the running value: it is read, changed, and written back on repeated passes instead of being reset.'
    });
  }
  const helper = analysis.functions[0];
  if (helper && analysis.assignments.some((assignment) => assignment.expressionText?.match(new RegExp(`\\b${escapeRegExp(helper.name)}\\b`)))) {
    quiz.push({
      question: `Why is \`${helper.name}\` defined separately instead of putting its code directly in the loop?`,
      answer: `Separating it gives the rule a name and keeps the loop focused on repetition. If the rule changes later, there is one place to edit, and the function can be tested or reused outside this loop.`
    });
  }
  if (!quiz.length) {
    quiz.push({
      question: 'What is the best first step when reading this program?',
      answer: 'Start with the values that are stored before any branching, then follow the path taken by the sample run. The Line by line tab is arranged in exactly that order.'
    });
  }
  return quiz.slice(0, 3);
}

/* -------------------------------------------------------------------------- */
/* Trace indexing and small helpers                                           */
/* -------------------------------------------------------------------------- */

function buildTraceStats(trace) {
  const stats = {
    assignmentsByLine: new Map(),
    conditionsByLine: new Map(),
    conditionOutcomes: new Map(),
    loopPasses: new Map(),
    functionCalls: new Map(),
    printsByLine: new Map(),
    returnsByLine: new Map(),
    iterationEventsByLine: new Map()
  };
  if (!trace) return stats;

  const pushToMap = (map, key, value) => {
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(value);
  };

  for (const event of trace.events ?? []) {
    if (['assignment', 'loop-target', 'parameter'].includes(event.kind)) {
      pushToMap(stats.assignmentsByLine, event.line, event);
    }
  }
  for (const step of trace.steps ?? []) {
    if (step.kind === 'print') {
      pushToMap(stats.printsByLine, step.line, step.extra?.printed ?? '');
    } else if (step.kind === 'return') {
      const value = step.extra?.value ?? extractReturnedValue(step.title);
      if (value !== undefined) pushToMap(stats.returnsByLine, step.line, value);
    } else if (step.kind === 'condition') {
      const truthy = !!step.extra?.truthy;
      pushToMap(stats.conditionOutcomes, step.line, truthy);
    } else if (step.kind === 'loop-check') {
      const truthy = /→ true$/.test(step.title);
      if (truthy) {
        stats.loopPasses.set(step.line, (stats.loopPasses.get(step.line) ?? 0) + 1);
      }
    } else if (step.kind === 'iteration') {
      stats.loopPasses.set(step.line, (stats.loopPasses.get(step.line) ?? 0) + 1);
      pushToMap(stats.iterationEventsByLine, step.line, step.extra);
    } else if (step.kind === 'call' && step.extra?.callee) {
      stats.functionCalls.set(step.extra.callee, (stats.functionCalls.get(step.extra.callee) ?? 0) + 1);
    }
  }
  return stats;
}

function printedAtLine(stats, line) {
  const values = stats.printsByLine.get(line) ?? [];
  return values.join('');
}

function extractReturnedValue(title) {
  const match = String(title ?? '').match(/^Return (.+)$/);
  return match?.[1] ?? undefined;
}

function describeReturns(fn) {
  const returns = collectReturns(fn.body);
  if (!returns.length) return 'It does not explicitly return a value.';
  const unique = dedupe(returns.map((item) => item.expression).filter(Boolean));
  if (!unique.length) return 'It can return without a value.';
  if (unique.length === 1) return `It hands back \`${shorten(unique[0], 44)}\`.`;
  return `It can hand back ${unique.slice(0, 3).map((expression) => `\`${shorten(expression, 36)}\``).join(' or ')}, depending on the path taken.`;
}

function findFirstAnyNode(root, types) {
  let result = null;
  const seen = new Set();
  const visit = (node) => {
    if (!node || result || seen.has(node)) return;
    seen.add(node);
    if (types.includes(node.type)) {
      result = node;
      return;
    }
    if (node.type === 'block') {
      node.children?.forEach(visit);
      return;
    }
    if (node.body?.children) node.body.children.forEach(visit);
    if (node.consequent) visit(node.consequent);
    if (node.alternate) visit(node.alternate);
    node.handlers?.forEach((handler) => visit(handler.body));
  };
  visit(root);
  return result;
}

function findFirstExecutionLoop(analysis) {
  const nodes = analysis.entry?.kind === 'function' ? analysis.entry.node.body.children : analysis.root.body.children;
  for (const node of nodes) {
    if (node.type === 'for' || node.type === 'while' || node.type === 'do') return node;
    if (node.type === 'if') {
      const nested = findFirstAnyNode(node.consequent, ['for', 'while', 'do']) ?? findFirstAnyNode(node.alternate, ['for', 'while', 'do']);
      if (nested) return nested;
    }
  }
  return findFirstAnyNode(analysis.root, ['for', 'while', 'do']);
}

function findFirstExecutionPrint(analysis) {
  const nodes = analysis.entry?.kind === 'function' ? analysis.entry.node.body.children : analysis.root.body.children;
  for (const node of nodes) {
    if (node.type === 'action' && node.action?.subtype === 'print') return node;
  }
  return findFirstAction(analysis, ['print']);
}

function findFirstAction(analysis, subtypes) {
  return analysis.actionNodes.find((node) => subtypes.includes(node.action?.subtype)) ?? null;
}

function findHelperCalledByLoop(analysis, loop) {
  if (!loop) return null;
  const functionNames = new Set(analysis.functions.map((fn) => fn.name));
  const texts = [];
  const seen = new Set();
  const visit = (node) => {
    if (!node || seen.has(node)) return;
    seen.add(node);
    if (node.type === 'block') {
      node.children?.forEach(visit);
      return;
    }
    if (node.type === 'action' && node.action?.expressionText) texts.push(node.action.expressionText);
    if (node.body?.children) node.body.children.forEach(visit);
    if (node.consequent) visit(node.consequent);
    if (node.alternate) visit(node.alternate);
  };
  visit(loop.body);
  for (const fn of analysis.functions) {
    if (!functionNames.has(fn.name)) continue;
    if (texts.some((text) => new RegExp(`\\b${escapeRegExp(fn.name)}\\s*\\(`).test(text))) return fn;
  }
  return null;
}

function findAccumulator(analysis, loop) {
  if (!loop) {
    const compound = analysis.assignments.find((assignment) => assignment.operator && assignment.operator !== '=');
    return compound?.target ?? null;
  }
  const candidates = [];
  const seen = new Set();
  const visit = (node) => {
    if (!node || seen.has(node)) return;
    seen.add(node);
    if (node.type === 'block') {
      node.children?.forEach(visit);
      return;
    }
    if (node.type === 'action' && node.action?.subtype === 'assignment') {
      candidates.push(node.action);
    }
    if (node.body?.children) node.body.children.forEach(visit);
    if (node.consequent) visit(node.consequent);
    if (node.alternate) visit(node.alternate);
  };
  visit(loop.body);
  const compound = candidates.find((action) => action.operator && action.operator !== '=');
  return compound?.targetDisplay ?? compound?.targetName ?? null;
}

function simpleIterableName(loop) {
  const text = loop?.loopMeta?.iterableText;
  if (!text) return '';
  const match = String(text).trim().match(/^[A-Za-z_$][\w$]*$/);
  return match ? match[0] : '';
}

function describeValueShape(ast) {
  if (!ast) return '';
  if (ast.type === 'ArrayExpression') return `array with ${ast.elements.length} item${ast.elements.length === 1 ? '' : 's'}`;
  if (ast.type === 'Literal') {
    if (ast.valueType === 'number') return 'number';
    if (ast.valueType === 'string') return 'text';
    if (ast.valueType === 'boolean') return 'true/false value';
    if (ast.valueType === 'null') return 'empty value';
  }
  if (ast.type === 'BinaryExpression') return 'calculated value';
  if (ast.type === 'CallExpression') return 'function result';
  return '';
}

function inlineExpressionPreview(ast) {
  if (!ast) return 'a value';
  return shorten(prettyExpression(ast), 38);
}

function prettyExpression(node) {
  if (!node) return '';
  switch (node.type) {
    case 'Literal': return node.raw ?? String(node.value);
    case 'Identifier': return node.name;
    case 'MemberExpression': return `${prettyExpression(node.object)}.${prettyExpression(node.property)}`;
    case 'CallExpression': return `${prettyExpression(node.callee)}(…)`;
    case 'BinaryExpression':
    case 'LogicalExpression': return `${prettyExpression(node.left)} ${node.operator} ${prettyExpression(node.right)}`;
    case 'ArrayExpression': return `[${node.elements.map(prettyExpression).join(', ')}]`;
    default: return node.text ?? '';
  }
}

function shorten(value, limit) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function previewOutput(value, limit) {
  const clean = String(value ?? '').replace(/\r/g, '').replace(/\n/g, ' ⏎ ').trim();
  return shorten(clean, limit);
}

function visibleWhitespace(value) {
  return String(value ?? '').replace(/\n/g, '⏎').replace(/\t/g, '→');
}

function dedupe(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    if (seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
