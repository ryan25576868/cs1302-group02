"""Interface strings for Prism.

English is the source language: the string passed to :func:`tr` is both the key
and the fallback, so a missing translation degrades to readable English rather
than to ``compare.title``-style keys. Adding a language means adding one dict.

The analysis text Prism generates (guides, trace notes) stays in English; this
module only covers the interface around it.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

LANGUAGES = [
    ("en", "English"),
    ("zh", "简体中文"),
]

_TABLES: Dict[str, Dict[str, str]] = {
    "en": {},
    "zh": {
        # -- window chrome -------------------------------------------------
        "Prism — code analysis workspace": "Prism — 代码分析工作台",
        "CODE WORKSPACE": "代码工作台",
        "Connect AI": "连接 AI",
        "Local · six languages": "本地 · 六种语言",
        "Local · Python": "本地 · Python",
        "Local · Python / JavaScript / TypeScript / Java / C++ / C":
            "本地 · Python / JavaScript / TypeScript / Java / C++ / C",
        "Compare · structural diff between two versions": "对比 · 两个版本的结构差异",
        "UI language": "界面语言",
        # -- menus ---------------------------------------------------------
        "&File": "文件(&F)",
        "&View": "视图(&V)",
        "&Tools": "工具(&T)",
        "&Help": "帮助(&H)",
        "New analysis": "新建分析",
        "Open Python file…": "打开源文件…",
        "Save guide…": "保存讲解…",
        "Quit": "退出",
        "Toggle full screen": "切换全屏",
        "Compare two versions…": "对比两个版本…",
        "Connect AI…": "连接 AI…",
        "Enhance current guide…": "增强当前讲解…",
        "About Prism": "关于 Prism",
        # -- welcome -------------------------------------------------------
        "LOCAL CODE WORKSPACE": "本地代码工作台",
        "Code, made clear.": "让代码看得明白。",
        "Write or import code. Prism explains the flow, structure, execution, "
        "and data without leaving this window.":
            "写上一段代码，或者导入一个文件。Prism 不离开这个窗口就能讲清楚它的"
            "流程、结构、执行过程和数据。",
        "Start an analysis": "开始一次分析",
        "The document starts blank. Open the editor, import a source file, or try a case.":
            "文档从空白开始。打开编辑器、导入源文件，或者试试示例。",
        "Language": "语言",
        "Open editor": "打开编辑器",
        "Import file": "导入文件",
        "Try a case": "试试示例",
        "Compare versions": "对比版本",
        "FLOWCHART   Trace decisions and loops\n"
        "SYNTAX TREE   Inspect the AST structure\n"
        "LIVE TRACE   Step through the safe run\n"
        "DATA FLOW   Follow values to their use\n"
        "GUIDE   Read the explanation beside the code":
            "流程图   跟踪分支与循环\n"
            "语法树   查看 AST 结构\n"
            "实时跟踪   逐步走一遍安全执行\n"
            "数据流   跟随变量到使用处\n"
            "讲解   在代码旁边读说明",
        "Local only · Python · JavaScript · TypeScript · Java · C++ · C":
            "仅本地运行 · Python · JavaScript · TypeScript · Java · C++ · C",
        # -- editor --------------------------------------------------------
        "← Welcome": "← 首页",
        "Import": "导入",
        "Clear": "清空",
        "Write Python code here…": "在这里写代码…",
        "Blank document": "空白文档",
        "Visualize & explain": "可视化并讲解",
        "Import source file": "导入源文件",
        "Code files": "代码文件",
        "Could not read file": "无法读取文件",
        "File too large": "文件太大",
        "Source files must stay under 60,000 characters.": "源文件不能超过 60,000 个字符。",
        # -- results -------------------------------------------------------
        "Enhance guide": "增强讲解",
        "Edit code": "编辑代码",
        "Save guide": "保存讲解",
        "Flowchart": "流程图",
        "Syntax Tree": "语法树",
        "Live Trace": "实时跟踪",
        "Data Flow": "数据流",
        "Guide": "讲解",
        # -- Function POV -----------------------------------------------
        "Function POV": "函数 POV",
        "Function POV currently supports Python only.":
            "函数 POV 目前只支持 Python。",
        "Function POV is available for this Python analysis.":
            "此 Python 分析可以使用函数 POV。",
        "Open Function POV to see language support.":
            "打开函数 POV 查看语言支持说明。",
        "Function POV · safe Python simulation": "函数 POV · 安全 Python 模拟",
        "← Back to analysis": "← 返回分析结果",
        "FUNCTION POV · SAFE PRACTICE": "函数 POV · 安全练习",
        "BE THE CODE · SAFE PRACTICE": "成为代码 · 安全练习",
        "Be the Code": "成为代码",
        "Be the Function": "成为函数",
        "A FUNCTION IS A JOURNEY": "走进函数的执行旅程",
        "A PROGRAM IS A JOURNEY": "走进程序的执行旅程",
        "Follow top-level statements, changing values, decisions, loops, and output. "
        "Prism uses a bounded simulation; it never runs your Python code.":
            "跟随顶层语句、变量变化、判断、循环和输出。Prism 使用有边界的模拟，"
            "绝不会运行你的 Python 代码。",
        "Choose a function, follow its values, and practise each decision. "
        "Prism uses a bounded simulation; it never runs your Python code.":
            "选择一个函数，跟随变量的变化并练习每个判断。Prism 使用有边界的模拟，"
            "绝不会运行你的 Python 代码。",
        "CHOOSE A FUNCTION": "选择函数",
        "WHOLE PROGRAM": "整个程序",
        "Program": "程序",
        "Follow executable top-level statements from start to finish.":
            "从头到尾跟随可执行的顶层语句。",
        "Only a bounded Python subset is simulated. Unsupported statements are explained before play.":
            "这里只模拟有边界的 Python 子集。不支持的语句会在开始前说明。",
        "Trace whole program": "跟踪整个程序",
        "This program is outside the safe simulation subset: {error}":
            "此程序使用了安全模拟范围之外的语法：{error}",
        "Ready for Be the Code. The simulator follows bounded steps and never executes your Python code.":
            "可以开始“成为代码”。模拟器会在有限步骤内跟踪程序，绝不会执行你的 Python 代码。",
        "No executable statements were found.": "没有找到可执行语句。",
        "Select a function": "选择一个函数",
        "Function details and arguments will appear here.": "函数信息和参数会显示在这里。",
        "ARGUMENTS · ENTER JSON VALUES": "参数 · 输入 JSON 值",
        "Blank optional arguments use their defaults. Only a safe subset of Python is simulated.":
            "可选参数留空时使用默认值。这里只模拟 Python 的安全子集。",
        "Enter function space": "进入函数空间",
        "Select a supported function to begin.": "选择一个受支持的函数开始练习。",
        "YOUR FUNCTION · CURRENT LINE HIGHLIGHTED": "当前函数 · 高亮显示正在执行的行",
        "CALL STACK": "调用栈",
        "LOCAL VARIABLES": "局部变量",
        "ANSWER HISTORY": "答题记录",
        "← Previous": "← 上一步",
        "↻ Restart": "↻ 重新开始",
        "Hint": "提示",
        "Show answer": "显示答案",
        "Check answer": "检查答案",
        "↻ Replay function": "↻ 重玩函数",
        "↻ Replay program": "↻ 重玩程序",
        "PROGRAM STEP {current} OF {total}": "程序第 {current}/{total} 步",
        "WHOLE PROGRAM · {file}": "整个程序 · {file}",
        "PROGRAM CALL STACK": "程序调用栈",
        "PROGRAM VARIABLES": "程序变量",
        "Predict the first meaningful operation.": "预测首先出现的重要操作。",
        "The program finished. Review its final output.": "程序已结束。查看最终输出。",
        "State update: {expression}": "状态更新：{expression}",
        "Does the loop condition evaluate to True or False?": "循环条件的结果是 True 还是 False？",
        "Will the for loop execute another pass?": "for 循环还会再执行一轮吗？",
        "Check whether any values remain in the iterable.":
            "请检查可迭代对象中是否还有剩余值。",
        "What value is assigned to {target} in the next loop pass?":
            "下一轮循环会给 {target} 赋什么值？",
        "Loop state: {expression}": "循环状态：{expression}",
        "What text does this print call output?": "这次 print 会输出什么文本？",
        "Choose whether the loop continues or stops.": "选择循环继续还是停止。",
        "Enter the next loop value as a JSON value.": "以 JSON 值输入下一轮循环值。",
        "Choose the first meaningful operation in the program.":
            "选择程序中首先出现的重要操作。",
        "Enter the printed text as a JSON string.": "以 JSON 字符串输入输出文本。",
        "Branch decision": "分支判断",
        "Loop iteration": "循环迭代",
        "Variable update": "变量更新",
        "Function call": "函数调用",
        "Output": "输出",
        "New Values": "更换数值",
        "Similar Logic": "相似逻辑",
        "condition": "条件判断",
        "branch": "分支",
        "loop": "循环",
        "arithmetic": "算术运算",
        "return": "返回值",
        "function parameters": "函数参数",
        "related Python concepts": "相关 Python 概念",
        "Practice Similar Questions": "练习类似题目",
        "Choose a practice level. The original source stays unchanged, and each new exercise is checked by Prism's safe simulator.":
            "选择练习级别。原始代码保持不变，每道新题都会由 Prism 安全模拟器验证。",
        "Original exercise": "原始练习",
        "New exercise · compare before starting": "新练习 · 开始前可与原题对照",
        "Original arguments: {values}": "原始参数：{values}",
        "New arguments: {values}": "新参数：{values}",
        "← Back to completion": "← 返回完成页",
        "Start this exercise": "开始此练习",
        "Choose a level to generate a verified practice exercise.":
            "选择一个级别，生成经过验证的练习题。",
        "Generated {level} exercise. Concepts: {concepts}. The candidate passed safe simulation.":
            "已生成“{level}”练习。涉及概念：{concepts}。该题已通过安全模拟验证。",
        "Logic change: {explanation}": "逻辑变化：{explanation}",
        "The comparison rule changed; practise evaluating the condition and choosing a branch.":
            "比较规则发生了变化；练习判断条件并选择对应分支。",
        "The arithmetic or variable-update rule changed; practise tracing each calculation.":
            "算术运算或变量更新规则发生了变化；练习逐步跟踪计算。",
        "The branch or loop structure changed; practise tracing the new execution path.":
            "分支或循环结构发生了变化；练习跟踪新的执行路径。",
        "The expression structure changed; practise tracing how it affects the result.":
            "表达式结构发生了变化；练习跟踪它如何影响结果。",
        "Complete an original practice first to create a similar exercise.":
            "请先完成一道原始练习，再生成类似题目。",
        "This practice mode is not supported.": "此练习模式不受支持。",
        "This exercise level is not supported.": "此练习级别不受支持。",
        "No safe, unused New Values exercise is available for this code.":
            "此代码没有可安全生成且未练习过的“更换数值”题目。",
        "This code does not match a supported Similar Logic pattern.":
            "此代码不符合当前支持的“相似逻辑”题型。",
        "No unused Similar Logic exercise passed safe simulation.":
            "没有未练习过且通过安全模拟的“相似逻辑”题目。",
        "Exercise search reached its safe candidate limit without finding a new variant.":
            "在安全候选数量上限内未找到新的练习题。",
        "Practice level: {level} · Concepts: {concepts}":
            "练习级别：{level} · 涉及概念：{concepts}",
        "True": "True",
        "False": "False",
        "State updated: {state}": "状态已更新：{state}",
        "Loop pass state: {state}": "本轮循环状态：{state}",
        "Program output: {output}": "程序输出：{output}",
        "No output was produced.": "程序没有产生输出。",
        "Review the source before the first operation.": "先查看代码，再开始第一个操作。",
        "Calculate the result using the values shown.": "根据显示的变量值计算结果。",
        "Choose the branch that matches this condition.": "选择符合此条件的分支。",
        "Choose the function called at this line.": "选择这一行调用的函数。",
        "Predict the text printed here.": "预测这里输出的文本。",
        "Not quite. Substitute the current values, then apply the operator. "
        "For an update, start with the variable's previous value.":
            "还不对。请代入当前变量值并应用运算符；更新变量时，先使用它之前的值。",
        "Not quite. Evaluate the comparison with the values shown, then follow "
        "the matching True or False branch.":
            "还不对。请用显示的值计算比较结果，再进入对应的 True 或 False 分支。",
        "Not quite. Read the iterable from left to right; each loop pass uses "
        "the next value, not the previous one.":
            "还不对。请从左到右查看可迭代对象；每轮循环使用下一个值，而不是上一个值。",
        "Not quite. Re-evaluate the loop condition with the updated variables "
        "to decide whether another iteration occurs.":
            "还不对。请用更新后的变量重新计算循环条件，判断是否还要迭代。",
        "Not quite. Check whether another value remains in the iterable.":
            "还不对。请检查可迭代对象中是否还有下一个值。",
        "Not quite. Evaluate each print argument in order, convert the values "
        "to text, and join them with spaces.":
            "还不对。请按顺序计算 print 的各个参数，将结果转为文本后用空格连接。",
        "Not quite. Evaluate the return expression using this function's local "
        "variables; that value is passed back to the caller.":
            "还不对。请用此函数的局部变量计算 return 表达式；该值会传回调用者。",
        "Not quite. Match the called function name, then trace how its arguments "
        "become local parameter values.":
            "还不对。请确认被调用的函数名称，再跟踪实参如何成为函数的局部参数值。",
        "Not quite. Look past simple assignments for the first decision, loop, update, call, or output.":
            "还不对。略过简单赋值，寻找第一个判断、循环、更新、调用或输出。",
        "Substitute the current values into the while condition.":
            "将当前变量值代入 while 条件。",
        "Follow the iterable from left to right and find the next value.":
            "从左到右查看可迭代对象，找出下一个值。",
        "Evaluate each print argument, convert it to text, then join them with spaces.":
            "分别计算 print 的参数，将其转换为文本后用空格连接。",
        "Skip simple assignments and find the first decision, loop, update, call, or output.":
            "略过简单赋值，寻找第一个判断、循环、更新、调用或输出。",
        "Mode: Be the Code\nChallenges: {total} · Solved by you: {solved} · "
        "Answers revealed: {revealed} · Attempts: {attempts}{practice}\n"
        "Final output:\n{output}\nFinal variables: {variables}":
            "模式：成为代码\n挑战：{total} · 自行答对：{solved} · 查看答案：{revealed} · "
            "尝试次数：{attempts}{practice}\n最终输出：\n{output}\n最终变量：{variables}",
        "Output shortened for display.": "输出过长，摘要中已截短。",
        "MISSION COMPLETE": "任务完成",
        "Stage clear!": "关卡完成！",
        "Python syntax could not be analysed: {error}": "无法分析 Python 语法：{error}",
        "No top-level synchronous functions were found. "
        "Function POV needs a regular def function to begin.":
            "没有找到顶层同步函数。函数 POV 需要普通的 def 函数才能开始。",
        "This is a simplified, bounded simulation. Unsupported syntax is explained before play.":
            "这是简化且有边界的模拟。不支持的语法会在开始前说明。",
        "Other structures may be outside the supported subset: {details}":
            "其他结构可能不在支持范围内：{details}",
        "No docstring is available for this function.": "此函数没有文档字符串。",
        "Calls: {calls} · Called by: {callers}": "调用：{calls} · 被调用：{callers}",
        "none": "无",
        "Leave blank to use default": "留空以使用默认值",
        "Required JSON value": "必填的 JSON 值",
        "This function has no parameters.": "此函数没有参数。",
        "This function uses advanced parameter syntax. "
        "Phase 1 supports simple positional parameters only.":
            "此函数使用了高级参数语法。第一阶段仅支持简单的位置参数。",
        "Blank optional arguments use their defaults. "
        "The simulation never executes your code.":
            "可选参数留空时使用默认值。模拟过程绝不会执行你的代码。",
        "Enter {name} as a JSON value, such as 4, true, or \"hello\".":
            "请将 {name} 输入为 JSON 值，例如 4、true 或 \"hello\"。",
        "This function is outside the safe simulation subset: {error}":
            "此函数使用了安全模拟范围之外的语法：{error}",
        "Python source must be text.": "Python 源码必须是文本。",
        "The value for {name} is nested too deeply.":
            "{name} 的值嵌套层级过深。",
        "The value for {name} is too long.": "{name} 的值过长。",
        "The value for {name} is too large.": "{name} 的值过大。",
        "The value for {name} must be a finite number.":
            "{name} 必须是有限数值。",
        "The value for {name} has too many items.":
            "{name} 包含的项目过多。",
        "The value for {name} must be a small object with string keys.":
            "{name} 必须是键为字符串且规模较小的对象。",
        "The value for {name} must be a JSON value.":
            "{name} 必须是有效的 JSON 值。",
        "Arguments must be an object with parameter names and values.":
            "参数必须是由参数名和值组成的对象。",
        "Too many function arguments.": "函数参数过多。",
        "Argument names must be valid parameter names.":
            "参数名必须是有效的标识符。",
        "This function has no supported steps to simulate.":
            "此函数没有可模拟的受支持步骤。",
        "This program has no executable top-level statements.":
            "此程序没有可执行的顶层语句。",
        "The requested POV step does not exist.": "请求的 POV 步骤不存在。",
        "Program output exceeded the safe size limit.":
            "程序输出超过了安全大小限制。",
        "Python source exceeds the safe simulation limit of {limit} characters.":
            "Python 源码超过安全模拟长度上限（{limit} 个字符）。",
        "Python code could not be simulated safely. Check the syntax and supported subset.":
            "无法安全模拟此 Python 代码。请检查语法，并确认代码使用了受支持的语法。",
        "Python code could not be simulated at line {line}. Check the syntax and supported subset.":
            "无法安全模拟第 {line} 行。请检查语法，并确认代码使用了受支持的语法。",
        "This Python operation is outside the supported simulation subset at line {line}.":
            "第 {line} 行的 Python 操作超出了模拟器的支持范围。",
        "The simulation reached the {limit}-step safety limit.":
            "模拟达到 {limit} 步的安全上限。",
        "The program exceeded the {limit}-iteration loop safety limit.":
            "程序超过了 {limit} 次循环迭代的安全上限。",
        "A loop exceeded the {limit}-iteration safety limit.":
            "循环超过了 {limit} 次迭代的安全上限。",
        "The call depth exceeded the safe limit of {limit}.":
            "函数调用深度超过安全上限 {limit}。",
        "The simulation could not safely continue. Check the code and input values.":
            "模拟无法安全继续。请检查代码和输入值。",
        "JSON input is too long (maximum {limit} characters).":
            "JSON 输入过长（最多 {limit} 个字符）。",
        "This JSON value is too large, too deeply nested, or not finite.":
            "此 JSON 值过大、嵌套过深，或不是有限数值。",
        "STEP {current} OF {total} · {function}":
            "第 {current}/{total} 步 · {function}",
        "{function} · {file}": "{function} · {file}",
        "Follow the current function state.": "查看当前函数状态。",
        "Finish ✓": "完成 ✓",
        "Next →": "下一步 →",
        "You are now {function}. The caller passed these arguments.":
            "现在你是 {function}。调用者传入了这些参数。",
        "Work out the value assigned to {target}.": "计算赋给 {target} 的值。",
        "Bind the expression result to {target}.": "将表达式结果存入 {target}。",
        "Does this condition evaluate to True or False?": "这个条件的结果是 True 还是 False？",
        "Which project function is being called here?": "这里调用的是哪个项目函数？",
        "The called function returned. Its value is back with you.":
            "被调用的函数已经返回，返回值已交还给你。",
        "What value does {function} return to its caller?": "{function} 会向调用者返回什么值？",
        "Follow the highlighted line, then continue.": "跟随高亮代码行，然后继续。",
        "Follow the highlighted line. Continue when you are ready.":
            "跟随高亮代码行，准备好后继续。",
        "Review the caller's values and local state, then continue.":
            "查看调用者传入的值和局部状态，然后继续。",
        "The nested call has returned. Continue with the result shown.":
            "嵌套调用已返回，请根据显示的结果继续。",
        "Calculate the result using the values shown.": "根据显示的值计算结果。",
        "Choose the branch that matches this condition.": "选择符合此条件的分支。",
        "Choose the function called at this line.": "选择此行调用的函数。",
        "Enter the value being returned. Use JSON for text or collections.":
            "输入函数将要返回的值。文本或集合请使用 JSON 格式。",
        "Enter your answer as a JSON value.": "请以 JSON 值的格式输入答案。",
        "This challenge is complete. You can review your answer history.":
            "本题已完成。你可以查看答题记录。",
        "Enter an answer before checking it.": "请先输入答案再进行检查。",
        "Use a JSON value: for example 4, true, or \"hello\".":
            "请使用 JSON 值，例如 4、true 或 \"hello\"。",
        "Correct": "正确",
        "Try again": "再试一次",
        "Attempt {number}: {answer} · {status}": "第 {number} 次：{answer} · {status}",
        "Answer revealed: {answer}": "已显示答案：{answer}",
        "Correct. {answer} is the value for this step.": "回答正确！此步骤的值是 {answer}。",
        "Not quite. Compare your answer with the highlighted expression and current values, then try again.":
            "还不正确。请对照高亮表达式和当前变量值，再试一次。",
        "Substitute the local values into the expression, then follow operator order.":
            "将局部变量代入表达式，并按运算符优先级计算。",
        "Substitute the local values and compare them to choose the matching branch.":
            "代入局部变量并进行比较，选择符合条件的分支。",
        "Look at the function name immediately before the parentheses.":
            "查看括号前面的函数名称。",
        "Evaluate the return expression using the local variables shown.":
            "使用显示的局部变量计算 return 表达式。",
        "Answer: {answer}. Review the highlighted line before continuing.":
            "答案：{answer}。继续前请回顾高亮代码行。",
        "Function: {function}\nChallenges: {total} · Solved by you: {solved} · "
        "Answers revealed: {revealed} · Attempts: {attempts}{practice}\nFinal return value: {value}":
            "函数：{function}\n挑战：{total} · 自行答对：{solved} · 查看答案：{revealed} · "
            "作答次数：{attempts}{practice}\n最终返回值：{value}",
        "No explicit return value.": "没有显式返回值。",
        "FUNCTION POV": "函数 POV",
        "Function POV currently supports Python only; this analysis uses {language}.":
            "函数 POV 目前只支持 Python；当前分析的语言是 {language}。",
        # -- compare -------------------------------------------------------
        "Before file…": "修改前的文件…",
        "After file…": "修改后的文件…",
        "Sample pair": "示例对",
        "Swap": "交换",
        "Compare": "开始对比",
        "Pick two versions of the same file to see the structural diff.":
            "选同一个文件的两个版本，看结构上的差异。",
        "Select a symbol": "选中一个符号",
        "Before": "修改前",
        "After": "修改后",
        "All symbols": "全部符号",
        "Added": "新增",
        "Removed": "删除",
        "Modified": "修改",
        "Moved": "改名移动",
        "Unchanged": "未变",
        "Choose both files first.": "先选好两个文件。",
        "Comparing…": "正在对比…",
        "No classes or functions found in either file.": "两个文件里都没找到类或函数。",
        "Choose the before file": "选择修改前的文件",
        "Choose the after file": "选择修改后的文件",
        "Source files": "源文件",
        "All files": "所有文件",
        "(no before file)": "（尚未选择修改前的文件）",
        "(no after file)": "（尚未选择修改后的文件）",
        "Could not compare: {error}": "无法对比：{error}",
        "Could not read {name}: {error}": "无法读取 {name}：{error}",
        "Sample: {old}  →  {new}": "示例：{old}  →  {new}",
        "{name}: pick a before file and an after file.":
            "{name}：选一个修改前和一个修改后的文件。",
        "No bundled sample for {name} yet — pick two files.":
            "暂时没有 {name} 的示例对 — 请自行选两个文件。",
        "Sample files are missing: {error}": "示例文件丢了：{error}",
        "structscope is not installed — see README, section “Compare two versions”":
            "没有安装 structscope — 见 README 的“Compare two versions”一节",
    },
}

_current = "en"


def language() -> str:
    """Current interface language code."""
    return _current


def set_language(code: str) -> None:
    """Switch the interface language; unknown codes fall back to English."""
    global _current
    _current = code if code in _TABLES else "en"


def language_name(code: str) -> str:
    for known, label in LANGUAGES:
        if known == code:
            return label
    return code


def tr(text: str, **fields) -> str:
    """Translate ``text``; formatted fields are applied after lookup."""
    translated = _TABLES.get(_current, {}).get(text, text)
    if fields:
        try:
            return translated.format(**fields)
        except (KeyError, IndexError, ValueError):
            return translated
    return translated


def simulation_error_text(message: str) -> str:
    """Translate common simulator errors without exposing raw English in Chinese UI."""
    if _current == "en":
        return message

    translated = _TABLES["zh"].get(message)
    if translated is not None:
        return translated

    match = re.fullmatch(
        r"The (?:source|program) is too long to simulate safely "
        r"\(limit: ([\d,]+) characters\)\.",
        message,
    )
    if match:
        return tr(
            "Python source exceeds the safe simulation limit of {limit} characters.",
            limit=match.group(1),
        )

    value_error_patterns = (
        (r"(.+) is nested too deeply\.", "The value for {name} is nested too deeply."),
        (r"(.+) is too long\.", "The value for {name} is too long."),
        (r"(.+) is too large\.", "The value for {name} is too large."),
        (r"(.+) must be a finite number\.", "The value for {name} must be a finite number."),
        (r"(.+) has too many items\.", "The value for {name} has too many items."),
        (
            r"(.+) must be a small object with string keys\.",
            "The value for {name} must be a small object with string keys.",
        ),
        (r"(.+) must be a JSON value\.", "The value for {name} must be a JSON value."),
    )
    for pattern, key in value_error_patterns:
        match = re.fullmatch(pattern, message)
        if match:
            return tr(key, name=match.group(1))

    limit_patterns = (
        (
            r"The simulation reached its safe limit of (\d+) steps\.",
            "The simulation reached the {limit}-step safety limit.",
        ),
        (
            r"The program exceeds the safe limit of (\d+) total loop iterations\.",
            "The program exceeded the {limit}-iteration loop safety limit.",
        ),
        (
            r"A loop exceeds the safe limit of (\d+) iterations\.",
            "A loop exceeded the {limit}-iteration safety limit.",
        ),
        (
            r"Call depth exceeded the safe limit of (\d+)\.",
            "The call depth exceeded the safe limit of {limit}.",
        ),
    )
    for pattern, key in limit_patterns:
        match = re.fullmatch(pattern, message)
        if match:
            return tr(key, limit=match.group(1))

    syntax_error = re.match(
        r"Cannot simulate (?:pasted )?Python(?: on line (\d+))?: ",
        message,
    )
    if syntax_error:
        line = syntax_error.group(1)
        if line:
            return tr(
                "Python code could not be simulated at line {line}. "
                "Check the syntax and supported subset.",
                line=line,
            )
        return tr(
            "Python code could not be simulated safely. "
            "Check the syntax and supported subset."
        )

    unsupported_line = re.search(r"\bat line (\d+)$", message)
    if unsupported_line:
        return tr(
            "This Python operation is outside the supported simulation subset "
            "at line {line}.",
            line=unsupported_line.group(1),
        )

    return tr(
        "The simulation could not safely continue. Check the code and input values."
    )


def untranslated(keys: Iterable[str]) -> List[str]:
    """Keys with no translation in any language but English (for tests)."""
    translated = set(_TABLES["zh"])
    return [key for key in keys if key not in translated]
