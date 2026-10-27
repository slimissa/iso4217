//! The wrapper numeric contract (ADR 0013, docs/decisions/wrapper-numeric-contract.md): every vector in the
//! `numeric_contract` group of tests/cross_language_consistency.json must hold in this wrapper. The same file is read by
//! the Python, JavaScript and Go suites.

use iso4217::{CurrencyRegistry, MinorError};
use serde_json::Value;
use std::panic::{catch_unwind, AssertUnwindSafe};

fn decode_x(v: &Value) -> f64 {
    match v {
        Value::String(s) => match s.as_str() {
            "NaN" => f64::NAN,
            "Infinity" => f64::INFINITY,
            "-Infinity" => f64::NEG_INFINITY,
            other => panic!("unknown amount token {other}"),
        },
        n => n.as_f64().expect("amount is a number"),
    }
}

/// The minor-unit magnitude a formatted amount shows: symbol, sign, commas and the point removed.
fn digits(s: &str) -> String {
    s.chars().filter(|c| c.is_ascii_digit()).collect::<String>().trim_start_matches('0').to_string()
}

#[test]
fn numeric_contract() {
    // Silence the expected panics of the panicking variants, then restore the harness hook so a real failure is printed.
    let harness_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(|_| {}));
    let raw = std::fs::read_to_string("../../tests/cross_language_consistency.json").expect("read fixture");
    let fixture: Value = serde_json::from_str(&raw).expect("parse fixture");
    let nc = &fixture["numeric_contract"];
    let reg = CurrencyRegistry::load().expect("load registry");
    let mut count = 0usize;
    let mut failures: Vec<String> = Vec::new();

    for g in nc["groups"].as_array().expect("groups") {
        let gid = g["id"].as_str().unwrap();
        for v in g["vectors"].as_array().expect("vectors") {
            let code = v["currency"].as_str().unwrap();
            let c = reg.currency(code).or_else(|| reg.non_iso(code)).unwrap_or_else(|| panic!("{code} not found"));
            let x = decode_x(&v["x"]);
            let label = format!("{gid}: {code} {}", v["x"]);
            let mut want_minor: Option<i64> = None;
            if !v["to_minor"].is_null() {
                let exp = &v["to_minor"];
                let checked = c.try_to_minor(x);
                if let Some(kind) = exp.get("error").and_then(|e| e.as_str()) {
                    let want = if kind == "non_finite" { MinorError::NonFinite } else { MinorError::Overflow };
                    if checked != Err(want) {
                        failures.push(format!("{label}: try_to_minor = {checked:?}, want Err({want:?})"));
                    }
                    if kind == "overflow" {
                        let msg = MinorError::Overflow.to_string();
                        if !msg.contains("amount too large") {
                            failures.push(format!("{label}: overflow message must say \"amount too large\", got {msg:?}"));
                        }
                    }
                    if catch_unwind(AssertUnwindSafe(|| c.to_minor(x))).is_ok() {
                        failures.push(format!("{label}: to_minor must panic on {kind}"));
                    }
                } else {
                    let want = exp.as_i64().expect("expected integer");
                    want_minor = Some(want);
                    if checked != Ok(want) {
                        failures.push(format!("{label}: try_to_minor = {checked:?}, want Ok({want})"));
                    }
                    match catch_unwind(AssertUnwindSafe(|| c.to_minor(x))) {
                        Ok(got) if got == want => {}
                        other => failures.push(format!("{label}: to_minor = {other:?}, want {want}")),
                    }
                }
            }
            if let Some(want) = v["format"].as_str() {
                let got = c.format(x);
                if got != want {
                    failures.push(format!("{label}: format = {got:?}, want {want:?}"));
                }
                if let Some(m) = want_minor {
                    if digits(&got) != m.unsigned_abs().to_string().trim_start_matches('0') {
                        failures.push(format!("{label}: format {got:?} disagrees with to_minor {m}"));
                    }
                }
            }
            count += 1;
        }
    }
    std::panic::set_hook(harness_hook);
    assert!(failures.is_empty(), "{} contract failure(s):\n{}", failures.len(), failures.join("\n"));
    assert_eq!(count as u64, nc["vector_count"].as_u64().unwrap(), "vector count");
    println!("NUMERIC_CONTRACT rust vectors={count}");
}
