#!/usr/bin/env node
/**
 * Zero-dependency test suite for the JavaScript ISO 4217 wrapper.
 *
 * Two parts:
 *   1. Direct API checks (issue #3) — the concrete behaviors the wrapper
 *      is supposed to guarantee.
 *   2. Cross-language consistency vectors (issue #4) — ports
 *      tests/cross_language_consistency.json, the same file the Python
 *      wrapper's test_wrappers.py checks, so a divergence between wrappers
 *      shows up here instead of only in Python.
 *
 * No test framework — this is deliberately runnable with just `node test.js`.
 * Exits 0 on success, 1 if any assertion fails.
 */

'use strict';

const path = require('path');
const fs = require('fs');
const { CurrencyRegistry } = require('./index.js');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

// ---------------------------------------------------------------------------
// Minimal test runner
// ---------------------------------------------------------------------------

let passCount = 0;
let failCount = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passCount += 1;
  } catch (err) {
    failCount += 1;
    failures.push({ name, message: err.message });
    console.log(`\u274c Test failed: ${name} — ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Part 1: Direct API checks (issue #3)
// ---------------------------------------------------------------------------

let registry;

test('CurrencyRegistry loads successfully', () => {
  registry = new CurrencyRegistry();
  assert(registry !== null && registry !== undefined, 'registry should not be null/undefined');
  assert(registry.activeCount > 0, 'registry should have active currencies');
});

test('USD active lookup returns correct minor_units (2)', () => {
  const usd = registry.active('USD');
  assert(usd !== null, "active('USD') should not be null");
  assert(usd.minorUnits === 2, `expected minorUnits 2, got ${usd.minorUnits}`);
});

test('JPY active lookup returns correct minor_units (0)', () => {
  const jpy = registry.active('JPY');
  assert(jpy !== null, "active('JPY') should not be null");
  assert(jpy.minorUnits === 0, `expected minorUnits 0, got ${jpy.minorUnits}`);
});

test('KWD active lookup returns correct minor_units (3)', () => {
  const kwd = registry.active('KWD');
  assert(kwd !== null, "active('KWD') should not be null");
  assert(kwd.minorUnits === 3, `expected minorUnits 3, got ${kwd.minorUnits}`);
});

test('Case-insensitive lookup works (usd, Usd, USD all work)', () => {
  for (const variant of ['usd', 'Usd', 'USD', 'uSd']) {
    const result = registry.active(variant);
    assert(result !== null, `active('${variant}') should not be null`);
    assert(result.code === 'USD', `active('${variant}').code = '${result.code}', expected 'USD'`);
  }
});

test('toMinor(100.50) returns 10050 for USD', () => {
  const usd = registry.active('USD');
  const result = usd.toMinor(100.50);
  assert(result === 10050, `expected 10050, got ${result}`);
});

test('fromMinor(10050) returns 100.5 for USD', () => {
  const usd = registry.active('USD');
  const result = usd.fromMinor(10050);
  assert(result === 100.5, `expected 100.5, got ${result}`);
});

test('format(100.50) returns "$100.50" for USD', () => {
  const usd = registry.active('USD');
  const result = usd.format(100.50);
  assert(result === '$100.50', `expected '$100.50', got '${result}'`);
});

test('format(500) returns "¥500" for JPY', () => {
  const jpy = registry.active('JPY');
  const result = jpy.format(500);
  assert(result === '¥500', `expected '¥500', got '${result}'`);
});

test('peggedTo("USD") includes AED, SAR', () => {
  const results = registry.peggedTo('USD').map((c) => c.code);
  assert(results.includes('AED'), `peggedTo('USD') should include AED, got [${results}]`);
  assert(results.includes('SAR'), `peggedTo('USD') should include SAR, got [${results}]`);
});

test('independent() includes USD, excludes AED', () => {
  const results = registry.independent().map((c) => c.code);
  assert(results.includes('USD'), `independent() should include USD, got [${results.slice(0, 10)}...]`);
  assert(!results.includes('AED'), `independent() should NOT include AED, got [${results.slice(0, 10)}...]`);
});

test('contains("USD") returns true', () => {
  assert(registry.has('USD') === true, `expected true, got ${registry.has('USD')}`);
});

test('contains("XXX") returns false', () => {
  assert(registry.has('XXX') === false, `expected false, got ${registry.has('XXX')}`);
});

test('Non-ISO lookup: BTC exists, minor_units=8', () => {
  const btc = registry.nonIso('BTC');
  assert(btc !== null, "nonIso('BTC') should not be null");
  assert(btc.minorUnits === 8, `expected minorUnits 8, got ${btc.minorUnits}`);
});

test('Withdrawn lookup: DEM exists, replaced_by="EUR"', () => {
  const dem = registry.withdrawn('DEM');
  assert(dem !== null, "withdrawn('DEM') should not be null");
  assert(dem.replacedBy === 'EUR', `expected replacedBy 'EUR', got '${dem.replacedBy}'`);
});

test('summary() returns object with expected keys', () => {
  const summary = registry.summary();
  const expectedKeys = [
    'version', 'updated', 'activeCurrencies', 'withdrawnCurrencies',
    'nonIsoCurrencies', 'peggedCurrencies', 'independentCurrencies',
    'minorUnitsDistribution',
  ];
  for (const key of expectedKeys) {
    assert(key in summary, `summary() missing expected key '${key}'`);
  }
});

// ---------------------------------------------------------------------------
// Part 2: Cross-language consistency vectors (issue #4)
// ---------------------------------------------------------------------------

const VECTORS_PATH = path.join(__dirname, '..', '..', 'tests', 'cross_language_consistency.json');

function loadVectors() {
  const raw = fs.readFileSync(VECTORS_PATH, 'utf-8');
  return JSON.parse(raw);
}

const vectors = loadVectors();

// -- Conversion vectors -------------------------------------------------

test('cross-lang: conversion vectors (toMinor)', () => {
  for (const vector of vectors.test_vectors) {
    const currency = registry.currency(vector.code);
    assert(currency !== null, `${vector.code} not found in registry`);
    for (const conv of vector.conversions || []) {
      const result = currency.toMinor(conv.major);
      assert(
        result === conv.minor,
        `${vector.code}.toMinor(${conv.major}) = ${result}, expected ${conv.minor}`
      );
    }
  }
});

test('cross-lang: conversion vectors round-trip (fromMinor)', () => {
  for (const vector of vectors.test_vectors) {
    const currency = registry.currency(vector.code);
    assert(currency !== null, `${vector.code} not found in registry`);
    for (const conv of vector.conversions || []) {
      // "lossy" entries are rounding-boundary values not exactly
      // representable in integer minor units (e.g. USD 100.005 rounds to
      // 10001, whose true inverse is 100.01, not the original 100.005).
      if (conv.lossy) continue;
      const back = currency.fromMinor(conv.minor);
      assert(
        back === conv.major,
        `${vector.code} round-trip failed: ${conv.major} -> ${conv.minor} -> ${back}`
      );
    }
  }
});

test('cross-lang: conversion vectors handle zero', () => {
  for (const vector of vectors.test_vectors) {
    const currency = registry.currency(vector.code);
    assert(currency !== null, `${vector.code} not found`);
    assert(currency.toMinor(0.0) === 0, `${vector.code}.toMinor(0.0) should be 0`);
    assert(currency.fromMinor(0) === 0.0, `${vector.code}.fromMinor(0) should be 0.0`);
  }
});

// -- Formatting vectors ---------------------------------------------------

test('cross-lang: formatting vectors', () => {
  for (const vector of vectors.test_vectors) {
    const currency = registry.currency(vector.code);
    assert(currency !== null, `${vector.code} not found in registry`);
    for (const fmt of vector.formatting || []) {
      const result = currency.format(fmt.major);
      assert(
        result === fmt.formatted,
        `${vector.code}.format(${fmt.major}) = '${result}', expected '${fmt.formatted}'`
      );
    }
  }
});

// -- Property vectors -----------------------------------------------------

test('cross-lang: minor_units values', () => {
  for (const vector of vectors.test_vectors) {
    const currency = registry.currency(vector.code);
    assert(currency !== null, `${vector.code} not found`);
    assert(
      currency.minorUnits === vector.minor_units,
      `${vector.code}.minorUnits = ${currency.minorUnits}, expected ${vector.minor_units}`
    );
  }
});

test('cross-lang: peg properties (peg_type, pegged_to, is_independent, is_pegged)', () => {
  for (const vector of vectors.test_vectors) {
    const currency = registry.currency(vector.code);
    assert(currency !== null, `${vector.code} not found`);

    if ('is_independent' in vector) {
      assert(
        currency.isIndependent === vector.is_independent,
        `${vector.code}.isIndependent = ${currency.isIndependent}, expected ${vector.is_independent}`
      );
    }
    if ('is_pegged' in vector) {
      assert(
        currency.isPegged === vector.is_pegged,
        `${vector.code}.isPegged = ${currency.isPegged}, expected ${vector.is_pegged}`
      );
    }
    if ('pegged_to' in vector) {
      assert(
        currency.peggedTo === vector.pegged_to,
        `${vector.code}.peggedTo = ${JSON.stringify(currency.peggedTo)}, expected ${JSON.stringify(vector.pegged_to)}`
      );
    }
    if ('peg_type' in vector) {
      assert(
        currency.pegType === vector.peg_type,
        `${vector.code}.pegType = ${JSON.stringify(currency.pegType)}, expected ${JSON.stringify(vector.peg_type)}`
      );
    }
    if ('peg_rate' in vector) {
      assert(
        currency.pegRate === vector.peg_rate,
        `${vector.code}.pegRate = ${currency.pegRate}, expected ${vector.peg_rate}`
      );
    }
    if ('peg_band_pct' in vector) {
      assert(
        currency.pegBandPct === vector.peg_band_pct,
        `${vector.code}.pegBandPct = ${currency.pegBandPct}, expected ${vector.peg_band_pct}`
      );
    }
  }
});

test('cross-lang: withdrawn properties (replaced_by, conversion_rate)', () => {
  for (const vector of vectors.test_vectors) {
    if (!vector.withdrawn) continue;
    const currency = registry.currency(vector.code);
    assert(currency !== null, `${vector.code} not found`);

    if ('replaced_by' in vector) {
      assert(
        currency.replacedBy === vector.replaced_by,
        `${vector.code}.replacedBy = ${JSON.stringify(currency.replacedBy)}, expected ${JSON.stringify(vector.replaced_by)}`
      );
    }
    if ('conversion_rate' in vector) {
      assert(
        currency.conversionRate === vector.conversion_rate,
        `${vector.code}.conversionRate = ${currency.conversionRate}, expected ${vector.conversion_rate}`
      );
    }
  }
});

// -- Lookup vectors ---------------------------------------------------------

// The JSON's "method" field is a snake_case-agnostic name ("active",
// "withdrawn", "currency") that happens to be identical in JS since these
// are single words. No mapping needed here, but we look the method up by
// name (not hardcode it) so this stays a faithful port of the JSON, the
// same way the Python reference implementation uses getattr().
function lookupMethod(registry, methodName) {
  const method = registry[methodName];
  assert(typeof method === 'function', `Registry has no method '${methodName}'`);
  return method.bind(registry);
}

test('cross-lang: case-insensitive lookup vectors', () => {
  for (const t of vectors.lookup_tests || []) {
    const method = lookupMethod(registry, t.method);
    if (t.expected_null) {
      for (const code of t.lookups) {
        const result = method(code);
        assert(result === null, `${t.method}('${code}') should return null`);
      }
    } else {
      for (const code of t.lookups) {
        const result = method(code);
        assert(result !== null, `${t.method}('${code}') returned null`);
        assert(
          result.code === t.expected_code,
          `${t.method}('${code}').code = '${result.code}', expected '${t.expected_code}'`
        );
      }
    }
  }
});

// -- Filter vectors -----------------------------------------------------

// JSON filter method names are snake_case ("pegged_to", "with_minor_units");
// JS uses camelCase for everything except summary() keys (see below). This
// map is the JS-idiom translation layer the task description asks for.
const FILTER_METHOD_MAP = {
  pegged_to: 'peggedTo',
  with_minor_units: 'withMinorUnits',
  independent: 'independent',
};

test('cross-lang: filter method vectors', () => {
  for (const t of vectors.filter_tests || []) {
    const jsMethodName = FILTER_METHOD_MAP[t.method];
    assert(jsMethodName !== undefined, `No JS method mapping for filter '${t.method}'`);
    const method = registry[jsMethodName];
    assert(typeof method === 'function', `Registry has no method '${jsMethodName}'`);

    const results = 'argument' in t ? method.call(registry, t.argument) : method.call(registry);
    const resultCodes = new Set(results.map((c) => c.code));

    for (const expectedCode of t.expected_contains || []) {
      assert(
        resultCodes.has(expectedCode),
        `${jsMethodName}() should contain ${expectedCode}`
      );
    }
    for (const excludedCode of t.expected_not_contains || []) {
      assert(
        !resultCodes.has(excludedCode),
        `${jsMethodName}() should NOT contain ${excludedCode}`
      );
    }
  }
});

// -- Summary vectors ------------------------------------------------------

// KNOWN, DOCUMENTED DIVERGENCE: registry.summary() intentionally returns
// camelCase keys in JS (see index.d.ts, README.md) while Python/Rust return
// snake_case keys matching this JSON file's expected_keys verbatim. This is
// an existing, shipped part of the JS public API, not something this test
// suite silently changes. Rather than assert literal string equality against
// the JSON's snake_case keys (which would just fail on a known, intentional,
// already-documented naming convention difference and provide no signal),
// this maps each JSON key to its JS-idiomatic equivalent and checks that.
const SUMMARY_KEY_MAP = {
  version: 'version',
  updated: 'updated',
  active_currencies: 'activeCurrencies',
  withdrawn_currencies: 'withdrawnCurrencies',
  non_iso_currencies: 'nonIsoCurrencies',
  pegged_currencies: 'peggedCurrencies',
  independent_currencies: 'independentCurrencies',
  minor_units_distribution: 'minorUnitsDistribution',
};

test('cross-lang: summary has expected keys (JS-idiom mapped)', () => {
  for (const t of vectors.summary_tests || []) {
    const summary = registry.summary();
    for (const key of t.expected_keys) {
      const jsKey = SUMMARY_KEY_MAP[key];
      assert(jsKey !== undefined, `No JS key mapping for summary key '${key}'`);
      assert(jsKey in summary, `summary() missing expected key '${jsKey}' (maps to JSON key '${key}')`);
    }
  }
});

// -- Edge cases -------------------------------------------------------------

test('cross-lang: registry contains all test vector codes', () => {
  for (const vector of vectors.test_vectors) {
    assert(
      registry.currency(vector.code) !== null,
      `${vector.code} from test vectors not found in registry`
    );
  }
});

test('cross-lang: toMinor handles negative amounts', () => {
  const usd = registry.currency('USD');
  assert(usd.toMinor(-100.50) === -10050, `expected -10050, got ${usd.toMinor(-100.50)}`);
  assert(usd.toMinor(-0.01) === -1, `expected -1, got ${usd.toMinor(-0.01)}`);
});

test('cross-lang: fromMinor handles negative amounts', () => {
  const usd = registry.currency('USD');
  assert(usd.fromMinor(-10050) === -100.5, `expected -100.5, got ${usd.fromMinor(-10050)}`);
  assert(usd.fromMinor(-1) === -0.01, `expected -0.01, got ${usd.fromMinor(-1)}`);
});

// ---------------------------------------------------------------------------
// Report and exit
// ---------------------------------------------------------------------------

const total = passCount + failCount;

if (failCount === 0) {
  console.log(`\u2705 All ${total} tests passed`);
  process.exit(0);
} else {
  console.log(`\n${failCount} of ${total} tests failed:`);
  for (const f of failures) {
    console.log(`  - ${f.name}: ${f.message}`);
  }
  process.exit(1);
}
