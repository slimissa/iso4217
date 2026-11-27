#!/usr/bin/env node
/**
 * Collection order (v1.9.6, ADR 0015): every list in the `collection_order` group of tests/cross_language_consistency.json
 * must be returned by this wrapper in exactly that order. The same group is read by the Python, Go and Rust suites, so the
 * four outputs are identical. Zero dependencies; exits 0 on success, 1 on any failure.
 */

'use strict';

const path = require('path');
const fs = require('fs');
const os = require('os');
const { CurrencyRegistry } = require('./index.js');

const fixture = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'tests', 'cross_language_consistency.json'), 'utf-8')
);
const co = fixture.collection_order;
if (!co || !co.shipped || !co.synthetic) {
  console.error('FAIL: tests/cross_language_consistency.json has no collection_order group with shipped and synthetic cases');
  process.exit(1);
}

const METHODS = {
  all_active: 'allActive',
  all_withdrawn: 'allWithdrawn',
  all_non_iso: 'allNonIso',
  all_currencies: 'allCurrencies',
};
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'iso4217-order-'));
process.on('exit', () => fs.rmSync(dir, { recursive: true, force: true }));
const failures = [];
let vectors = 0;
let n = 0;

function build(registry) {
  if (registry === 'shipped') return new CurrencyRegistry(path.join(__dirname, 'iso4217.json'));
  const file = path.join(dir, `registry-${n++}.json`);
  fs.writeFileSync(file, JSON.stringify(registry));
  return new CurrencyRegistry(file);
}

function compare(label, got, want) {
  vectors += 1;
  const g = got.map(c => c.code);
  if (JSON.stringify(g) !== JSON.stringify(want)) {
    failures.push(`${label}: got ${JSON.stringify(g)}, expected ${JSON.stringify(want)}`);
  }
}

for (const c of [Object.assign({ id: 'shipped' }, co.shipped)].concat(co.synthetic)) {
  const registry = build(c.registry);
  for (const [method, codes] of Object.entries(c.collections)) {
    if (!METHODS[method]) {
      failures.push(`${c.id}: unknown collection ${method}`);
      continue;
    }
    compare(`${c.id}: ${method}`, registry[METHODS[method]](), codes);
  }
  for (const [anchor, codes] of Object.entries(c.pegged_to)) {
    compare(`${c.id}: pegged_to(${anchor})`, registry.peggedTo(anchor), codes);
  }
}

if (vectors !== co.vector_count) {
  failures.push(`the fixture declares vector_count=${co.vector_count} but this suite ran ${vectors}`);
}

if (failures.length) {
  for (const f of failures) console.error(`FAIL: ${f}`);
  process.exit(1);
}
console.log(`COLLECTION_ORDER javascript vectors=${vectors}`);
