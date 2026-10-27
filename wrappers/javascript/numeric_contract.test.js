#!/usr/bin/env node
/**
 * The wrapper numeric contract (ADR 0013, docs/decisions/wrapper-numeric-contract.md): every vector in the
 * `numeric_contract` group of tests/cross_language_consistency.json must hold in this wrapper. The same file is read by
 * the Python, Go and Rust suites. Zero dependencies; exits 0 on success, 1 on any failure.
 */

'use strict';

const path = require('path');
const fs = require('fs');
const { CurrencyRegistry } = require('./index.js');

const fixture = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', '..', 'tests', 'cross_language_consistency.json'), 'utf-8')
);
const nc = fixture.numeric_contract;
const registry = new CurrencyRegistry();
const TOKENS = { NaN: NaN, Infinity: Infinity, '-Infinity': -Infinity };

const failures = [];
let count = 0;

function lookup(code) {
  return registry.currency(code) || registry.nonIso(code);
}

function attempt(fn) {
  try {
    return { value: fn() };
  } catch (err) {
    return { error: err };
  }
}

function digits(s) {
  return s.replace(/[^0-9]/g, '').replace(/^0+/, '');
}

for (const group of nc.groups) {
  for (const v of group.vectors) {
    const c = lookup(v.currency);
    const x = typeof v.x === 'string' ? TOKENS[v.x] : v.x;
    const label = `${group.id}: ${v.currency} ${JSON.stringify(v.x)}`;
    let wantMinor = null;
    if ('to_minor' in v) {
      const r = attempt(() => c.toMinor(x));
      if (typeof v.to_minor === 'object') {
        const kind = v.to_minor.error;
        const isRange = r.error instanceof RangeError;
        if (!r.error) {
          failures.push(`${label}: toMinor = ${r.value}, want error ${kind}`);
        } else if (kind === 'overflow' && !(isRange && /amount too large/.test(r.error.message))) {
          failures.push(`${label}: overflow must throw RangeError("amount too large"), got ${r.error.name}: ${r.error.message}`);
        } else if (kind === 'non_finite' && (isRange || !(r.error instanceof Error))) {
          failures.push(`${label}: non-finite must throw a plain Error, got ${r.error.name}`);
        }
      } else {
        wantMinor = v.to_minor;
        if (r.error || r.value !== wantMinor || Object.is(r.value, -0)) {
          failures.push(`${label}: toMinor = ${r.error ? r.error.message : r.value}, want ${wantMinor}`);
        }
      }
    }
    if ('format' in v) {
      const r = attempt(() => c.format(x));
      if (r.error || r.value !== v.format) {
        failures.push(`${label}: format = ${r.error ? 'throws ' + r.error.message : JSON.stringify(r.value)}, want ${JSON.stringify(v.format)}`);
      } else if (wantMinor !== null && digits(r.value) !== BigInt(wantMinor).toString().replace(/^-/, '').replace(/^0+/, '')) {
        failures.push(`${label}: format ${r.value} disagrees with toMinor ${wantMinor}`);
      }
    }
    count += 1;
  }
}

if (count !== nc.vector_count) {
  failures.push(`checked ${count} vectors, the fixture declares ${nc.vector_count}`);
}
if (failures.length > 0) {
  console.log(`${failures.length} numeric-contract failure(s):`);
  for (const f of failures) console.log('  ' + f);
  process.exit(1);
}
console.log(`NUMERIC_CONTRACT javascript vectors=${count}`);
