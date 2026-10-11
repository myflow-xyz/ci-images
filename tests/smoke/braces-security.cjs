'use strict';

const assert = require('node:assert/strict');
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const bundle = process.argv[2];
assert.ok(bundle, 'a Markdown tool bundle is required');
const braces = require(require.resolve('braces', { paths: [bundle] }));
const nested = (open, close, depth) => open.repeat(depth) + 'x' + close.repeat(depth);
const depthError = error => error instanceof SyntaxError && /maximum depth/.test(error.message);

for (const method of ['parse', 'compile', 'expand', 'stringify']) {
  for (const [open, close] of [['{', '}'], ['(', ')']]) {
    assert.doesNotThrow(() => braces[method](nested(open, close, 128)), `${method}: accepted depth`);
    for (const depth of [129, 4500]) {
      assert.throws(() => braces[method](nested(open, close, depth)), depthError,
        `${method}: reject excessive ${open} depth without stack exhaustion`);
    }
  }
}
assert.throws(() => braces('{('.repeat(100) + 'x' + ')}'.repeat(100)), depthError);
assert.throws(() => braces.expand('{'.repeat(4500) + 'x'), depthError);
assert.throws(() => braces.compile(nested('{', '}', 129), { maxLength: 100000 }), depthError);

// Public AST entry points must also reject a tree not produced by the guarded parser.
for (const method of ['compile', 'expand', 'stringify']) {
  const ast = { type: 'root', nodes: [] };
  let parent = ast;
  for (let i = 0; i < 4500; i++) {
    const node = { type: 'brace', open: true, close: true, nodes: [], parent };
    parent.nodes.push(node);
    parent = node;
  }
  parent.nodes.push({ type: 'text', value: 'x', parent });
  assert.throws(() => braces[method](ast), depthError, `${method}: raw AST depth`);
}

assert.deepEqual(braces.expand('docs/{guide,api}/{1..3}.md'), [
  'docs/guide/1.md', 'docs/guide/2.md', 'docs/guide/3.md',
  'docs/api/1.md', 'docs/api/2.md', 'docs/api/3.md'
]);
assert.equal(braces.compile('docs/{guide,api}.md'), 'docs/(guide|api).md');
assert.equal(braces.stringify(braces.parse('a/{b,c}/d')), 'a/{b,c}/d');
assert.deepEqual(braces.expand('\\{literal\\}'), ['{literal}']);
assert.deepEqual(braces.expand('x'.repeat(2000)), ['x'.repeat(2000)]);

const directory = mkdtempSync(path.join(tmpdir(), 'braces-security-'));
const cli = path.join(bundle, 'node_modules/.bin/markdownlint-cli2');
function lint(args) {
  const result = spawnSync(process.execPath, [cli, ...args], {
    cwd: directory, encoding: 'utf8', timeout: 10000
  });
  assert.ifError(result.error);
  assert.equal(result.signal, null);
  return result;
}
try {
  mkdirSync(path.join(directory, 'docs'));
  writeFileSync(path.join(directory, 'docs/good.md'), '# Valid document\n');
  writeFileSync(path.join(directory, 'docs/bad.md'), '## Skipped invalid heading\n');
  let result = lint(['docs/{good,bad}.md', '!docs/bad.md']);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /Linting: 1 file\b/);
  result = lint(['docs/bad.md']);
  assert.equal(result.status, 1);
  assert.match(result.stdout + result.stderr, /MD041/);
  result = lint([nested('{', '}', 4500) + '.md']);
  assert.equal(result.status, 2);
  assert.match(result.stdout + result.stderr, /maximum depth/);
  assert.doesNotMatch(result.stdout + result.stderr, /Maximum call stack size exceeded/);
  writeFileSync(path.join(directory, '.markdownlint-cli2.jsonc'), JSON.stringify({
    globs: [nested('{', '}', 4500) + '.md']
  }));
  result = lint([]);
  assert.equal(result.status, 2);
  assert.match(result.stdout + result.stderr, /maximum depth/);
  assert.doesNotMatch(result.stdout + result.stderr, /Maximum call stack size exceeded/);
} finally {
  rmSync(directory, { recursive: true, force: true });
}

console.log('braces depth, public API, and Markdown CLI security regressions passed');
