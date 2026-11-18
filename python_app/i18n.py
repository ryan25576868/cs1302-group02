"""Interface strings for Prism.

English is the source language: the string passed to :func:`tr` is both the key
and the fallback, so a missing translation degrades to readable English rather
than to ``compare.title``-style keys. Adding a language means adding one dict.

The analysis text Prism generates (guides, trace notes) stays in English; this
module only covers the interface around it.
"""

from __future__ import annotations

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


def untranslated(keys: Iterable[str]) -> List[str]:
    """Keys with no translation in any language but English (for tests)."""
    translated = set(_TABLES["zh"])
    return [key for key in keys if key not in translated]
