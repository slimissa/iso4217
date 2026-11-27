#!/usr/bin/env node
/**
 * The wrapper lookup contract (ADR 0015, docs/decisions/wrapper-lookup-contract.md): every vector in the `lookup_contract`
 * group of tests/cross_language_consistency.json must hold in this wrapper. The same file is read by the Python, Go and Rust
 * suites. Zero dependencies; exits 0 on success, 1 on any failure.
 */

'use strict';

const path = require('path');
const fs = require('fs');
const os = require('os');
const { CurrencyRegistry } = require('./index.js');

const fixture = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'tests', 'cross_language_consistency.json'), 'utf-8')
);
const lc = fixture.lookup_contract;
if (!lc) {
  console.error('FAIL: tests/cross_language_consistency.json has no lookup_contract group');
  process.exit(1);
}

const METHODS = { currency: 'currency', active: 'active', withdrawn: 'withdrawn', non_iso: 'nonIso', contains: 'has' };
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'iso4217-lookup-'));
process.on('exit', () => fs.rmSync(dir, { recursive: true, force: true }));
const failures = [];
let vectors = 0;
let invalid = 0;
let n = 0;

function build(registry) {
  const file = path.join(dir, `registry-${n++}.json`);
  fs.writeFileSync(file, JSON.stringify(registry));
  return new CurrencyRegistry(file);
}

for (const group of [lc.precedence, lc.duplicates]) {
  for (const c of group) {
    const registry = build(c.registry);
    for (const lk of c.lookups) {
      vectors += 1;
      const found = registry[METHODS[lk.method]](lk.code);
      if (!found || found.name !== lk.expected_name) {
        failures.push(`${c.id}: ${lk.method}(${lk.code}) expected ${lk.expected_name}, got ${found && found.name}`);
      }
    }
    if (c.expected_active_count !== undefined) {
      vectors += 1;
      if (registry.allActive().length !== c.expected_active_count) {
        failures.push(`${c.id}: allActive() has ${registry.allActive().length}, expected ${c.expected_active_count}`);
      }
    }
  }
}

const registry = build(lc.precedence[0].registry);
const inv = lc.invalid_input;
// A method named in method_applies_to applies only to the wrappers listed there (v1.9.6).
const scope = inv.method_applies_to || {};
const applies = (method) => (scope[method] || inv.applies_to).includes('javascript');
const mine = inv.methods.filter(applies);
for (const method of mine) {
  if (typeof registry[METHODS[method]] !== 'function') {
    failures.push(`invalid_input names ${method}, which this suite does not map to a CurrencyRegistry method`);
    continue;
  }
  for (const value of inv.values.concat([undefined])) {
    const isExtra = value === undefined;
    if (!isExtra) invalid += 1;
    let error = null;
    try {
      registry[METHODS[method]](value);
    } catch (e) {
      error = e;
    }
    const label = `${method}(${isExtra ? 'undefined' : JSON.stringify(value)})`;
    if (!error) failures.push(`${label} did not throw`);
    else if (error.name !== inv.error || !(error instanceof TypeError)) failures.push(`${label} threw ${error.name}, expected ${inv.error}`);
    else if (!String(error.message).includes(inv.message_contains)) failures.push(`${label} message: ${error.message}`);
  }
}

for (const [label, ok] of [
  ['vector_count', vectors === lc.vector_count],
  ['invalid_input_count', lc.invalid_input_count === inv.methods.length * inv.values.length],
  ['invalid_input pairs that apply here', invalid === mine.length * inv.values.length],
]) {
  if (!ok) failures.push(`the fixture's declared ${label} does not match what this suite ran`);
}

if (failures.length) {
  for (const f of failures) console.error(`FAIL: ${f}`);
  process.exit(1);
}
console.log(`LOOKUP_CONTRACT javascript vectors=${vectors} invalid=${invalid}`);
