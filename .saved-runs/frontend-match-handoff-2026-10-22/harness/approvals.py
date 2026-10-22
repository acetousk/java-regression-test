"""JSON-defined transaction approvals over PostgreSQL-origin events, never application SQL."""
from decimal import Decimal
import json

from incremental import events


class ApprovalEngine:
    """The JSON supplies policy; this module supplies only matching primitives.

    Every event in a transaction must match an exemption for its engine. There is
    no implicit exemption for an empty transaction or an unknown event/rule.
    """
    def __init__(self, rules, approved_difference=None):
        self.rules = rules
        self.approved_difference = approved_difference
        self.exemptions = rules.get("transaction_exemptions", [])
        if not isinstance(self.exemptions, list):
            raise ValueError("transaction_exemptions must be a list")
        for rule in self.exemptions:
            if set(rule) != {"engine", "when"} or not isinstance(rule["engine"], str):
                raise ValueError("Invalid transaction exemption")
            self._validate(rule["when"])

    def _validate(self, condition):
        if not isinstance(condition, dict):
            raise ValueError("Approval condition must be an object")
        for operator in ("all", "any"):
            if set(condition) == {operator}:
                if not isinstance(condition[operator], list) or not condition[operator]:
                    raise ValueError("Approval condition requires nonempty operands")
                for child in condition[operator]:
                    self._validate(child)
                return
        if set(condition) == {"approved_difference"}:
            if not isinstance(condition["approved_difference"], str):
                raise ValueError("approved_difference requires a name")
            return
        if set(condition) == {"keyed_rows"}:
            if not isinstance(self._value(condition["keyed_rows"]), list):
                raise ValueError("keyed_rows requires a list")
            return
        if ("path" not in condition or not isinstance(condition["path"], str)
                or len(condition) != 2):
            raise ValueError("Invalid approval condition")
        operator = next(key for key in condition if key != "path")
        if operator not in ("equals", "in", "all_in", "empty"):
            raise ValueError(f"Unknown approval operator: {operator}")
        value = self._value(condition[operator])
        if operator in ("in", "all_in") and not isinstance(value, list):
            raise ValueError(f"{operator} requires a list")
        if operator == "empty" and type(value) is not bool:
            raise ValueError("empty requires a boolean")

    def _value(self, value):
        if isinstance(value, dict):
            if set(value) != {"ref"} or value["ref"] not in self.rules:
                raise ValueError("Unknown approval reference")
            return self.rules[value["ref"]]
        return value

    def _matches(self, event, condition):
        if "all" in condition:
            return all(self._matches(event, child) for child in condition["all"])
        if "any" in condition:
            return any(self._matches(event, child) for child in condition["any"])
        if "approved_difference" in condition:
            return self.approved_difference is not None and self.approved_difference(
                event, condition["approved_difference"])
        if "keyed_rows" in condition:
            row = event.get("new")
            if not isinstance(row, dict):
                return False
            return any(event.get("table") == rule["table"] and any(
                len(values) == len(rule["key"]) and all(
                    field in row and row[field] == value for field, value in zip(rule["key"], values))
                for values in rule["values"])
                for rule in self._value(condition["keyed_rows"]))
        found = event
        for part in condition["path"].split("."):
            if not isinstance(found, dict) or part not in found:
                return False
            found = found[part]
        operator = next(key for key in condition if key != "path")
        expected = self._value(condition[operator])
        if operator == "equals":
            return type(found) is type(expected) and found == expected
        if operator == "in":
            return found in expected
        if operator == "all_in":
            # Nonempty: missing object identities must never approve DDL.
            return isinstance(found, list) and bool(found) and all(item in expected for item in found)
        if operator == "empty":
            return (found is None or found == []) if expected else (isinstance(found, list) and bool(found))
        raise ValueError("Unknown approval operator")

    def exempt_transaction(self, engine, transaction):
        conditions = [rule["when"] for rule in self.exemptions if rule["engine"] == engine]
        if not conditions:
            return False
        captured = events(transaction)  # Validates coverage against raw PostgreSQL row changes.
        if not captured:
            return False
        for event in captured:
            event = dict(event)
            for field in ("old", "new"):
                if isinstance(event.get(field), str):
                    event[field] = json.loads(event[field], parse_int=Decimal, parse_float=Decimal)
            if not any(self._matches(event, condition) for condition in conditions):
                return False
        return True
