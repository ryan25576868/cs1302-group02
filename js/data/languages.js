/**
 * Prism language definitions and starter programs.
 *
 * The app is intentionally dependency-free. Each language below is handled by
 * the local structural parser and (when possible) the safe trace interpreter.
 */

export const LANGUAGES = [
  {
    id: 'javascript',
    name: 'JavaScript',
    short: 'JS',
    monogram: 'JS',
    extension: 'js',
    family: 'clike',
    entry: 'script',
    tagline: 'The language of the web',
    blurb: 'Scripts, functions, arrays, and the browser.',
    tint: '#F5D547',
    tintInk: '#36300A',
    wash: '#FBF5D7',
    hoverWash: '#F8EFBF',
    lineComment: '//',
    blockComment: ['/*', '*/'],
    keywords: [
      'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while',
      'do', 'break', 'continue', 'new', 'class', 'extends', 'import', 'export',
      'from', 'default', 'try', 'catch', 'finally', 'throw', 'switch', 'case',
      'typeof', 'instanceof', 'in', 'of', 'async', 'await', 'yield', 'this',
      'true', 'false', 'null', 'undefined', 'void', 'delete', 'static', 'super'
    ],
    literals: ['true', 'false', 'null', 'undefined'],
    sample: `function applyDiscount(price, isMember) {
  if (isMember) {
    return price * 0.9;
  }
  return price;
}

const prices = [12, 8, 25];
let total = 0;

for (const price of prices) {
  total += applyDiscount(price, true);
}

console.log("Total:", total);`,
    capabilities: ['functions', 'loops', 'conditionals', 'arrays'],
    interpreter: 'full'
  },
  {
    id: 'python',
    name: 'Python',
    short: 'PY',
    monogram: 'Py',
    extension: 'py',
    family: 'python',
    entry: 'script',
    tagline: 'Readable by design',
    blurb: 'Indentation, lists, and beginner-friendly syntax.',
    tint: '#DCEAF7',
    tintInk: '#275676',
    wash: '#EFF6FB',
    hoverWash: '#E4F0F9',
    lineComment: '#',
    blockComment: null,
    keywords: [
      'def', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'not', 'and',
      'or', 'is', 'None', 'True', 'False', 'class', 'import', 'from', 'as',
      'try', 'except', 'finally', 'raise', 'with', 'yield', 'lambda', 'pass',
      'break', 'continue', 'global', 'nonlocal', 'async', 'await', 'del',
      'assert', 'self'
    ],
    literals: ['True', 'False', 'None'],
    sample: `def apply_discount(price, is_member):
    if is_member:
        return price * 0.9
    return price


prices = [12, 8, 25]
total = 0

for price in prices:
    total += apply_discount(price, True)

print("Total:", total)`,
    capabilities: ['functions', 'loops', 'conditionals', 'lists'],
    interpreter: 'full'
  },
  {
    id: 'typescript',
    name: 'TypeScript',
    short: 'TS',
    monogram: 'TS',
    extension: 'ts',
    family: 'clike',
    entry: 'script',
    tagline: 'JavaScript with labels',
    blurb: 'JavaScript plus type annotations that document intent.',
    tint: '#DCEAFB',
    tintInk: '#24568C',
    wash: '#F0F6FD',
    hoverWash: '#E5F0FC',
    lineComment: '//',
    blockComment: ['/*', '*/'],
    keywords: [
      'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while',
      'do', 'break', 'continue', 'new', 'class', 'extends', 'import', 'export',
      'from', 'default', 'try', 'catch', 'finally', 'throw', 'switch', 'case',
      'typeof', 'instanceof', 'in', 'of', 'async', 'await', 'yield', 'this',
      'true', 'false', 'null', 'undefined', 'void', 'delete', 'static', 'super',
      'interface', 'type', 'enum', 'implements', 'private', 'public', 'protected',
      'readonly', 'number', 'string', 'boolean', 'any', 'unknown', 'never'
    ],
    literals: ['true', 'false', 'null', 'undefined'],
    sample: `function applyDiscount(price: number, isMember: boolean): number {
  if (isMember) {
    return price * 0.9;
  }
  return price;
}

const prices: number[] = [12, 8, 25];
let total: number = 0;

for (const price of prices) {
  total += applyDiscount(price, true);
}

console.log("Total:", total);`,
    capabilities: ['typed functions', 'loops', 'conditionals', 'arrays'],
    interpreter: 'full'
  },
  {
    id: 'java',
    name: 'Java',
    short: 'JAVA',
    monogram: 'Jv',
    extension: 'java',
    family: 'clike',
    entry: 'main',
    tagline: 'Structure at scale',
    blurb: 'Classes, methods, and strongly typed objects.',
    tint: '#F6DDD5',
    tintInk: '#913C25',
    wash: '#FCF1ED',
    hoverWash: '#FAE7E0',
    lineComment: '//',
    blockComment: ['/*', '*/'],
    keywords: [
      'class', 'interface', 'extends', 'implements', 'public', 'private',
      'protected', 'static', 'final', 'void', 'int', 'long', 'short', 'byte',
      'double', 'float', 'boolean', 'char', 'String', 'new', 'return', 'if',
      'else', 'for', 'while', 'do', 'break', 'continue', 'switch', 'case',
      'default', 'try', 'catch', 'finally', 'throw', 'throws', 'import',
      'package', 'this', 'super', 'true', 'false', 'null', 'abstract', 'synchronized'
    ],
    literals: ['true', 'false', 'null'],
    sample: `public class Main {
  static double applyDiscount(double price, boolean isMember) {
    if (isMember) {
      return price * 0.9;
    }
    return price;
  }

  public static void main(String[] args) {
    double[] prices = {12, 8, 25};
    double total = 0;

    for (int i = 0; i < prices.length; i++) {
      total += applyDiscount(prices[i], true);
    }

    System.out.println("Total: " + total);
  }
}`,
    capabilities: ['classes', 'methods', 'loops', 'arrays'],
    interpreter: 'full'
  },
  {
    id: 'cpp',
    name: 'C++',
    short: 'C++',
    monogram: 'C++',
    extension: 'cpp',
    family: 'clike',
    entry: 'main',
    tagline: 'Speed and control',
    blurb: 'A compiled language used for games, tools, and systems.',
    tint: '#E3DEFA',
    tintInk: '#4D4297',
    wash: '#F4F1FD',
    hoverWash: '#EDE8FC',
    lineComment: '//',
    blockComment: ['/*', '*/'],
    keywords: [
      'include', 'using', 'namespace', 'std', 'cout', 'cin', 'endl', 'int',
      'double', 'float', 'char', 'bool', 'void', 'string', 'auto', 'const',
      'return', 'if', 'else', 'for', 'while', 'do', 'break', 'continue',
      'class', 'struct', 'public', 'private', 'protected', 'new', 'delete',
      'true', 'false', 'nullptr', 'static', 'unsigned', 'long', 'short',
      'switch', 'case', 'default', 'try', 'catch', 'throw', 'vector'
    ],
    literals: ['true', 'false', 'nullptr'],
    sample: `#include <iostream>
using namespace std;

double applyDiscount(double price, bool isMember) {
  if (isMember) {
    return price * 0.9;
  }
  return price;
}

int main() {
  double prices[] = {12, 8, 25};
  double total = 0;

  for (int i = 0; i < 3; i++) {
    total += applyDiscount(prices[i], true);
  }

  cout << "Total: " << total << endl;
  return 0;
}`,
    capabilities: ['functions', 'loops', 'conditionals', 'fixed arrays'],
    interpreter: 'full'
  },
  {
    id: 'c',
    name: 'C',
    short: 'C',
    monogram: 'C',
    extension: 'c',
    family: 'clike',
    entry: 'main',
    tagline: 'The foundation',
    blurb: 'The small, influential language beneath modern computing.',
    tint: '#E8E5DE',
    tintInk: '#4D4940',
    wash: '#F7F5F1',
    hoverWash: '#EEEAE2',
    lineComment: '//',
    blockComment: ['/*', '*/'],
    keywords: [
      'include', 'define', 'int', 'double', 'float', 'char', 'void', 'long',
      'short', 'unsigned', 'signed', 'const', 'static', 'return', 'if', 'else',
      'for', 'while', 'do', 'break', 'continue', 'struct', 'typedef', 'sizeof',
      'switch', 'case', 'default', 'printf', 'scanf', 'malloc', 'free', 'NULL'
    ],
    literals: ['NULL', 'true', 'false'],
    sample: `#include <stdio.h>

double apply_discount(double price, int is_member) {
  if (is_member) {
    return price * 0.9;
  }
  return price;
}

int main() {
  double prices[3] = {12, 8, 25};
  double total = 0;
  int i;

  for (i = 0; i < 3; i++) {
    total += apply_discount(prices[i], 1);
  }

  printf("Total: %.2f\\n", total);
  return 0;
}`,
    capabilities: ['functions', 'loops', 'conditionals', 'fixed arrays'],
    interpreter: 'full'
  }
];

export const MODES = [
  {
    id: 'flow',
    name: 'Flowchart',
    short: 'Flow',
    kicker: 'Follow the path',
    description: 'Trace the route your program takes through every condition, loop, and return.',
    micro: 'Branches & loops',
    accent: '#C77B2B',
    accentSoft: '#FCF0E2',
    accentInk: '#7A4712'
  },
  {
    id: 'tree',
    name: 'Syntax Tree',
    short: 'Tree',
    kicker: 'See the skeleton',
    description: 'Unfold the program into a map of functions, statements, and expressions.',
    micro: 'Structure & nesting',
    accent: '#2F7D6E',
    accentSoft: '#E8F4F1',
    accentInk: '#19584D'
  },
  {
    id: 'trace',
    name: 'Live Trace',
    short: 'Trace',
    kicker: 'Watch it unfold',
    description: 'Step through a safe simulated run and watch each variable and output change.',
    micro: 'Animated execution',
    accent: '#5B5BD6',
    accentSoft: '#EEEEFD',
    accentInk: '#3737A3'
  },
  {
    id: 'data',
    name: 'Data Flow',
    short: 'Data',
    kicker: 'Follow the values',
    description: 'See values being created, carried, and transformed across the timeline.',
    micro: 'Values & dependencies',
    accent: '#C5536A',
    accentSoft: '#FAECEF',
    accentInk: '#873044'
  }
];

export const LANGUAGE_BY_ID = Object.fromEntries(LANGUAGES.map((language) => [language.id, language]));
export const MODE_BY_ID = Object.fromEntries(MODES.map((mode) => [mode.id, mode]));

export const DEFAULT_MODE = 'flow';

export const SITE_COPY = {
  eyebrow: 'Code, made visible',
  title: 'See your code',
  titleAccent: 'from every angle.',
  subtitle:
    'Turn a snippet into a picture you can follow, then read a beginner-friendly guide that explains what every line is doing — and why.',
  localNote: 'Your code is analyzed locally. Nothing is uploaded unless you ask AI to enhance the guide.',
  cta: 'Visualize & explain',
  privacy: 'Local-first · No account needed',
  guide: 'Beginner’s guide'
};
