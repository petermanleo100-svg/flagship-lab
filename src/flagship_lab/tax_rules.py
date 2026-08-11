from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_RULE_PACK = {
    "pack_id": "cn-tax-demo",
    "version": "2026.08.2",
    "rules": [
        {"code": "TAX_ID_REQUIRED", "operator": "required_all", "fields": ["seller_tax_id", "buyer_tax_id"], "severity": "HIGH", "message": "交易对手税号缺失"},
        {"code": "VAT_RECALC", "operator": "computed_equal", "actual": "tax_amount", "factors": ["amount", "tax_rate"], "tolerance": 0.01, "severity": "HIGH", "message": "税额与金额×税率不一致"},
        {"code": "DUPLICATE_INVOICE", "operator": "in_set", "field": "invoice_id", "context": "duplicate_invoice_ids", "severity": "MEDIUM", "message": "发票号码重复"},
        {"code": "EXTREME_AMOUNT", "operator": "gte", "field": "amount", "value": 5_000_000, "severity": "MEDIUM", "message": "金额超过演示阈值500万元"},
    ],
}


ALLOWED_OPERATORS = {"required_all", "computed_equal", "in_set", "gte"}
ALLOWED_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def validate_rule_pack(pack: dict[str, Any]) -> None:
    if not pack.get("pack_id") or not pack.get("version") or not isinstance(pack.get("rules"), list):
        raise ValueError("rule pack requires pack_id, version and rules")
    codes: set[str] = set()
    for rule in pack["rules"]:
        code = rule.get("code")
        if not code or code in codes:
            raise ValueError("rule codes must be non-empty and unique")
        codes.add(code)
        if rule.get("operator") not in ALLOWED_OPERATORS:
            raise ValueError(f"unsupported operator for {code}")
        if rule.get("severity") not in ALLOWED_SEVERITIES:
            raise ValueError(f"unsupported severity for {code}")
        if not rule.get("message"):
            raise ValueError(f"missing message for {code}")


def evaluate_rule(rule: dict[str, Any], row: Any, context: dict[str, Any]) -> tuple[bool, dict]:
    operator = rule["operator"]
    if operator == "required_all":
        missing = [field for field in rule["fields"] if row[field] in (None, "")]
        return bool(missing), {"missing_fields": missing}
    if operator == "computed_equal":
        expected = 1.0
        for field in rule["factors"]:
            expected *= float(row[field])
        expected = round(expected, 2)
        actual = float(row[rule["actual"]])
        return abs(expected - actual) > float(rule.get("tolerance", 0)), {"expected": expected, "actual": actual}
    if operator == "in_set":
        value = row[rule["field"]]
        return value in context[rule["context"]], {"value": value}
    if operator == "gte":
        actual = float(row[rule["field"]])
        return actual >= float(rule["value"]), {"actual": actual, "threshold": rule["value"]}
    raise ValueError(f"unsupported operator: {operator}")

