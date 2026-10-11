'use strict';

// Temporary mitigation for GHSA-vfj7-8cjw-p6xm until an upstream fixed release.
// Keep the original package version so SBOMs and dependency alerts stay truthful.
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { readFileSync, writeFileSync } = require('node:fs');
const path = require('node:path');

const root = process.argv[2];
assert.ok(root, 'a braces package directory is required');
assert.equal(JSON.parse(readFileSync(path.join(root, 'package.json'))).version, '3.0.3');
const guard = "    if (node.nodes && depth > 128) {\n      throw new SyntaxError('Pattern nesting exceeds maximum depth (128)');\n    }\n";
const files = [
  ['parse.js', 'e572166565f15fa6ad9865ae49d678218e32aabfd1b3720f6d0d43d39800d310', [
    ['  const push = node => {\n', "  const push = node => {\n    if (node.nodes && stack.length > 128) {\n      throw new SyntaxError('Pattern nesting exceeds maximum depth (128)');\n    }\n"]
  ]],
  ['compile.js', 'dc98f22eee3d511785d92a00758d5f0d48efed5f5813bdecc2de430c529b5c9f', [
    ['  const walk = (node, parent = {}) => {\n', '  const walk = (node, parent = {}, depth = 0) => {\n' + guard],
    ['output += walk(child, node);', 'output += walk(child, node, depth + 1);']
  ]],
  ['expand.js', '41ccc196ebfa7b7781a634e721eb744e4e7bcb54cba427a7e3d6806a1b9e58f7', [
    ['  const walk = (node, parent = {}) => {\n', '  const walk = (node, parent = {}, depth = 0) => {\n' + guard],
    ['walk(child, node);', 'walk(child, node, depth + 1);']
  ]],
  ['stringify.js', '379f22d77bfa1478341ccd49c5e4267464aabcbba03558bab332aac23fc6f23a', [
    ['  const stringify = (node, parent = {}) => {\n', '  const stringify = (node, parent = {}, depth = 0) => {\n' + guard],
    ['output += stringify(child);', 'output += stringify(child, {}, depth + 1);']
  ]]
];

const replacements = files.map(([file, checksum, edits]) => {
  const filename = path.join(root, 'lib', file);
  let source = readFileSync(filename, 'utf8');
  assert.equal(createHash('sha256').update(source).digest('hex'), checksum,
    `Review the braces security patch against changed upstream source: ${file}`);
  for (const [before, after] of edits) {
    assert.equal(source.split(before).length - 1, 1, `ambiguous braces patch: ${file}`);
    source = source.replace(before, after);
  }
  return [filename, source];
});
for (const [filename, source] of replacements) {
  writeFileSync(filename, source);
}
console.log('Applied GHSA-vfj7-8cjw-p6xm depth guards to braces 3.0.3');
