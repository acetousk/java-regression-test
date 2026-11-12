#!/usr/bin/env python3
"""Initialize and build both engines with their own runtimes.

Build both engines, boot against disposable PostgreSQL, and stop both processes.
Optional deterministic transaction barriers coordinate logical time and compare committed state.
"""

import argparse
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

from approvals import ApprovalEngine
from deterministic import DeterministicCoordinator
from incremental import DatabaseState, INSTALL_SQL, TRACKING_SCHEMA

ROOT = Path(__file__).resolve().parent
REPOSITORIES = ("moqui-framework", "mr-moqui")
POSTGRES_IMAGE = "postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336"


APPROVED_STARTUP_DIFFERENCES = json.loads((ROOT / "approved-differences.json").read_text())

RUST_ONLY_SOURCES = json.loads((ROOT / "rust-only-sources.json").read_text())


def _xml(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Rust only source unavailable: {path}; set source_root to the source checkout parent")
    return ET.parse(path).getroot(), hashlib.sha256(path.read_bytes()).hexdigest()


def source_records(manifest, source_root):
    """Resolve exact source records and their entity PKs, including nested data."""
    root = Path(source_root)
    entities, hashes, records, locators = {}, {}, [], {}
    for path in manifest["metadata"]:
        xml, hashes[path] = _xml(root, path)
        for entity in xml.findall("entity"):
            entities[entity.get("package") + "." + entity.get("entity-name")] = entity

    def collect(node, source, locator, inherited=None, entity_name=None):
        name = entity_name or node.tag
        if name not in entities:
            raise ValueError(f"Missing entity metadata for Rust only source: {name}")
        entity = entities[name]
        fields = {f.get("name"): f for f in entity.findall("field")}
        values = {**(inherited or {}), **node.attrib}
        if not values.keys() <= fields.keys():
            raise ValueError(f"Unknown source fields: {name}: {values.keys() - fields.keys()}")
        pk = {key: values[key] for key, field in fields.items() if field.get("is-pk") == "true"}
        if not pk:
            raise ValueError(f"Missing PK metadata: {name}")
        # Raw Rust snapshots use entity/field names unless explicitly overridden.
        columns = {key: field.get("column-name", key) for key, field in fields.items()}
        expected = {columns[key]: values.get(key) or None for key in fields}
        table = "public." + entity.get("table-name", entity.get("entity-name"))
        records.append({"source": source, "locator": locator, "entity": name,
                        "pk": pk, "table": table, "expected": expected,
                        "pk_columns": {columns[k]: v for k, v in pk.items()},
                        "source_values": values})
        for child in node:
            relation = next((r for r in entity.findall("relationship")
                             if r.get("short-alias") == child.tag), None)
            if relation is None:
                raise ValueError(f"Unknown nested source relationship: {name}.{child.tag}")
            collect(child, source, locators[id(child)], pk, relation.get("related"))

    for source in manifest["sources"]:
        xml, hashes[source["path"]] = _xml(root, source["path"])
        def locate(node, prefix):
            locators[id(node)] = prefix
            counts = Counter()
            for child in node:
                counts[child.tag] += 1
                locate(child, f"{prefix}/{child.tag}[{counts[child.tag]}]")

        locate(xml, f"/{xml.tag}")
        before = len(records)
        if source["mode"] == "data":
            nodes = list(xml)
        elif source["mode"] == "enum-seeds":
            nodes = [n for seed in xml.iter("seed-data") for n in seed
                     if n.tag in ("moqui.basic.Enumeration", "moqui.basic.EnumerationType")
                     and n.get("enumTypeId") in source["groups"]]
        else:
            raise ValueError(f"Unknown Rust only source mode: {source['mode']}")
        for node in nodes:
            collect(node, source["path"], locators[id(node)])
        if len(records) - before != source["expected_records"]:
            raise ValueError(f"Rust only source record count changed: {source['path']}")
    return records, hashes


def filter_snapshots(java, rust, manifest, source_root):
    """Return copies plus an exact audit. Only Rust rows can be excluded."""
    if manifest.get("version") != 1 or manifest.get("classification") != "Rust only":
        raise ValueError("Unsupported Rust only manifest")
    seeds, hashes = source_records(manifest, source_root)
    operational = {entry["table"]: entry for entry in manifest["operational"]}
    parsed = [[json.loads(record, parse_float=Decimal) for record in snapshot["records"]]
              for snapshot in (java, rust)]
    audit = {"classification": "Rust only", "manifest": manifest,
             "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
             "source_sha256": hashes, "excluded": [], "retained_candidates": []}

    def key(record, seed, java_side=False):
        row = record.get("row", {})
        if (record.get("table") == seed["table"]
                and all(row.get(k) == v for k, v in seed["pk_columns"].items())):
            return True
        # Narrow collision guard only: never rename/normalize compared records.
        guard = manifest["java_pk_guards"].get(seed["entity"]) if java_side else None
        return bool(guard and record.get("table") == guard["table"]
                    and all(row.get(guard["columns"][k]) == v for k, v in seed["pk"].items()))

    retained = []
    for index, (raw, record) in enumerate(zip(rust["records"], parsed[1])):
        table = record.get("table")
        attribution = None
        if table in operational and "row" in record:
            attribution = {"kind": "operational", **operational[table]}
        else:
            candidates = [s for s in seeds if key(record, s)]
            if candidates:
                seed = candidates[0]
                reason = None
                if len(candidates) != 1:
                    reason = "source PK collision"
                elif any(key(r, seed, java_side=True) for r in parsed[0]):
                    reason = "PK present in Java"
                elif sum(key(r, seed) for r in parsed[1]) != 1:
                    reason = "duplicate Rust PK"
                else:
                    row = dict(record["row"])
                    row.pop("lastUpdatedStamp", None)  # Loader-generated, not source data.
                    if row != seed["expected"]:
                        reason = "values differ from source (including unset fields)"
                attribution = {"kind": "source-file", **seed}
                if reason:
                    audit["retained_candidates"].append({"record_index": index, "record": raw,
                                                          "reason": reason, "sources": candidates})
                    attribution = None
        if attribution is None:
            retained.append(raw)
        else:
            audit["excluded"].append({"side": "rust", "record_index": index,
                                      "record": raw, **attribution})
    audit["excluded_counts"] = dict(Counter(item["kind"] for item in audit["excluded"]))
    return java, {**rust, "records": retained}, audit


def apply_approved_differences(java, rust, approved, *, schema_proof=None):
    snapshots = [
        {"schema": snapshot["schema"], "records": [
            json.loads(record, parse_int=Decimal, parse_float=Decimal)
            for record in snapshot["records"]]}
        for snapshot in (java, rust)
    ]
    # Phase2 Change17: seed filtering must not hide populated keys from schema proof.
    schema_original = deepcopy(snapshots) if schema_proof is None else [
        {"schema": snapshot["schema"], "records": [
            json.loads(record, parse_int=Decimal, parse_float=Decimal)
            for record in snapshot["records"]]} for snapshot in schema_proof]
    applied = apply_reviewed_event_sets(snapshots, schema_original, approved.get("reviewed_event_sets", []))
    applied.extend(apply_rust_only_tables(snapshots, approved.get("rust_only_tables", [])))
    # Change 6: apply only the user's enumerated asymmetries; raw evidence stays intact.
    applied.extend(apply_java_only_tables(snapshots, approved.get("java_only_tables", [])))
    applied.extend(apply_reviewed_seed_rows(snapshots, approved.get("reviewed_seed_rows", [])))
    applied.extend(apply_extension_views(snapshots, approved.get("extension_views", [])))
    applied.extend(apply_template_differences(snapshots, approved.get("template_differences", [])))
    applied.extend(apply_rust_only_columns(snapshots, approved.get("rust_only_columns", []), original=schema_original))
    applied.extend(apply_schema_additions(snapshots, schema_original, applied,
                                         approved.get("schema_additions", [])))
    applied.extend(apply_rust_only_ddl(snapshots, approved.get("rust_only_ddl", [])))
    # Approved rows one engine has and the other does not, per entity: Rust rows minus Java rows. Each such
    # row is one refresh and one create during an empty-database load, which the statistics rule below uses.
    seed_row_deltas = Counter()
    for rule in approved["theme_resources"]:
        matches = []
        for snapshot in snapshots:
            matches.append([item for item in snapshot["records"]
                            if item.get("table") == "public.screen_theme_resource"
                            and item["row"].get("screen_theme_id") == rule["theme"]
                            and item["row"].get("sequence_num") == rule["sequence"]])
        valid = True
        for side, items in zip(("java", "rust"), matches):
            expected = rule[side]
            if expected is None:
                valid = valid and not items
            else:
                seed = {"screen_theme_id": rule["theme"], "sequence_num": rule["sequence"],
                        "resource_type_enum_id": expected[0], "resource_value": expected[1]}
                valid = valid and len(items) == 1 and {
                    k: v for k, v in items[0]["row"].items() if k != "last_updated_stamp"
                } == seed
        if not valid:
            continue
        for snapshot, items in zip(snapshots, matches):
            if not items:
                continue
            if rule["java"] is None or rule["rust"] is None:
                # This exact resource is approved as absent on the other engine.
                snapshot["records"].remove(items[0])
                seed_row_deltas["moqui.screen.ScreenThemeResource"] += 1 if snapshot is snapshots[1] else -1
            else:
                # Normalize approved seed values, retaining each engine's actual timestamp.
                items[0]["row"]["resource_type_enum_id"] = rule["java"][0]
                items[0]["row"]["resource_value"] = rule["java"][1]
        applied.append({"kind": "theme_resource", **rule})

    for rule in approved.get("rust_seed_additions", []):
        # Each listed key must be exactly one Rust row and no Java row; only then is the Rust row set aside.
        found = []
        for values in rule["values"]:
            key = dict(zip(rule["key"], values))
            sides = [[item for item in snapshot["records"] if item.get("table") == rule["table"]
                      and all(item["row"].get(field) == value for field, value in key.items())]
                     for snapshot in snapshots]
            if sides[0] or len(sides[1]) != 1:
                found = None
                break
            found.append(sides[1][0])
        if not found:
            continue
        for item in found:
            snapshots[1]["records"].remove(item)
        seed_row_deltas[rule["entity"]] += len(found)
        applied.append({"kind": "rust_seed_addition", "table": rule["table"], "rows": len(found)})

    for rule in approved.get("java_seed_additions", []):
        # Each listed key must be exactly one Java row and no Rust row; only then is the Java row set aside.
        found = []
        for values in rule["values"]:
            key = dict(zip(rule["key"], values))
            sides = [[item for item in snapshot["records"] if item.get("table") == rule["table"]
                      and all(item["row"].get(field) == value for field, value in key.items())]
                     for snapshot in snapshots]
            if sides[1] or len(sides[0]) != 1:
                found = None
                break
            found.append(sides[0][0])
        if not found:
            continue
        for item in found:
            snapshots[0]["records"].remove(item)
        seed_row_deltas[rule["entity"]] -= len(found)
        applied.append({"kind": "java_seed_addition", "table": rule["table"], "rows": len(found)})

    applied.extend(apply_rust_only_statistics(snapshots, approved.get("rust_only_statistics")))
    applied.extend(apply_seed_statistics(snapshots, seed_row_deltas))

    for rule in approved.get("statistics_timing", []):
        normalized_rows = []
        for snapshot in snapshots:
            count = 0
            for item in snapshot["records"]:
                if item.get("table") != rule["table"]:
                    continue
                row = item["row"]
                try:
                    for field in rule["fields"]:
                        value = row[field]
                        if field.endswith("_date_time") or field == "last_updated_stamp":
                            datetime.fromisoformat(value)
                        elif field == "is_slow_hit":
                            if value not in ("Y", "N"):
                                raise ValueError("invalid slow-hit flag")
                        elif not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                            raise ValueError("invalid timing metric")
                    if "slow_hit_count" in row and not (
                            row["slow_hit_count"] == row["slow_hit_count"].to_integral_value()
                            and row["slow_hit_count"] <= row["hit_count"]):
                        raise ValueError("invalid slow-hit count")
                except (KeyError, TypeError, ValueError):
                    continue
                # Only approved timing/slow-hit metrics change in the comparison copy.
                # Ids, hit counts, operation names, duplicate rows, and schema remain strict.
                for field in rule["fields"]:
                    row[field] = None
                count += 1
            normalized_rows.append(count)
        if any(normalized_rows):
            applied.append({"kind": "statistics_timing", **deepcopy(rule),
                            "java_rows": normalized_rows[0], "rust_rows": normalized_rows[1]})

    if approved.get("statistics_bin_boundaries"):
        applied.extend(apply_statistics_bin_boundaries(snapshots, approved.get("statistics_timing", [])))

    for rule in approved["full_text_indexes"]:
        table, field = rule["table"], rule["field"]
        column = field + "_tsv"
        expression = f"to_tsvector('english'::regconfig, COALESCE({field}, ''::text))"
        declaration = f"    {column} tsvector GENERATED ALWAYS AS ({expression}) STORED"
        # Match exact pg_dump definitions, not arbitrary columns ending in _tsv.
        table_pattern = re.compile(r"(CREATE TABLE " + re.escape(table) + r" \(\n)(.*?)(\n\);)", re.S)
        match = table_pattern.search(snapshots[0]["schema"])
        if not match or match.group(2).split(",\n").count(declaration) != 1:
            continue
        index_blocks = []
        for side, snapshot in zip(("java", "rust"), snapshots):
            name = rule[side + "_index"]
            target = column if side == "java" else f"to_tsvector('english'::regconfig, {field})"
            expected = (f"--\n-- Name: {name}; Type: INDEX; Schema: public; Owner: moqui\n--\n\n"
                        f"CREATE INDEX {name} ON {table} USING gin ({target});")
            blocks = re.split(r"(?=--\n-- Name: )", snapshot["schema"])
            found = [block for block in blocks if block.strip() == expected]
            index_blocks.append(found[0] if len(found) == 1 else None)
        expected_metadata = {"name": column, "type": "tsvector", "not_null": False, "default": expression}
        metadata = [item for item in snapshots[0]["records"] if item.get("relation") == table]
        if (not all(index_blocks) or len(metadata) != 1 or
                [c for c in metadata[0]["columns"] if c["name"] == column] != [expected_metadata]):
            continue
        # Phase2 Change17: project only the exact catalog counterpart of this existing storage rule.
        catalog_matches = []
        relation_metadata = [[r for r in snapshot["records"] if r.get("relation") == table]
                             for snapshot in snapshots]
        has_catalog = any("schema_objects" in r for side in relation_metadata for r in side)
        if has_catalog:
            for side, relations in zip(("java", "rust"), relation_metadata):
                target = column if side == "java" else f"to_tsvector('english'::regconfig, {field})"
                name = rule[side + "_index"]
                expected_object = {
                    "kind": "index", "name": name, "method": "gin",
                    "definition": f"CREATE INDEX {name} ON {table} USING gin ({target})",
                    "columns": [column] if side == "java" else [None],
                    "key_metadata": [{"opclass": "pg_catalog.tsvector_ops", "collation": None, "option": 0}],
                    "key_count": 1, "attribute_count": 1, "unique": False, "primary": False,
                    "exclusion": False, "valid": True, "ready": True, "live": True,
                    "expressions": None if side == "java" else target, "predicate": None,
                    "constraint_backed": False, "plain": side == "java", "options": None,
                    "owner": "moqui", "partition": False, "table_inherits": False}
                objects = relations[0].get("schema_objects", []) if len(relations) == 1 else []
                found = [o for o in objects if o.get("name") == name]
                catalog_matches.append((objects, found[0]) if found == [expected_object] else None)
            if not all(catalog_matches):
                continue
        # Both approved index definitions and the generated column must exist before accepting either.
        snapshots[0]["schema"] = table_pattern.sub(
            lambda m: m.group(1) + ",\n".join(c for c in m.group(2).split(",\n") if c != declaration)
            + m.group(3), snapshots[0]["schema"], count=1)
        for snapshot, block in zip(snapshots, index_blocks):
            snapshot["schema"] = snapshot["schema"].replace(block, "", 1)
        for objects, obj in catalog_matches:
            objects.remove(obj)
        metadata[0]["columns"].remove(expected_metadata)
        for item in snapshots[0]["records"]:
            if item.get("table") == table:
                item["row"].pop(column, None)
        applied.append({"kind": "full_text_storage", **deepcopy(rule)})
    return snapshots, applied


def convert_template(template, source, target):
    """Canonical syntax conversion for reviewed seed templates, not a general language transpiler.

    Only interpolation tokens change; quoted strings and literal template text stay exact.
    The caller must pin the approved Java source: Groovy/JS truthiness is not generally equivalent.
    Unsupported syntax fails closed. Never evaluate expressions.
    """
    operators = {"java": "?:", "rust": "||"}
    if source not in operators or target not in operators or not isinstance(template, str):
        raise ValueError("Unsupported template conversion")
    token = re.compile(r"\s+|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|"
                       r"[A-Za-z_$][A-Za-z0-9_$]*|\?:|\|\||[.()+?:]")

    def expression(match):
        text, tokens, offset = match.group(1), [], 0
        for part in token.finditer(text):
            if part.start() != offset:
                raise ValueError("Unsupported template expression")
            offset = part.end()
            value = part.group()
            if value.isspace():
                continue
            if value == operators[source]:
                value = operators[target]
            elif source != target and value == operators[target]:
                raise ValueError("Unexpected template dialect")
            tokens.append(value)
        if offset != len(text) or not tokens:
            raise ValueError("Unsupported template expression")
        return "${" + " ".join(tokens) + "}"

    # Restrict to brace-free expressions; nested/string braces are deliberately unsupported.
    parts = re.split(r"(\$\{[^{}]*\})", template)
    result = []
    for part in parts:
        match = re.fullmatch(r"\$\{([^{}]*)\}", part)
        if match:
            result.append(expression(match))
        else:
            if "${" in part:
                raise ValueError("Unsupported template interpolation")
            result.append(part)
    return "".join(result)


def apply_template_differences(snapshots, rules):
    applied = []
    for rule in rules:
        matches = [[item["row"] for item in snapshot["records"]
                    if item.get("table") == rule["table"] and "row" in item
                    and all(item["row"].get(key) == value for key, value in rule["key"].items())]
                   for snapshot in snapshots]
        if any(len(rows) != 1 for rows in matches):
            continue
        java, rust = (rows[0] for rows in matches)
        field = rule["field"]
        if java.get(field) != rule["java"]:
            continue
        if rule.get("validator") == "elvis_or":
            try:
                # Both directions must match the pinned source's canonical token stream.
                valid = (convert_template(java[field], "java", "rust")
                         == convert_template(rust.get(field), "rust", "rust")
                         and convert_template(rust.get(field), "rust", "java")
                         == convert_template(java[field], "java", "java"))
            except ValueError:
                valid = False
        elif "validator" not in rule:
            valid = rust.get(field) == rule["rust"]
        else:
            valid = False
        if valid:
            rust[field] = java[field]
            applied.append({"kind": "template_difference", **deepcopy(rule)})
    return applied


def seeded_column_rows_match(snapshots, original, rule):
    """Phase2 Change22: select exact seed values only through the captured primary key."""
    table, name, keys, seeds = (rule[k] for k in ('table', 'name', 'primary_key', 'seed_values'))
    if (not isinstance(keys, list) or not keys or name in keys
            or not all(isinstance(key, str) and re.fullmatch(r'[a-z_][a-z0-9_]*', key) for key in keys)
            or len(set(keys)) != len(keys) or not isinstance(seeds, list) or not seeds):
        return False
    metadata = [[record for record in side['records'] if record.get('relation') == table] for side in original]
    if any(len(items) != 1 or items[0].get('kind') != 'r' for items in metadata):
        return False
    for items in metadata:
        relation = items[0]
        objects = relation.get('schema_objects')
        if not isinstance(objects, list) or any(not isinstance(obj, dict) for obj in objects):
            return False
        primary = [obj for obj in objects if obj.get('primary') is True]
        if len(primary) != 1:
            return False
        obj = primary[0]
        if (not complete_schema_object(obj) or obj['kind'] != 'index' or obj['columns'] != keys
                or obj['method'] != 'btree' or obj['unique'] is not True or obj['exclusion'] is not False
                or any(obj[key] is not True for key in ('valid', 'ready', 'live', 'plain', 'constraint_backed'))
                or obj['key_count'] != len(keys) or obj['attribute_count'] != len(keys)
                or not re.fullmatch(r'[a-z_][a-z0-9_]*', obj['name'])
                or obj['definition'] != f"CREATE UNIQUE INDEX {obj['name']} ON {table} USING btree ({', '.join(keys)})"):
            return False
        for key in keys:
            columns = [column for column in relation['columns'] if column.get('name') == key]
            if (len(columns) != 1 or columns[0].get('not_null') is not True
                    or not isinstance(columns[0].get('type'), str) or not columns[0]['type']):
                return False
    if any(next(c['type'] for c in metadata[0][0]['columns'] if c['name'] == key)
           != next(c['type'] for c in metadata[1][0]['columns'] if c['name'] == key) for key in keys):
        return False

    def identity(value):
        return json.dumps(canonical(json.loads(report_json(value), parse_int=Decimal, parse_float=Decimal)),
                          separators=(',', ':'))

    def valid_key(key):
        return (isinstance(key, dict) and set(key) == set(keys)
                and all(value is not None and not isinstance(value, (dict, list, bool)) for value in key.values()))

    if any(not isinstance(seed, dict) or set(seed) != {'key', 'value'} or seed['value'] is None
           or not valid_key(seed['key']) for seed in seeds):
        return False
    try:
        expected = {identity(seed['key']): identity(seed['value']) for seed in seeds}
        if len(expected) != len(seeds):
            return False
        inventories = []
        for side in original + snapshots:
            relation = next(record for record in side['records'] if record.get('relation') == table)
            fields = [column.get('name') for column in relation['columns']]
            if (not all(isinstance(field, str) and field for field in fields)
                    or len(set(fields)) != len(fields)):
                return False
            rows = [record for record in side['records'] if record.get('table') == table]
            values = {}
            for record in rows:
                if (set(record) != {'table', 'row'} or not isinstance(record['row'], dict)
                        or set(record['row']) != set(fields)):
                    return False
                row = record['row']
                key = {field: row.get(field) for field in keys}
                if not valid_key(key):
                    return False
                token = identity(key)
                if token in values:
                    return False
                values[token] = identity(row[name]) if name in row else None
            inventories.append(values)
        java_original, rust_original, java_current, rust_current = inventories
        null = identity(None)
        # Every listed seed remains present in raw evidence; every other value is null.
        if (any(rust_original.get(key) != value for key, value in expected.items())
                or any(value != expected.get(key, null) for key, value in rust_original.items())
                or any(value is not None for value in java_original.values())
                or any(value is not None for value in java_current.values())
                or any(key not in rust_original or value != rust_original[key] for key, value in rust_current.items())):
            return False
    except (ValueError, TypeError, KeyError):
        return False
    return True


def apply_rust_only_columns(snapshots, rules, *, original=None):
    """Project exact added columns with null-only or explicitly bounded seed values."""
    java, rust = snapshots
    original = deepcopy(snapshots) if original is None else original
    applied = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        seeded = 'primary_key' in rule or 'seed_values' in rule
        if set(rule) != ({'table', 'name', 'type', 'primary_key', 'seed_values'} if seeded else {'table', 'name', 'type'}):
            continue
        table, name = rule['table'], rule['name']
        if (not isinstance(table, str) or not re.fullmatch(r'[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*', table)
                or not isinstance(name, str) or not re.fullmatch(r'[a-z_][a-z0-9_]*', name)
                or not isinstance(rule['type'], str) or not rule['type']):
            continue
        metadata = [[item for item in snapshot['records'] if item.get('relation') == table]
                    for snapshot in snapshots + original]
        if any(len(items) != 1 or not isinstance(items[0].get('columns'), list)
               or any(not isinstance(column, dict) for column in items[0]['columns']) for items in metadata):
            continue
        expected = {'name': name, 'type': rule['type'], 'not_null': False, 'default': None}
        # Phase2 Change22: numeric zero is not a captured boolean nullability flag.
        if any(column.get('not_null') is not False
               for side in (1, 3) for column in metadata[side][0]['columns']
               if column.get('name') == name):
            continue
        if any((any(column.get('name') == name for column in items[0]['columns']) if side % 2 == 0 else
                [column for column in items[0]['columns'] if column.get('name') == name] != [expected])
               for side, items in enumerate(metadata)):
            continue
        rows = [[item.get('row') for item in snapshot['records'] if item.get('table') == table]
                for snapshot in snapshots + original]
        if any(not isinstance(row, dict) for side in rows for row in side):
            continue
        if seeded:
            if not seeded_column_rows_match(snapshots, original, rule):
                continue
        elif (any(name in row for side in (rows[0], rows[2]) for row in side)
                or any(name not in row or row[name] is not None for side in (rows[1], rows[3]) for row in side)):
            continue
        pattern = re.compile(r'(CREATE TABLE ' + re.escape(table) + r' \(\n)(.*?)(\n\);)', re.S)
        matches = [list(pattern.finditer(snapshot['schema'])) for snapshot in snapshots + original]
        if any(len(items) != 1 for items in matches):
            continue
        declaration = '    ' + name + ' ' + rule['type']
        declarations = [items[0].group(2).split(',\n') for items in matches]
        if any((any(re.match(r'\s*' + re.escape(name) + r'\s', column) for column in columns) if side % 2 == 0
                else columns.count(declaration) != 1) for side, columns in enumerate(declarations)):
            continue
        rust['schema'] = pattern.sub(lambda match: match.group(1) + ',\n'.join(
            column for column in declarations[1] if column != declaration) + match.group(3), rust['schema'], count=1)
        metadata[1][0]['columns'].remove(expected)
        for row in rows[1]:
            row.pop(name, None)
        applied.append({'kind': 'rust_only_column', **deepcopy(rule)})
    return applied


def complete_schema_object(obj):
    """Phase2 Change17: matching two incomplete objects is not catalog proof."""
    if not isinstance(obj, dict):
        return False
    common = {"kind", "name", "definition", "columns"}
    if obj.get("kind") == "index":
        strings = {"kind", "name", "definition", "method", "owner"}
        flags = {"unique", "primary", "exclusion", "valid", "ready", "live",
                 "constraint_backed", "plain", "partition", "table_inherits"}
        integers = {"key_count", "attribute_count"}
        fields = common | strings | flags | integers | {"key_metadata", "expressions", "predicate", "options"}
    elif obj.get("kind") == "foreign_key":
        strings = {"kind", "name", "definition", "target", "match", "update", "delete",
                   "target_key_definition", "target_kind"}
        flags = {"enforced", "validated", "deferrable", "deferred", "local", "parent_constraint",
                 "target_key_valid", "target_key_unique", "target_key_plain", "target_partition", "table_inherits"}
        integers = {"inherited"}
        fields = common | strings | flags | integers | {"target_columns", "target_column_types", "trigger_states"}
    else:
        return False

    def integer(value):
        return type(value) is int or (isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value())

    def text_list(value):
        return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v for v in value)

    if (set(obj) != fields or any(not isinstance(obj[k], str) or not obj[k] for k in strings)
            or any(type(obj[k]) is not bool for k in flags)
            or any(not integer(obj[k]) for k in integers) or not text_list(obj["columns"])):
        return False
    if obj["kind"] == "index":
        keys = obj["key_metadata"]
        return (obj["expressions"] is None and obj["predicate"] is None and obj["options"] is None
                and isinstance(keys, list) and len(keys) == len(obj["columns"])
                and all(isinstance(k, dict) and set(k) == {"opclass", "collation", "option"}
                        and isinstance(k["opclass"], str) and bool(k["opclass"])
                        and (k["collation"] is None or isinstance(k["collation"], str) and bool(k["collation"]))
                        and integer(k["option"]) and k["option"] == 0 for k in keys))
    return (text_list(obj["target_columns"]) and text_list(obj["target_column_types"])
            and len(obj["target_columns"]) == len(obj["columns"]) == len(obj["target_column_types"])
            and text_list(obj["trigger_states"]))


# Phase2 Change17: exact catalog-backed additions never waive shared constraints.
def apply_schema_additions(snapshots, original, applied_columns, rules):
    applied = []
    approved_columns = {(r["table"], r["name"]) for r in applied_columns
                        if r["kind"] == "rust_only_column"}
    ident = r"[a-z_][a-z0-9_]*"

    def relation(snapshot, table):
        items = [r for r in snapshot["records"] if r.get("relation") == table]
        return items[0] if len(items) == 1 and items[0].get("kind") == "r" else None

    def bounded(type_name):
        match = re.fullmatch(r"character(?: varying)?\(([1-9][0-9]*)\)", type_name)
        if match:
            return int(match[1]) * 4
        return {"smallint": 2, "integer": 4, "bigint": 8, "boolean": 1,
                "date": 4, "timestamp without time zone": 8}.get(type_name)

    for rule in rules:
        table, name, obj = rule.get("table", ""), rule.get("name", ""), rule.get("catalog", {})
        if (not complete_schema_object(obj)
                or not re.fullmatch(ident + r"\." + ident, table)
                or not re.fullmatch(ident, name) or obj.get("name") != name):
            continue
        before = [relation(s, table) for s in original]
        current = relation(snapshots[1], table)
        if any(r is None or not isinstance(r.get("schema_objects"), list) for r in before) or current is None:
            continue
        matches = [[o for o in r["schema_objects"] if o.get("name") == name and o.get("kind") == obj["kind"]] for r in before]
        if matches[0] or matches[1] != [obj]:
            continue
        columns = obj.get("columns", [])
        if (not isinstance(columns, list) or not columns
                or any(not isinstance(c, str) or not re.fullmatch(ident, c) for c in columns)
                or len(set(columns)) != len(columns)):
            continue
        shared, extras, width, valid = [], [], 0, True
        for column in columns:
            definitions = [[c for c in r["columns"] if c["name"] == column] for r in before]
            if len(definitions[1]) != 1:
                valid = False
                break
            if definitions[0]:
                if definitions[0] != definitions[1] or len(definitions[0]) != 1:
                    valid = False
                    break
                size = bounded(definitions[0][0]["type"])
                if size is None:
                    valid = False
                    break
                shared.append(column)
                width += size
            else:
                if (table, column) not in approved_columns:
                    valid = False
                    break
                extras.append(column)
                # Recheck raw rows: missing fields are not evidence of NULL.
                if any(column not in r["row"] or r["row"][column] is not None
                       for r in original[1]["records"] if r.get("table") == table):
                    valid = False
                    break
        if not valid or width > 512:
            continue
        if obj.get("kind") == "index":
            required = {"method": "btree", "unique": False, "primary": False,
                        "exclusion": False, "valid": True, "ready": True, "live": True,
                        "expressions": None, "predicate": None, "constraint_backed": False,
                        "plain": True, "options": None, "partition": False, "table_inherits": False}
            if (any(k not in obj or obj[k] != v for k, v in required.items())
                    or obj.get("key_count") != len(columns) or obj.get("attribute_count") != len(columns)
                    or (not extras and rule.get("shared_only") is not True)):
                continue
            ddl = f"CREATE INDEX {name} ON {table} USING btree ({', '.join(columns)});"
            if obj.get("definition") != ddl[:-1]:
                continue
            dump_kind, dump_name = "INDEX", name
        elif obj.get("kind") == "foreign_key":
            if shared or not extras:
                continue
            required = {"validated": True, "deferrable": False, "deferred": False,
                        "match": "s", "update": "a", "delete": "a", "local": True,
                        "inherited": 0, "parent_constraint": False, "target_key_valid": True,
                        "target_key_unique": True, "target_key_plain": True, "target_kind": "r",
                        "target_partition": False, "table_inherits": False, "enforced": True,
                        "trigger_states": ["O", "O", "O", "O"]}
            if any(k not in obj or obj[k] != v for k, v in required.items()):
                continue
            parent, keys = obj.get("target", ""), obj.get("target_columns", [])
            if (not re.fullmatch(ident + r"\." + ident, parent) or len(keys) != len(columns)
                    or any(not isinstance(c, str) or not re.fullmatch(ident, c) for c in keys)):
                continue
            definition = f"FOREIGN KEY ({', '.join(columns)}) REFERENCES {parent}({', '.join(keys)})"
            if obj.get("definition") != definition:
                continue
            ddl = f"ALTER TABLE ONLY {table}\n    ADD CONSTRAINT {name} {definition};"
            dump_kind, dump_name = "FK CONSTRAINT", table.split(".")[1] + " " + name
        else:
            continue
        if rule.get("ddl") != ddl:
            continue
        # Match complete statement lines. Extra SQL remains visible, even after a matching statement.
        statement = re.compile(r"^" + re.escape(ddl) + r"$", re.M)
        if obj["kind"] == "index":
            # Index names belong to a schema; foreign-key names belong to a table.
            schema = re.escape(table.split(".")[0])
            identity = re.compile(r"^CREATE (?:UNIQUE )?INDEX (?:" + schema + r"\.)?" + re.escape(name)
                                  + r"\s+ON (?:ONLY )?" + schema + r"\." + ident + r"(?=\s|\()", re.M)
        else:
            identity = re.compile(r"^ALTER TABLE (?:ONLY )?" + re.escape(table)
                                  + r"\s+ADD CONSTRAINT " + re.escape(name) + r"(?=\s)", re.M)
        if (identity.search(original[0]["schema"])
                or len(identity.findall(original[1]["schema"])) != 1
                or len(statement.findall(snapshots[1]["schema"])) != 1):
            continue
        objects = current.get("schema_objects", [])
        if [o for o in objects if o.get("name") == name and o.get("kind") == obj["kind"]] != [obj]:
            continue
        # Header removal is restricted to the exact object, never a whole pg_dump block.
        header = (r"--\n-- Name: " + re.escape(dump_name) + "; Type: " + dump_kind
                  + "; Schema: " + re.escape(table.split(".")[0]) + r"; Owner: (?:[a-z_][a-z0-9_]*|-)\n--\n\n")
        snapshots[1]["schema"] = re.sub(
            r"^(?:" + header + r")?" + re.escape(ddl) + r"(?:\n{1,3}|$)",
            "", snapshots[1]["schema"], count=1, flags=re.M)
        objects.remove(obj)
        applied.append({"kind": "schema_addition", **deepcopy(rule), "null_only_columns": extras})
    return applied


def apply_rust_only_ddl(snapshots, rules):
    """Remove only the exact approved schema/extension blocks, never their contained tables."""
    java, rust = snapshots
    applied = []
    for rule in rules:
        kind, name = rule["kind"], rule["name"]
        if kind not in ("SCHEMA", "EXTENSION"):
            continue
        create = re.compile(r"^CREATE " + kind + r" (?:IF NOT EXISTS )?" + re.escape(name) + r"(?=[\s;])", re.M)
        if create.search(java["schema"]) or len(create.findall(rust["schema"])) != 1:
            continue
        if not rule["blocks"] or any(rust["schema"].count(block) != 1 for block in rule["blocks"]):
            continue
        for block in rule["blocks"]:
            rust["schema"] = rust["schema"].replace(block, "", 1)
        applied.append({"kind": "rust_only_ddl", "object_type": kind, "name": name})
    return applied


def apply_extension_views(snapshots, rules):
    """Phase 2 Change 13: require captured ownership and exact absent-view metadata."""
    applied = []
    for rule in rules:
        side = rule.get("engine")
        expected = rule.get("metadata", {})
        owner = expected.get("extension")
        name = expected.get("relation")
        if (side not in ("java", "rust") or expected.get("kind") != "v"
                or not name or not expected.get("view_definition") or not isinstance(owner, dict)
                or set(owner) != {"name", "version"} or not all(owner.values())):
            continue
        current, other = snapshots if side == "java" else reversed(snapshots)
        matches = [record for record in current["records"] if record.get("relation") == name]
        if matches != [expected]:
            continue
        if any(record.get("relation") == name or record.get("table") == name
               for record in other["records"]):
            continue
        # Extension-owned views have no independent pg_dump view block or stored rows.
        declaration = re.compile(r"^CREATE (?:OR REPLACE )?(?:MATERIALIZED )?VIEW "
                                 + re.escape(name) + r"(?=[\s;(])", re.M)
        if any(declaration.search(snapshot["schema"]) for snapshot in snapshots):
            continue
        if any(record.get("table") == name for record in current["records"]):
            continue
        current["records"].remove(matches[0])
        applied.append({"kind": "extension_view", "engine": side, "metadata": deepcopy(expected)})
    return applied


def apply_java_only_tables(snapshots, tables):
    """Use the same absence/metadata/DDL guards for explicitly approved Java relations."""
    applied = apply_rust_only_tables([snapshots[1], snapshots[0]], tables)
    return [{**item, "kind": "java_only_table"} for item in applied]


def apply_reviewed_seed_rows(snapshots, rules):
    """Exclude a reviewed asymmetric row only with exact non-generated values."""
    applied = []
    for rule in rules:
        if rule.get("engine") not in ("java", "rust") or not rule.get("key"):
            continue
        side = 0 if rule["engine"] == "java" else 1
        matches = [[item for item in snapshot["records"]
                    if item.get("table") == rule["table"] and "row" in item
                    and all(item["row"].get(k) == v for k, v in rule["key"].items())]
                   for snapshot in snapshots]
        if matches[1 - side] or len(matches[side]) != 1:
            continue
        item = matches[side][0]
        if {k: v for k, v in item["row"].items() if k != "last_updated_stamp"} != rule["expected"]:
            continue
        snapshots[side]["records"].remove(item)
        applied.append({"kind": "reviewed_seed_row", "engine": rule["engine"],
                        "table": rule["table"], "key": deepcopy(rule["key"])})
    return applied


def apply_reviewed_event_sets(snapshots, original, rules):
    """Phase2 Change21: exact reviewed event correspondence never hides later events."""
    applied = []
    tables = Counter(rule.get('table') for rule in rules if isinstance(rule, dict)
                     and isinstance(rule.get('table'), str))

    def identity(value):
        # Match JSON numeric types without conflating booleans, strings, or rounded floats.
        return json.dumps(canonical(json.loads(report_json(value), parse_int=Decimal, parse_float=Decimal)),
                          separators=(',', ':'))

    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {'table', 'primary_key', 'shared_pairs', 'rust_only'}:
            continue
        table, keys = rule['table'], rule['primary_key']
        pairs, extra = rule['shared_pairs'], rule['rust_only']
        if (not isinstance(table, str) or not re.fullmatch(r'[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*', table)
                or tables[table] != 1 or not isinstance(keys, list) or not keys
                or not all(isinstance(key, str) and key for key in keys) or len(set(keys)) != len(keys)
                or not isinstance(pairs, list) or not isinstance(extra, list) or not (pairs or extra)
                or any(not isinstance(pair, dict) or set(pair) != {'java', 'rust'} for pair in pairs)):
            continue
        selected = [[pair[side] for pair in pairs] + (extra if side == 'rust' else [])
                    for side in ('java', 'rust')]
        metadata = [[record for record in snapshot['records'] if record.get('relation') == table]
                    for snapshot in original]
        if any(len(items) != 1 or items[0].get('kind') != 'r'
               or not isinstance(items[0].get('columns'), list)
               or any(not isinstance(column, dict) for column in items[0]['columns']) for items in metadata):
            continue
        fields = [[column.get('name') for column in items[0]['columns'] if isinstance(column, dict)]
                  for items in metadata]
        if (not fields[0] or fields[0] != fields[1]
                or any(not isinstance(field, str) or not field for field in fields[0])
                or len(set(fields[0])) != len(fields[0]) or not set(keys) < set(fields[0])):
            continue
        rows = [[record for record in snapshot['records'] if record.get('table') == table]
                for snapshot in original]
        current = [[record for record in snapshot['records'] if record.get('table') == table]
                   for snapshot in snapshots]
        if (any(set(record) != {'table', 'row'} or not isinstance(record['row'], dict)
                or set(record['row']) != set(fields[0])
                or any(record['row'][key] is None or isinstance(record['row'][key], (dict, list, bool)) for key in keys)
                for side in rows + current for record in side)
                or any(not isinstance(row, dict) or set(row) != set(fields[0])
                       or any(row[key] is None or isinstance(row[key], (dict, list, bool)) for key in keys)
                       for side in selected for row in side)):
            continue
        try:
            def primary(row):
                return identity({key: row[key] for key in keys})

            def payload(row):
                return identity({key: value for key, value in row.items() if key not in keys})

            originals = [[record['row'] for record in side] for side in rows]
            primary_counts = [Counter(primary(row) for row in side) for side in originals]
            payload_counts = [Counter(payload(row) for row in side) for side in originals]
            row_counts = [Counter(identity(row) for row in side) for side in originals]
            current_counts = [Counter(identity(record['row']) for record in side) for side in current]
            selected_ids = [[primary(row) for row in side] for side in selected]
            selected_payloads = [[payload(row) for row in side] for side in selected]
            valid = (all(count == 1 for counts in primary_counts for count in counts.values())
                and all(len(set(side)) == len(side) for side in selected_ids + selected_payloads)
                and all(payload(pair['java']) == payload(pair['rust']) for pair in pairs)
                and all(payload_counts[0][payload(row)] == 0 for row in extra)
                and all(row_counts[side][identity(row)] == current_counts[side][identity(row)] == 1
                        and payload_counts[side][payload(row)] == 1
                        for side in (0, 1) for row in selected[side]))
            tokens = [set(identity(row) for row in side) for side in selected]
        except (TypeError, ValueError, KeyError):
            continue
        if not valid:
            continue
        for side in (0, 1):
            snapshots[side]['records'] = [record for record in snapshots[side]['records']
                if not (record.get('table') == table and identity(record['row']) in tokens[side])]
        applied.append({'kind': 'reviewed_event_set', **deepcopy(rule),
                        'java_rows': len(selected[0]), 'rust_rows': len(selected[1])})
    return applied


def owned_table_dump_block(block, table):
    """Phase2 Change19: require complete owned statements before excluding a dump block."""
    header = re.match(r"--\n-- Name: [^\n]+; Type: (?:TABLE|INDEX|CONSTRAINT|FK CONSTRAINT); "
                      r"Schema: [^\n]+; Owner: [^\n]+\n--\n\n", block)
    if not header:
        return False
    body = block[header.end():]
    # Standard pg_dump quotes can contain semicolons and newlines. Unsupported SQL
    # remains visible, including dollar quotes, escape strings and inline comments.
    tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[^'\";]+|;", body)
    if ''.join(tokens) != body:
        return False
    statements, current = [], ''
    for token in tokens:
        if token == ';':
            statements.append(current.strip())
            current = ''
        else:
            if not token.startswith(("'", '"')) and any(marker in token for marker in ('--', '/*', '$', '\\')):
                return False
            if token.startswith("'") and re.search(r"\b[Ee]$", current):
                return False
            current += token
    if current.strip() or not statements:
        return False
    target = re.escape(table)
    identifier = r'(?:[a-z_][a-z0-9_]*|"(?:[^"]|"")+")'
    patterns = [
        r"CREATE TABLE " + target + r" \([\s\S]*\)",
        r"ALTER TABLE (?:ONLY )?" + target + r" OWNER TO " + identifier,
        r"ALTER TABLE ONLY " + target + r"\s+ADD CONSTRAINT " + identifier + " "
        + r"(?:PRIMARY KEY|UNIQUE|FOREIGN KEY|CHECK|EXCLUDE)\b[\s\S]+",
        r"CREATE (?:UNIQUE )?INDEX " + identifier + r" ON (?:ONLY )?" + target
        + r" USING [a-z_][a-z0-9_]* \([\s\S]*\)(?: WHERE [\s\S]+)?",
    ]
    return (sum(bool(re.fullmatch(patterns[0], statement)) for statement in statements) <= 1
            and all(any(re.fullmatch(pattern, statement) for pattern in patterns) for statement in statements))


def apply_rust_only_tables(snapshots, tables):
    """Set aside listed Rust-only tables, retaining all raw evidence and shared objects."""
    java, rust = snapshots
    applied = []
    for table in tables:
        target = re.escape(table) + r"(?=[\s;(])"
        create = re.compile(r"^CREATE TABLE " + target, re.M)
        metadata = [item for item in rust["records"] if item.get("relation") == table]
        if (any(item.get("relation") == table or item.get("table") == table
                for item in java["records"]) or create.search(java["schema"])
                or len(metadata) != 1 or metadata[0].get("kind") != "r"
                or len(create.findall(rust["schema"])) != 1):
            continue
        owned = re.compile(r"^(?:CREATE TABLE |ALTER TABLE (?:ONLY )?|"
                           r"CREATE (?:UNIQUE )?INDEX \S+ ON (?:ONLY )?)" + target, re.M)
        blocks = re.split(r"(?=--\n-- (?:Name: |PostgreSQL database dump complete\n))", rust["schema"])
        selected = [block for block in blocks if owned.search(block)]
        if not selected or not all(owned_table_dump_block(block, table) for block in selected):
            continue
        rust["schema"] = "".join(block for block in blocks if not owned.search(block))
        rows = sum(item.get("table") == table for item in rust["records"])
        rust["records"] = [item for item in rust["records"]
                           if item.get("relation") != table and item.get("table") != table]
        applied.append({"kind": "rust_only_table", "table": table, "rows": rows})
    return applied


def apply_statistics_bin_boundaries(snapshots, timing_rules):
    """Accept different bin splits, not different workloads. Raw snapshots are untouched."""
    timing = next((rule["fields"] for rule in timing_rules
                   if rule["table"] == "public.artifact_hit_bin"), [])
    if not timing:
        return []
    groups, removed, applied = [{}, {}], [[], []], []
    for side, snapshot in enumerate(snapshots):
        bins = bin_rows(snapshot)
        # Duplicate/malformed ids must not be hidden by aggregation.
        try:
            ids = [int(item["row"]["hit_bin_id"]) for item in bins]
        except (KeyError, TypeError, ValueError):
            return []
        if len(set(ids)) != len(ids):
            return []
        for item in bins:
            row = item["row"]
            count = row.get("hit_count")
            if (any(field not in row or row[field] is not None for field in timing)
                    or not isinstance(count, Decimal) or not count.is_finite()
                    or count <= 0 or count != count.to_integral_value()):
                continue
            key = json.dumps(canonical({k: v for k, v in row.items()
                                        if k not in (*timing, "hit_bin_id", "hit_count")}))
            groups[side].setdefault(key, []).append(item)
    for key in sorted(groups[0].keys() & groups[1].keys()):
        sides = [group[key] for group in groups]
        totals = [sum(item["row"]["hit_count"] for item in items) for items in sides]
        if (len(sides[0]) == len(sides[1]) == 1) or totals[0] != totals[1]:
            continue
        for side, items in enumerate(sides):
            items.sort(key=lambda item: int(item["row"]["hit_bin_id"]))
            items[0]["row"]["hit_count"] = totals[side]
            for item in items[1:]:
                removed[side].append(int(item["row"]["hit_bin_id"]))
                snapshots[side]["records"].remove(item)
        applied.append({"kind": "statistics_bin_boundaries", "identity": json.loads(key),
                        "java_bins": len(sides[0]), "rust_bins": len(sides[1]),
                        "hit_count": int(totals[0])})
    for side, snapshot in enumerate(snapshots):
        for item in bin_rows(snapshot):
            original = int(item["row"]["hit_bin_id"])
            shift = sum(gap < original for gap in removed[side])
            if shift:
                item["row"]["hit_bin_id"] = str(original - shift)
    return applied


def apply_seed_statistics(snapshots, seed_row_deltas):
    """Hit counts that follow from approved seed rows. The empty-database load refreshes and then creates
    each row once, so an approved row present on only one engine moves that entity's create and refresh
    counts by one. A bin is adjusted only when each engine has at most one bin for the operation and the
    counts differ by exactly the approved rows; a Rust bin left with no hits must have no Java counterpart
    and is set aside. The bins it leaves behind in the same flush keep their order: their sequenced ids
    close the gap, so ids stay strict for every other bin."""
    def bins(snapshot, name, sub_type):
        return [item for item in snapshot["records"] if item.get("table") == "public.artifact_hit_bin"
                and item["row"].get("artifact_type") == "AT_ENTITY"
                and item["row"].get("artifact_sub_type") == sub_type
                and item["row"].get("artifact_name") == name]

    applied, removed = [], []
    for name, delta in sorted(seed_row_deltas.items()):
        if not delta:
            continue
        for sub_type in ("create", "refresh"):
            java_bins, rust_bins = (bins(snapshot, name, sub_type) for snapshot in snapshots)
            if len(java_bins) > 1 or len(rust_bins) > 1 or not (java_bins or rust_bins):
                continue
            java_count = java_bins[0]["row"]["hit_count"] if java_bins else 0
            rust_count = rust_bins[0]["row"]["hit_count"] if rust_bins else 0
            if rust_count - java_count != delta:
                continue
            if rust_bins and not java_bins:
                removed.append(rust_bins[0]["row"])
                snapshots[1]["records"].remove(rust_bins[0])
            elif java_bins and not rust_bins:
                continue  # Java-only bins are never approved by a seed rule.
            else:
                rust_bins[0]["row"]["hit_count"] = java_count
            applied.append({"kind": "seed_statistics", "artifact_name": name, "artifact_sub_type": sub_type,
                            "java_hit_count": int(java_count), "rust_hit_count": int(rust_count)})
    # Ids are issued in order within one flush, which shares its bin end time.
    gaps = [(row.get("bin_end_date_time"), int(row["hit_bin_id"])) for row in removed]
    for item in snapshots[1]["records"]:
        if item.get("table") != "public.artifact_hit_bin":
            continue
        row = item["row"]
        original = int(row["hit_bin_id"])
        shift = sum(1 for end, gap in gaps if end == row.get("bin_end_date_time") and gap < original)
        if shift:
            row["hit_bin_id"] = str(original - shift)
    return applied


def bin_rows(snapshot):
    return [item for item in snapshot["records"] if item.get("table") == "public.artifact_hit_bin"]


def apply_rust_only_statistics(snapshots, rule):
    """Rust counts reads Java does not make (FK existence checks, the load report counts) under sub types of
    their own. Those bins are set aside here and listed in the report, not compared with Java. Java must have
    no bin of these sub types, and Rust gives them the ids after shared bins in the same flush, so no other id moves."""
    if not rule:
        return []
    sub_types = set(rule["artifact_sub_types"])
    if any(item["row"].get("artifact_sub_type") in sub_types for item in bin_rows(snapshots[0])):
        return []
    rust_only = [item for item in bin_rows(snapshots[1]) if item["row"].get("artifact_sub_type") in sub_types]
    others = [item["row"] for item in bin_rows(snapshots[1]) if item not in rust_only]
    if not rust_only or any(
            row.get("bin_end_date_time") == item["row"].get("bin_end_date_time")
            and int(item["row"]["hit_bin_id"]) < int(row["hit_bin_id"])
            for item in rust_only for row in others):
        return []
    for item in rust_only:
        snapshots[1]["records"].remove(item)
    rows = sorted(({"artifact_type": item["row"]["artifact_type"],
                    "artifact_sub_type": item["row"]["artifact_sub_type"],
                    "artifact_name": item["row"]["artifact_name"],
                    "hit_count": int(item["row"]["hit_count"])} for item in rust_only),
                  key=lambda row: (row["artifact_sub_type"], row["artifact_name"]))
    return [{"kind": "rust_only_statistics", "rows": rows,
             "hit_count": sum(row["hit_count"] for row in rows)}]


def git(*args):
    subprocess.run(["git", *map(str, args)], check=True)


def engine_directories(args=None):
    return {name: Path(getattr(args, f"{name}_checkout", None) or ROOT / checkout).resolve()
            for name, checkout in zip(("java", "rust"), REPOSITORIES)}


def rust_artifact(directory):
    target = Path(os.environ.get("CARGO_TARGET_DIR", "target"))
    if not target.is_absolute():
        target = directory / target
    return target / "debug/moqui"


def build_engines(java_home=None, directories=None):
    environment = os.environ.copy()
    if java_home:
        environment["JAVA_HOME"] = str(Path(java_home).resolve())
        environment["PATH"] = str(Path(java_home).resolve() / "bin") + os.pathsep + environment.get("PATH", "")

    manifest = ROOT / ".runs" / "build.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.unlink(missing_ok=True)
    engines = (
        ("java", "moqui-framework", ["./gradlew", "--no-daemon", "clean", "build"], "moqui.war"),
        ("rust", "mr-moqui", ["cargo", "build", "--locked", "-p", "moqui"], "target/debug/moqui"),
    )
    artifacts = {}
    directories = directories or engine_directories()
    for name, checkout, command, artifact in engines:
        directory = directories[name]
        runtime = directory / "runtime"
        if runtime.is_symlink() or not (runtime / "conf" / "MoquiDevConf.xml").is_file():
            raise SystemExit(f"Missing private runtime configuration: {runtime}")
        # Change 2: Recent hosts embed a locally prepared PostgreSQL archive at build time.
        if name == "rust" and (directory / "scripts/pg-payload.sh").is_file():
            subprocess.run(["bash", "scripts/pg-payload.sh", "strip"], cwd=directory,
                           env=environment, check=True)
        print(f"Building {name}: {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=directory, env=environment, check=True)
        executable = rust_artifact(directory) if name == "rust" else directory / artifact
        if not executable.is_file():
            raise SystemExit(f"Build did not produce {executable}")
        if name == "rust" and not os.access(executable, os.X_OK):
            raise SystemExit(f"Rust artifact is not executable: {executable}")
        with executable.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        artifacts[name] = {
            "artifact": str(executable),
            "runtime": str(runtime),
            "sha256": checksum,
            "checkout": str(directory),
        }
    manifest.write_text(json.dumps(artifacts, indent=2) + "\n")
    print(f"Both engines built; artifact/runtime paths recorded in {manifest}")


def demo_conf(source, destination, db_port, password, http_port, crypt_pass):
    """Preserve dev/demo settings, overriding test connectivity and the shared test key."""
    tree = ET.parse(source)
    root = tree.getroot()
    properties = {
        "entity_ds_db_conf": "postgres",
        "entity_ds_host": "127.0.0.1",
        "entity_ds_port": str(db_port),
        "entity_ds_database": "moqui",
        "entity_ds_schema": "public",
        "entity_ds_user": "moqui",
        "entity_ds_password": password,
        "entity_ds_crypt_pass": crypt_pass,
        "entity_ds_sslmode": "disable",
        "entity_empty_db_load": "all",
        "webapp_http_port": str(http_port),
        "webapp_https_enabled": "false",
        "cluster_https_port": "0",
        # Change 3: Auxiliary listeners must not collide with another local instance.
        "ssh_port": "0",
        "opensearch_run": "false",
    }
    for name, value in properties.items():
        node = root.find(f"default-property[@name='{name}']")
        if node is None:
            node = ET.SubElement(root, "default-property", {"name": name})
        node.set("value", value)
    receiver = root.find("telemetry/receiver")
    if receiver is not None:
        receiver.set("grpc-port", "0")
    # The generated configuration contains disposable database credentials.
    destination.touch(mode=0o600)
    tree.write(destination, encoding="utf-8", xml_declaration=True)


def wait_for_ports(processes, ports, timeout, boot_logs=None, failure_check=None):
    """Wait for completed application initialization and both HTTP ports to listen."""
    waiting = set(processes)
    deadline = time.monotonic() + timeout
    while waiting:
        if failure_check:
            failure_check()
        for name in list(waiting):
            process = processes[name]
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited before readiness; see its boot log")
            if boot_logs:
                text = boot_logs[name].read_text(errors="replace")
                # Phase 1, Change 1: Accept both HTTP listener messages after data initialization.
                if name == "java":
                    if not all(marker in text for marker in (
                            "records (with types from empty-db-load:", "Moqui Framework initialized in")):
                        continue
                elif ("Table check and empty-db load finished" not in text
                      or not re.search(r"Listening (?:for HTTP )?on [^\s]+:" + str(ports[name]) + r"(?:\s|$)", text)):
                    continue
                # MoquiStart initializes the webapp before registering Jetty's shutdown hook.
                if name == "java" and not re.search(r"Started (?:oejs\.)?Server@", text):
                    continue
            try:
                with socket.create_connection(("127.0.0.1", ports[name]), timeout=0.2):
                    pass
            except OSError:
                continue
            waiting.remove(name)
            print(f"{name} reached port {ports[name]}", flush=True)
        if waiting and time.monotonic() >= deadline:
            raise TimeoutError(f"HTTP-port readiness timed out: {', '.join(sorted(waiting))}")
        if waiting:
            time.sleep(0.1)


def stop_engines(processes, boot_logs, timeout):
    """Signal both engines first; verify only shutdown evidence written after SIGTERM."""
    offsets = {name: path.stat().st_size for name, path in boot_logs.items()}
    report = {}
    deadline = time.monotonic() + timeout
    for name, process in processes.items():
        report[name] = {"forced_kill": False, "errors": []}
        if process.poll() is not None:
            report[name]["errors"].append("Engine exited before shutdown was requested")
            continue
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for name, process in processes.items():
        result = report[name]
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            result["forced_kill"] = True
            result["errors"].append("Graceful shutdown timed out; SIGKILL required")
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        result["returncode"] = process.returncode
        allowed_codes = (0, 128 + signal.SIGTERM, -signal.SIGTERM) if name == "java" else (0,)
        if process.returncode not in allowed_codes:
            result["errors"].append(f"Unexpected exit code: {process.returncode}")
        with boot_logs[name].open("rb") as stream:
            stream.seek(offsets[name])
            text = stream.read().decode("utf-8", errors="replace")
        # Change 4: Current Rust uses telemetry instead of legacy artifact-bin persistence.
        # Either version must supply fresh shutdown evidence, alongside a clean process exit.
        markers = (("ArtifactHitBins stored", "Moqui ExecutionContextFactory Destroyed")
                   if name == "java" else
                   (() if "Moqui server shutdown complete" in text else ("ArtifactHitBins stored",)))
        result["missing_shutdown_markers"] = [marker for marker in markers if marker not in text]
        if result["missing_shutdown_markers"]:
            result["errors"].append("Missing post-SIGTERM flush/completion evidence")
    return report


def canonical(value):
    if isinstance(value, dict):
        return ["object", [[key, canonical(item)] for key, item in sorted(value.items())]]
    if isinstance(value, list):
        return ["array", [canonical(item) for item in value]]
    if isinstance(value, Decimal):
        # normalize() can round large values under the default Decimal context.
        number = format(value, "f")
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return ["number", "0" if value == 0 else number]
    return [type(value).__name__, value]


def report_json(value):
    """Phase2 Change17: retain exact JSON numbers in diagnostic catalogs and proofs."""
    def encode(item, depth):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError("Non-finite report number")
            return str(item)
        if isinstance(item, (dict, list)):
            opening, closing = ("{", "}") if isinstance(item, dict) else ("[", "]")
            if not item:
                return opening + closing
            indent = "  " * (depth + 1)
            values = ([json.dumps(key) + ": " + encode(child, depth + 1)
                       for key, child in item.items()] if isinstance(item, dict) else
                      [encode(child, depth + 1) for child in item])
            return opening + "\n" + indent + (",\n" + indent).join(values) + "\n" + "  " * depth + closing
        return json.dumps(item, allow_nan=False)
    return encode(value, 0)


def startup_summary(java, rust):
    """Diagnostic inventory only: Rust-only objects are reported, never excluded."""
    relations, tables = [], []
    for snapshot in (java, rust):
        inventory, rows = {}, {}
        for record in snapshot["records"]:
            item = json.loads(record, parse_int=Decimal, parse_float=Decimal)
            if "relation" in item:
                inventory[item["relation"]] = item
            if "table" in item and "row" in item:
                rows.setdefault(item["table"], []).append(item["row"])
        relations.append(inventory)
        tables.append(rows)

    def counts(values):
        return Counter(json.dumps(canonical(value), separators=(",", ":")) for value in values)

    differing_tables = {}
    for table in sorted(tables[0].keys() | tables[1].keys()):
        left, right = (side.get(table, []) for side in tables)
        left_counts, right_counts = counts(left), counts(right)
        if left_counts == right_counts:
            continue
        columns = sorted(set().union(*(row.keys() for row in left + right)))
        differing_tables[table] = {
            "java_rows": len(left), "rust_rows": len(right),
            "java_unmatched_rows": sum((left_counts - right_counts).values()),
            "rust_unmatched_rows": sum((right_counts - left_counts).values()),
            # Column multisets locate likely causes; they do not establish row equality.
            "differing_column_multisets": [column for column in columns if
                counts([column in row, row.get(column)] for row in left) !=
                counts([column in row, row.get(column)] for row in right)],
        }
    # Diagnostics only: compare each operation's bin hit-count multiset without
    # timing/sequence-id noise. Do not sum bins: that would conceal duplicates.
    bin_groups = []
    identity = ("artifact_type", "artifact_sub_type", "artifact_name")
    for side in tables:
        groups = {}
        for row in side.get("public.artifact_hit_bin", []):
            key = tuple(row.get(field) for field in identity)
            groups.setdefault(key, []).append(str(row.get("hit_count")))
        bin_groups.append({key: sorted(values) for key, values in groups.items()})
    operation_differences = [
        {**dict(zip(identity, key)), "java_hit_counts": bin_groups[0].get(key, []),
         "rust_hit_counts": bin_groups[1].get(key, [])}
        for key in sorted(bin_groups[0].keys() | bin_groups[1].keys(), key=repr)
        if bin_groups[0].get(key, []) != bin_groups[1].get(key, [])
    ]
    return {
        "artifact_bin_operations": {
            "diagnostic_only": True,
            "operation_bin_multisets_equal": not operation_differences,
            "java_bins": sum(len(values) for values in bin_groups[0].values()),
            "rust_bins": sum(len(values) for values in bin_groups[1].values()),
            "differing_operations": operation_differences,
        },
        "relation_inventory_available": bool(relations[0]) and bool(relations[1]),
        "java_only_relations": sorted(relations[0].keys() - relations[1].keys()),
        "rust_only_relations": sorted(relations[1].keys() - relations[0].keys()),
        "shared_relation_differences": {
            name: {"java": relations[0][name], "rust": relations[1][name]}
            for name in sorted(relations[0].keys() & relations[1].keys())
            if relations[0][name] != relations[1][name]
        },
        "differing_tables": differing_tables,
        "differences_excluded": False,
    }


STATISTICS_TABLES = ("public.artifact_hit_bin", "public.artifact_hit")


def statistics_equal(normalized):
    """The artifact statistics alone, after approved differences: every hit and bin row, and the hit bin
    sequence position. Timestamps of other tables do not decide this verdict; the full gate still does."""
    def rows(snapshot):
        selected = []
        for record in snapshot["records"]:
            table, row = record.get("table"), record.get("row")
            if table in STATISTICS_TABLES:
                selected.append(record)
            elif table == "public.sequence_value_item" and row.get("seq_name") in (
                    "moqui.server.ArtifactHit", "moqui.server.ArtifactHitBin"):
                selected.append({"table": table, "row": {"seq_name": row["seq_name"], "seq_num": row.get("seq_num")}})
        return Counter(json.dumps(canonical(record), separators=(",", ":")) for record in selected)
    return rows(normalized[0]) == rows(normalized[1])


def snapshot_compare(left, right, report_dir, *, rust_only_manifest=None, source_root=None,
                     approved_differences=None, emit_report=True):
    """Compare complete captured row multisets, retaining duplicate rows."""
    java, rust = (json.loads(path.read_text()) for path in (left, right))
    (report_dir / "summary.json").write_text(report_json(startup_summary(java, rust)) + "\n")
    exclusions = None
    schema_proof = (java, rust)  # Phase2 Change17: retain rows before source exclusions.
    if rust_only_manifest is not None:
        java, rust, exclusions = filter_snapshots(
            java, rust, rust_only_manifest, ROOT if source_root is None else source_root,
        )
    rows = []
    for snapshot in (java, rust):
        rows.append(Counter(json.dumps(canonical(json.loads(
            record, parse_int=Decimal, parse_float=Decimal,
        )), ensure_ascii=True, separators=(",", ":")) for record in snapshot["records"]))
    java_rows, rust_rows = rows
    normalized, applied = apply_approved_differences(
        java, rust, APPROVED_STARTUP_DIFFERENCES if approved_differences is None else approved_differences,
        schema_proof=schema_proof)
    accepted_rows = [Counter(json.dumps(canonical(record), ensure_ascii=True, separators=(",", ":"))
                             for record in snapshot["records"]) for snapshot in normalized]
    accepted_schema_equal = normalized[0]["schema"] == normalized[1]["schema"]
    equal = accepted_schema_equal and accepted_rows[0] == accepted_rows[1]
    schema_equal = java["schema"] == rust["schema"]
    java_schema, rust_schema = (snapshot["schema"].encode("utf-8") for snapshot in (java, rust))
    schema_bytes = []
    # Positional byte ranges are exact and linear-time; a minimal edit alignment
    # on large, repetitive SQL dumps can take minutes. schema.diff gives line context.
    start = None
    length = max(len(java_schema), len(rust_schema))
    for offset in range(length + 1):
        different = offset < length and java_schema[offset:offset + 1] != rust_schema[offset:offset + 1]
        if different and start is None:
            start = offset
        elif not different and start is not None:
            left_bytes, right_bytes = java_schema[start:offset], rust_schema[start:offset]
            schema_bytes.append({
                "operation": "replace" if left_bytes and right_bytes else "delete" if left_bytes else "insert",
                "java_offset": min(start, len(java_schema)),
                "rust_offset": min(start, len(rust_schema)),
                "java_hex": left_bytes.hex(), "rust_hex": right_bytes.hex(),
            })
            start = None
    report = {
        "byte_encoding": "UTF-8 schema text and canonical JSON records; hex is exact",
        "schema_byte_differences": schema_bytes,
        "record_byte_differences": [
            {"side": side, "count": count, "hex": record.encode("utf-8").hex()}
            for side, differences in (("java", java_rows - rust_rows), ("rust", rust_rows - java_rows))
            for record, count in sorted(differences.items())
        ],
        "approved_differences_applied": applied,
        "unapproved_record_byte_differences": [
            {"side": side, "count": count, "hex": record.encode("utf-8").hex()}
            for side, differences in (("java", accepted_rows[0] - accepted_rows[1]),
                                      ("rust", accepted_rows[1] - accepted_rows[0]))
            for record, count in sorted(differences.items())
        ],
        "schema_equal_after_approved_differences": accepted_schema_equal,
        "records_equal_after_approved_differences": accepted_rows[0] == accepted_rows[1],
        "statistics_equal_after_approved_differences": statistics_equal(normalized),
        "comparison_passed": equal,
        "schema_dump_equal": schema_equal,
        "row_and_sequence_values_equal": java_rows == rust_rows,
        "java_only_records": list((java_rows - rust_rows).elements()),
        "rust_only_records": list((rust_rows - java_rows).elements()),
        "complete_logical_equivalence_verified": False,
    }
    if exclusions is not None:
        report["rust_only_exclusions"] = exclusions
    (report_dir / "comparison.json").write_text(report_json(report) + "\n")
    (report_dir / "schema.diff").write_text("".join(difflib.unified_diff(
        java["schema"].splitlines(keepends=True), rust["schema"].splitlines(keepends=True),
        fromfile="java-schema", tofile="rust-schema",
    )))
    (report_dir / "unapproved-schema.diff").write_text("".join(difflib.unified_diff(
        normalized[0]["schema"].splitlines(keepends=True), normalized[1]["schema"].splitlines(keepends=True),
        fromfile="java-schema-after-approved-differences", tofile="rust-schema-after-approved-differences",
    )))
    if not equal and emit_report:
        print(report_json(report), flush=True)
    return equal


def diff_compare(left, right, report_dir, *, approved_differences=None):
    """Compare PostgreSQL-replayed state without recapturing user rows.

    Rebuild canonical counters only for affected relations and approval dependencies.
    """
    if not all(isinstance(state, DatabaseState) and state.healthy for state in (left, right)):
        raise ValueError("Incremental comparison requires healthy PostgreSQL change-tracked baselines")
    approved = APPROVED_STARTUP_DIFFERENCES if approved_differences is None else approved_differences
    normalized, applied = apply_approved_differences(left.snapshot(), right.snapshot(), approved)

    def group(record):
        return record.get("table") or record.get("relation") or record.get("sequence") or "__other__"

    dependencies = {"public.artifact_hit_bin", "public.artifact_hit", "public.sequence_value_item"}
    for rules in approved.values():
        if isinstance(rules, list):
            dependencies.update(rule["table"] for rule in rules if isinstance(rule, dict) and "table" in rule)
    touched = left.dirty | right.dirty | dependencies
    touched |= {json.loads(record)['sequence'] for state in (left, right) for record in state.catalog
                if 'sequence' in json.loads(record)}
    if any(not hasattr(state, "comparison_cache") or state.schema != getattr(state, "compared_schema", None)
           for state in (left, right)):
        touched |= {group(record) for snapshot in normalized for record in snapshot["records"]}
        touched |= set(getattr(left, "comparison_cache", {})) | set(getattr(right, "comparison_cache", {}))
    for state, snapshot in zip((left, right), normalized):
        cache = getattr(state, "comparison_cache", {})
        for name in touched:
            cache[name] = Counter()
        for record in snapshot["records"]:
            name = group(record)
            if name in touched:
                cache[name][json.dumps(canonical(record), ensure_ascii=True, separators=(",", ":"))] += 1
        state.comparison_cache = cache
        state.compared_schema = state.schema
    differences = []
    for name in sorted(set(left.comparison_cache) | set(right.comparison_cache)):
        java, rust = (state.comparison_cache.get(name, Counter()) for state in (left, right))
        for side, items in (("java", java - rust), ("rust", rust - java)):
            differences.extend({"relation": name, "side": side, "count": count,
                                "hex": record.encode("utf-8").hex()} for record, count in sorted(items.items()))
    schema_equal = normalized[0]["schema"] == normalized[1]["schema"]
    equal = schema_equal and not differences
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = {"mode": "postgresql-incremental", "comparison_passed": equal,
              "compared_relations": sorted(touched), "schema_equal_after_approved_differences": schema_equal,
              "unapproved_record_byte_differences": differences, "approved_differences_applied": applied,
              "transactions_replayed": {side: state.transactions for side, state in (("java", left), ("rust", right))},
              "uncommitted_state_verified": False}
    (report_dir / "comparison.json").write_text(report_json(report) + "\n")
    if not schema_equal:
        (report_dir / "unapproved-schema.diff").write_text("".join(difflib.unified_diff(
            normalized[0]["schema"].splitlines(keepends=True), normalized[1]["schema"].splitlines(keepends=True),
            fromfile="java", tofile="rust")))
    left.dirty.clear()
    right.dirty.clear()
    if not equal:
        print(report_json(report), flush=True)
    return equal


def remove_observation_triggers(schema):
    """Phase2 Change20: remove only exact generated observation trigger definitions."""
    identifier = r"[a-z_][a-z0-9_]*"
    pattern = re.compile(
        r"^--\n-- Name: (?P<table>" + identifier + r") (?P<trigger>moqui_regression_(?:row|truncate)); "
        r"Type: TRIGGER; Schema: (?P<schema>" + identifier + r"); Owner: (?:" + identifier + r"|-)\n--\n\n"
        r"(?P<statement>[^\n]+);(?:\n{1,3}|$)", re.M)

    # A matching-looking header inside a function body or SQL literal is not a dump object.
    token = re.compile(r"--[^\n]*(?:\n|$)|/\*|\b[Ee]'(?:\\.|''|[^'\\])*'|"
                       r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
                       r"(?P<tag>\$(?:[a-zA-Z_][a-zA-Z_0-9]*)?\$).*?(?P=tag)", re.S)
    protected, position = [], 0
    while found := token.search(schema, position):
        start, end = found.span()
        if found[0] == '/*':
            depth = 1
            while depth:
                boundary = re.search(r"/\*|\*/", schema[end:])
                if boundary is None:
                    end = len(schema)
                    break
                end += boundary.end()
                depth += 1 if boundary[0] == '/*' else -1
        if not found[0].startswith('--'):
            protected.append((start, end))
        position = end
    starts = [start for start, _ in protected]

    def remove(match):
        interval = bisect_right(starts, match.start()) - 1
        if interval >= 0 and match.start() < protected[interval][1]:
            return match[0]
        table = match['schema'] + '.' + match['table']
        trigger = match['trigger']
        events, level = (('INSERT OR DELETE OR UPDATE', 'ROW') if trigger.endswith('_row')
                         else ('TRUNCATE', 'STATEMENT'))
        expected = (f"CREATE TRIGGER {trigger} AFTER {events} ON {table} FOR EACH {level} "
                    "EXECUTE FUNCTION moqui_regression.row_change()")
        # Altered enable states remain application-visible even when CREATE is unchanged.
        altered_state = re.compile(r"^ALTER TABLE (?:ONLY )?" + re.escape(table)
            + r"\s+(?:ENABLE(?: REPLICA| ALWAYS)?|DISABLE) TRIGGER (?:"
            + re.escape(trigger) + r"|ALL|USER);$", re.M)
        if (match['statement'] != expected or schema.count(expected + ';') != 1
                or altered_state.search(schema)):
            return match[0]
        return ''

    return pattern.sub(remove, schema)


def capture_snapshot(container, destination, *, include_rows=True, snapshot_id=None):
    """Capture schema and committed records while application execution is paused."""
    # Phase 2, Change 13: callers may share an exported row snapshot with pg_dump.
    if snapshot_id is not None and not re.fullmatch(r"[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+", snapshot_id):
        raise ValueError("Invalid exported PostgreSQL snapshot ID")
    snapshot_options = ["--snapshot=" + snapshot_id] if snapshot_id else []
    schema = subprocess.check_output([
        "docker", "exec", container, "pg_dump", "-U", "moqui", "-d", "moqui",
        "--schema-only", "--restrict-key=MoquiRegression", "--lock-wait-timeout=5000",
        f"--exclude-schema={TRACKING_SCHEMA}",
    ] + snapshot_options, text=True, timeout=60)
    schema = remove_observation_triggers(schema)
    sql = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL timezone = 'UTC';
SET LOCAL datestyle = 'ISO, YMD';
SET LOCAL intervalstyle = 'postgres';
SET LOCAL extra_float_digits = 3;
SET LOCAL search_path = pg_catalog;
SELECT json_build_object(
  'relation', n.nspname || '.' || c.relname, 'kind', c.relkind,
  'view_definition', CASE WHEN c.relkind IN ('v', 'm') THEN pg_get_viewdef(c.oid, false) END,
  'extension', (SELECT json_build_object('name', e.extname, 'version', e.extversion)
    FROM pg_depend dep JOIN pg_extension e ON e.oid=dep.refobjid
    WHERE dep.classid='pg_class'::regclass AND dep.objid=c.oid AND dep.objsubid=0
      AND dep.refclassid='pg_extension'::regclass AND dep.deptype='e'),
  -- Phase2 Change17: capture object proof in the same row snapshot.
  'schema_objects', COALESCE((SELECT json_agg(objects.value ORDER BY objects.value->>'name', objects.value->>'kind') FROM (
    SELECT json_build_object(
      'kind', 'index', 'name', ic.relname, 'method', am.amname,
      'definition', pg_get_indexdef(i.indexrelid),
      'columns', (SELECT json_agg(a.attname ORDER BY k.ord)
        FROM unnest(i.indkey) WITH ORDINALITY k(num, ord)
        LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num),
      'key_metadata', (SELECT json_agg(json_build_object(
          'opclass', ons.nspname || '.' || op.opcname, 'collation', cn.nspname || '.' || coll.collname,
          'option', k.opt) ORDER BY k.ord)
        FROM unnest(i.indclass, i.indcollation, i.indoption) WITH ORDINALITY AS k(cls, coll, opt, ord)
        JOIN pg_opclass op ON op.oid=k.cls JOIN pg_namespace ons ON ons.oid=op.opcnamespace
        LEFT JOIN pg_collation coll ON coll.oid=k.coll LEFT JOIN pg_namespace cn ON cn.oid=coll.collnamespace),
      'key_count', i.indnkeyatts, 'attribute_count', i.indnatts,
      'unique', i.indisunique, 'primary', i.indisprimary, 'exclusion', i.indisexclusion,
      'valid', i.indisvalid, 'ready', i.indisready, 'live', i.indislive,
      'expressions', pg_get_expr(i.indexprs, i.indrelid),
      'predicate', pg_get_expr(i.indpred, i.indrelid),
      'constraint_backed', EXISTS(SELECT 1 FROM pg_constraint co WHERE co.conindid=i.indexrelid),
      'plain', NOT EXISTS(SELECT 1 FROM unnest(i.indkey, i.indclass, i.indcollation, i.indoption)
          AS k(num, cls, coll, opt)
        LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num
        LEFT JOIN pg_opclass op ON op.oid=k.cls
        LEFT JOIN pg_namespace ons ON ons.oid=op.opcnamespace
        WHERE k.num <= 0 OR k.opt IS DISTINCT FROM 0 OR op.opcdefault IS DISTINCT FROM true
          OR ons.nspname IS DISTINCT FROM 'pg_catalog' OR k.coll IS DISTINCT FROM a.attcollation),
      'options', ic.reloptions, 'owner', pg_get_userbyid(ic.relowner),
      'partition', ic.relispartition,
      'table_inherits', EXISTS(SELECT 1 FROM pg_inherits inh WHERE inh.inhrelid=c.oid OR inh.inhparent=c.oid)
    ) AS value
    FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_am am ON am.oid=ic.relam
    WHERE i.indrelid=c.oid
    UNION ALL
    SELECT json_build_object(
      'kind', 'foreign_key', 'name', co.conname, 'definition', pg_get_constraintdef(co.oid, false),
      'columns', (SELECT json_agg(a.attname ORDER BY k.ord) FROM unnest(co.conkey) WITH ORDINALITY k(num, ord)
        JOIN pg_attribute a ON a.attrelid=co.conrelid AND a.attnum=k.num),
      'target_column_types', (SELECT json_agg(format_type(a.atttypid, a.atttypmod) ORDER BY k.ord)
        FROM unnest(co.confkey) WITH ORDINALITY k(num, ord)
        JOIN pg_attribute a ON a.attrelid=co.confrelid AND a.attnum=k.num),
      'target', tn.nspname || '.' || tc.relname,
      'target_columns', (SELECT json_agg(a.attname ORDER BY k.ord) FROM unnest(co.confkey) WITH ORDINALITY k(num, ord)
        JOIN pg_attribute a ON a.attrelid=co.confrelid AND a.attnum=k.num),
      'enforced', COALESCE((to_jsonb(co)->>'conenforced')::boolean, true),
      'trigger_states', (SELECT json_agg(t.tgenabled ORDER BY t.tgenabled) FROM pg_trigger t WHERE t.tgconstraint=co.oid),
      'validated', co.convalidated, 'deferrable', co.condeferrable, 'deferred', co.condeferred,
      'match', co.confmatchtype, 'update', co.confupdtype, 'delete', co.confdeltype,
      'local', co.conislocal, 'inherited', co.coninhcount, 'parent_constraint', co.conparentid <> 0,
      'target_key_valid', ti.indisvalid, 'target_key_unique', ti.indisunique,
      'target_key_plain', ti.indexprs IS NULL AND ti.indpred IS NULL AND ti.indnkeyatts=cardinality(co.confkey),
      'target_key_definition', pg_get_indexdef(co.conindid),
      'target_kind', tc.relkind, 'target_partition', tc.relispartition,
      'table_inherits', EXISTS(SELECT 1 FROM pg_inherits inh WHERE inh.inhrelid=c.oid OR inh.inhparent=c.oid
        OR inh.inhrelid=tc.oid OR inh.inhparent=tc.oid)
    ) AS value
    FROM pg_constraint co JOIN pg_class tc ON tc.oid=co.confrelid
    JOIN pg_namespace tn ON tn.oid=tc.relnamespace JOIN pg_index ti ON ti.indexrelid=co.conindid
    WHERE co.conrelid=c.oid AND co.contype='f'
  ) objects), '[]'::json),
  'columns', (SELECT json_agg(json_build_object(
    'name', a.attname, 'type', format_type(a.atttypid, a.atttypmod),
    'not_null', a.attnotnull, 'default', pg_get_expr(d.adbin, d.adrelid)) ORDER BY a.attnum)
    FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
    WHERE a.attrelid=c.oid AND a.attnum > 0 AND NOT a.attisdropped))
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r', 'p', 'm', 'v', 'f') AND n.nspname !~ '^pg_'
  AND n.nspname NOT IN ('information_schema', 'moqui_regression')
ORDER BY n.nspname, c.relname;
SELECT format(
  'SELECT json_build_object(''table'', %L, ''row'', row_to_json(t)) FROM ONLY %I.%I t',
  n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm') AND n.nspname !~ '^pg_'
  AND n.nspname NOT IN ('information_schema', 'moqui_regression')
  AND __INCLUDE_ROWS__
ORDER BY n.nspname, c.relname
\gexec
SELECT format(
  'SELECT json_build_object(''sequence'', %L, ''state'', row_to_json(t)) FROM (SELECT * FROM %I.%I) t',
  n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S' AND n.nspname !~ '^pg_'
  AND n.nspname NOT IN ('information_schema', 'moqui_regression')
ORDER BY n.nspname, c.relname
\gexec
COMMIT;
"""
    if snapshot_id:
        sql = sql.replace("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;",
            "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSET TRANSACTION SNAPSHOT '" + snapshot_id + "';", 1)
    records = subprocess.check_output([
        "docker", "exec", "-i", container, "psql", "-X", "-qAt",
        "--set", "ON_ERROR_STOP=1", "-U", "moqui", "-d", "moqui",
    ], input=sql.replace('__INCLUDE_ROWS__', 'true' if include_rows else 'false'), text=True, timeout=60).splitlines()
    destination.touch(mode=0o600)
    destination.write_text(json.dumps({"schema": schema, "records": records}, indent=2) + "\n")


CDC_SLOT = "moqui_regression_cdc"


def approval_snapshots(states, containers, evidence):
    """Approval validators need current DDL metadata, just like paired comparisons."""
    for side, state in states.items():
        if state.schema_dirty:
            refresh_incremental_catalog(containers[side], state, evidence / f"{side}-catalog.json")
    return [states[side].snapshot() for side in ("java", "rust")]


def approved_statistics_change(event, kind, snapshots, approved):
    """Exempt only extra bins validated by the existing snapshot approvals."""
    row = event.get("new", {})
    if (kind not in ("seed_statistics", "rust_only_statistics") or event.get("kind") != "insert"
            or event.get("table") != "public.artifact_hit_bin"
            or not isinstance(row, dict) or row.get("artifact_type") != "AT_ENTITY"):
        return False
    captured = snapshots()
    _, applied = apply_approved_differences(*captured, approved)
    if kind == "rust_only_statistics":
        bins = [json.loads(record, parse_int=Decimal, parse_float=Decimal)["row"]
                for record in captured[1]["records"]
                if json.loads(record).get("table") == "public.artifact_hit_bin"]
        if [item for item in bins if item.get("hit_bin_id") == row.get("hit_bin_id")] != [row]:
            return False
        return any(rule["kind"] == kind and any(
            all(row.get(field) == value for field, value in item.items()) for item in rule["rows"])
            for rule in applied)
    return any(rule["kind"] == kind and rule["java_hit_count"] == 0
               and rule["artifact_name"] == row.get("artifact_name")
               and rule["artifact_sub_type"] == row.get("artifact_sub_type")
               and rule["rust_hit_count"] == row.get("hit_count") for rule in applied)


def create_cdc_slot(container):
    """Start logical decoding before either engine connects, so every committed change is captured."""
    subprocess.run(["docker", "exec", "-i", container, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                    "-U", "moqui", "-d", "moqui"], input=INSTALL_SQL, text=True,
                   check=True, stdout=subprocess.DEVNULL, timeout=60)
    subprocess.run(["docker", "exec", container, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                    "-U", "moqui", "-d", "moqui", "-c",
                    f"SELECT pg_create_logical_replication_slot('{CDC_SLOT}', 'test_decoding')"],
                   check=True, stdout=subprocess.DEVNULL, timeout=60)


def read_cdc(container, *, with_cursor=False):
    """Consume committed transactions since the last read: one list of change lines per transaction.

    A transaction with an assigned xid is always reported, including DDL-only ones (empty list);
    reads and rollbacks never appear.
    """
    select = "json_build_object('lsn', lsn, 'data', data)::text" if with_cursor else 'data'
    query = (f"SELECT {select} FROM pg_logical_slot_get_changes('{CDC_SLOT}', NULL, NULL, "
             "'include-xids', '0', 'skip-empty-xacts', '0');")
    if with_cursor:
        def marker(phase):
            return (f"SELECT json_build_object('phase','{phase}','lsn',confirmed_flush_lsn,'plugin',plugin,"
                    f"'database',database,'wal_status',wal_status)::text FROM pg_replication_slots "
                    f"WHERE slot_name='{CDC_SLOT}';")
        query = marker('before') + query + marker('after')
    output = subprocess.run(
        ["docker", "exec", container, "psql", "-X", "-qAt", "-0", "-v", "ON_ERROR_STOP=1",
         "-U", "moqui", "-d", "moqui", "-c", query],
        check=True, capture_output=True, text=True, timeout=60).stdout
    transactions, current = [], None
    cursor = {}
    for row in output.removesuffix("\n").split("\0"):
        if not row:
            continue
        if with_cursor:
            envelope = json.loads(row)
            if 'phase' in envelope:
                if (envelope['plugin'] != 'test_decoding' or envelope['database'] != 'moqui'
                        or envelope['wal_status'] not in ('reserved', 'extended') or not envelope['lsn']):
                    raise RuntimeError('PostgreSQL logical slot is missing, invalid, or has lost WAL')
                cursor[envelope['phase']] = envelope['lsn']
                continue
            cursor['last_event'] = envelope['lsn']
            row = envelope['data']
        if row == "BEGIN":
            if current is not None:
                raise RuntimeError("Nested PostgreSQL decoding transaction")
            current = []
        elif row == "COMMIT":
            if current is None:
                raise RuntimeError("PostgreSQL COMMIT without BEGIN")
            transactions.append(current)
            current = None
        elif current is not None:
            current.append(row)
        else:
            raise RuntimeError(f"Change data outside a transaction: {row[:200]}")
    if current is not None:
        raise RuntimeError("Change data ended inside a transaction")
    if with_cursor and not {'before', 'after'} <= cursor.keys():
        raise RuntimeError('PostgreSQL logical slot disappeared during capture')
    return (transactions, cursor) if with_cursor else transactions


def refresh_incremental_catalog(container, state, destination):
    """A capture/catalog failure invalidates the replayed baseline."""
    try:
        _refresh_incremental_catalog(container, state, destination)
    except Exception:
        state.healthy = False
        raise


def _refresh_incremental_catalog(container, state, destination):
    """Refresh DDL metadata only when it changed; sequences are checked at every barrier."""
    integrity = r"""
DO $$ BEGIN
  IF (SELECT count(*) FROM pg_event_trigger
      WHERE evtenabled='O' AND evttags IS NULL AND (
        (evtname='moqui_regression_ddl' AND evtevent='ddl_command_end'
         AND evtfoid='moqui_regression.schema_change'::regproc) OR
        (evtname='moqui_regression_drop' AND evtevent='sql_drop'
         AND evtfoid='moqui_regression.schema_drop'::regproc))) <> 2
  THEN RAISE EXCEPTION 'Incremental DDL observation trigger missing or disabled'; END IF;
  IF EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE c.relkind IN ('r','p') AND n.nspname !~ '^pg_'
      AND n.nspname NOT IN ('information_schema','moqui_regression')
      AND (SELECT count(*) FROM pg_trigger t WHERE t.tgrelid=c.oid
           -- Phase2 Change20: matching names alone cannot prove complete observation.
           AND ((t.tgname='moqui_regression_row' AND t.tgtype=29)
             OR (t.tgname='moqui_regression_truncate' AND t.tgtype=32))
           AND t.tgenabled='O' AND t.tgfoid='moqui_regression.row_change'::regproc
           AND t.tgqual IS NULL AND t.tgnargs=0 AND t.tgattr=''::int2vector
           AND octet_length(t.tgargs)=0 AND t.tgconstraint=0 AND NOT t.tgisinternal
           AND NOT t.tgdeferrable AND NOT t.tginitdeferred) <> 2)
  THEN RAISE EXCEPTION 'Incremental observation trigger missing or disabled'; END IF;
END $$;
"""
    subprocess.run(['docker', 'exec', '-i', container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
                    '-U', 'moqui', '-d', 'moqui'], input=integrity, text=True, timeout=60, check=True,
                   stdout=subprocess.DEVNULL)
    if state.schema_dirty:
        capture_snapshot(container, destination, include_rows=False)

        catalog = json.loads(destination.read_text())
        readback = catalog_row_readback(container, state, catalog)
        state.refresh_catalog(catalog, reload_rows=readback.__getitem__)
    else:
        sql = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '10s';
SELECT format('SELECT json_build_object(''sequence'', %L, ''state'', row_to_json(t)) FROM (SELECT * FROM %I.%I) t',
              n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind='S' AND n.nspname !~ '^pg_' AND n.nspname NOT IN ('information_schema','moqui_regression')
ORDER BY n.nspname,c.relname
\gexec
COMMIT;
"""
        sequences = subprocess.check_output(
            ['docker', 'exec', '-i', container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
             '-U', 'moqui', '-d', 'moqui'], input=sql, text=True, timeout=60).splitlines()
        old = [record for record in state.catalog if 'sequence' in json.loads(record)]
        if old != sequences:
            state.dirty.update(json.loads(record)['sequence'] for record in old + sequences)
        state.catalog = [record for record in state.catalog if 'sequence' not in json.loads(record)] + sequences


def catalog_row_readback(container, state, catalog):
    """Read DDL-affected rows in one PostgreSQL snapshot, not one process per table."""
    old_columns = {item['relation']: item.get('columns') for item in map(json.loads, state.catalog)
                   if 'relation' in item}
    tables = sorted(item['relation'] for item in map(json.loads, catalog['records'])
                    if 'relation' in item and (item['relation'] in state.readback or (
                        state.rows.get(item['relation']) and item['relation'] in old_columns
                        and old_columns[item['relation']] != item.get('columns'))))
    rows = {table: [] for table in tables}
    if not tables:
        return rows
    statements = ["BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;",
                  "SET LOCAL statement_timeout='10s'; SET LOCAL timezone='UTC';"]
    for table in tables:
        identifier = '.'.join('"' + part.replace('"', '""') + '"' for part in table.split('.', 1))
        statements.append("SELECT json_build_object('table', '" + table.replace("'", "''")
                          + "', 'row', row_to_json(t)) FROM ONLY " + identifier + " t;")
    statements.append('COMMIT;')
    output = subprocess.check_output(
        ['docker', 'exec', '-i', container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
         '-U', 'moqui', '-d', 'moqui'], input='\n'.join(statements), text=True, timeout=60)
    for record in output.splitlines():
        rows[json.loads(record)['table']].append(record)
    return rows


def boot_and_stop(args, *, evidence_dir=None, readiness_check=None):
    # Reject occupied HTTP ports so another application's listener cannot pass readiness.
    for port in (args.java_port, args.rust_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S.%fZ")
    # Change 5: Boot-only validation supplies its evidence path and HTTP readiness check.
    evidence = Path(evidence_dir) if evidence_dir is not None else ROOT / ".runs" / run_id
    evidence.mkdir(parents=True, mode=0o700)
    print(f"Startup evidence: {evidence}", flush=True)
    approved = getattr(args, "approved_differences", APPROVED_STARTUP_DIFFERENCES)
    (evidence / "approved-differences.json").write_text(json.dumps(approved, indent=2) + "\n")
    manifest = ROOT / ".runs/build.json"
    if manifest.exists():
        (evidence / "build.json").write_bytes(manifest.read_bytes())
    containers, processes, logs = {}, {}, []
    directories = engine_directories(args)
    coordinator = None
    hook_url = None
    verification = {"deterministic_requested": bool(getattr(args, "deterministic", False)),
                    "servers_started": False, "shutdown_verified": False,
                    "final_databases_equal": None, "passed": False,
                    "approved_differences_sha256": hashlib.sha256(
                        (evidence / "approved-differences.json").read_bytes()).hexdigest()}
    started = False
    password = secrets.token_hex(24)
    crypt_pass = secrets.token_hex(32)
    environment = os.environ.copy()
    if args.java_home:
        environment["JAVA_HOME"] = str(Path(args.java_home).resolve())
        environment["PATH"] = str(Path(args.java_home).resolve() / "bin") + os.pathsep + environment.get("PATH", "")
    # This is infrastructure entropy, not an application deterministic-input source.
    container_environment = {**os.environ, "POSTGRES_PASSWORD": password}
    ports = {"java": args.java_port, "rust": args.rust_port}
    try:
        # One fresh, storage-isolated container per engine; never reset an existing DB.
        for name, checkout in zip(("java", "rust"), REPOSITORIES):
            container = f"moqui-regression-{run_id}-{name}"
            containers[name] = container
            subprocess.run([
                "docker", "run", "--detach", "--rm", "--name", container,
                "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql",
                "--env", "POSTGRES_USER=moqui", "--env", "POSTGRES_DB=moqui",
                "--env", "POSTGRES_PASSWORD", "--env", "TZ=UTC",
                POSTGRES_IMAGE, "-c", "timezone=UTC", "-c", "max_prepared_transactions=100",
                "-c", "wal_level=logical", "-c", "max_replication_slots=4",
                # Autoanalyze commits catalog-only transactions at arbitrary points in the CDC stream.
                "-c", "autovacuum=off",
            ], env=container_environment, check=True, stdout=subprocess.DEVNULL)
            mapping = subprocess.check_output(
                ["docker", "port", container, "5432/tcp"], text=True
            ).strip()
            db_port = int(mapping.rsplit(":", 1)[1])
            deadline = time.monotonic() + args.boot_timeout
            while subprocess.run(
                ["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "moqui", "-d", "moqui"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"{name} PostgreSQL did not become ready")
                time.sleep(0.2)
            image_id = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.Image}}", container], text=True
            ).strip()
            (evidence / f"{name}-postgres-image.txt").write_text(image_id + "\n")
            table_count = subprocess.check_output([
                "docker", "exec", container, "psql", "-U", "moqui", "-d", "moqui", "-Atc",
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','S','v','m','f')",
            ], text=True).strip()
            if table_count != "0":
                raise RuntimeError(f"{name} database is not empty")
            if getattr(args, "deterministic", False):
                create_cdc_slot(container)
            runtime = directories[name] / "runtime"
            conf = evidence / f"{name}-demo.xml"
            demo_conf(runtime / "conf/MoquiDevConf.xml", conf, db_port, password, ports[name], crypt_pass)

        if (evidence / "java-postgres-image.txt").read_bytes() != (evidence / "rust-postgres-image.txt").read_bytes():
            raise RuntimeError("PostgreSQL containers resolved to different image IDs")

        # Java needs the PostgreSQL JDBC driver in its private runtime.
        driver = directories["java"] / "runtime/lib/postgresql-42.7.7.jar"
        if not driver.exists():
            driver.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(
                "https://repo.maven.apache.org/maven2/org/postgresql/postgresql/42.7.7/postgresql-42.7.7.jar",
                timeout=60,
            ) as response:
                payload = response.read()
            driver.write_bytes(payload)

        if getattr(args, "deterministic", False):
            states = {}
            for side, container in containers.items():
                baseline = evidence / f"{side}-baseline.json"
                capture_snapshot(container, baseline)
                states[side] = DatabaseState(json.loads(baseline.read_text()))
                initial_changes, cursor = read_cdc(container, with_cursor=True)
                if initial_changes:
                    raise RuntimeError('Database changed while establishing the incremental baseline')
                states[side].capture_cursor = cursor['after']
            if not diff_compare(states['java'], states['rust'], evidence / 'baseline-comparison',
                                approved_differences=approved):
                raise RuntimeError("Initial incremental baselines differ")

            def changes(side):
                transactions, cursor = read_cdc(containers[side], with_cursor=True)
                # Persist consumed PostgreSQL evidence before replay. A failed run
                # is never resumed with an already-advanced logical slot.
                with (evidence / f"{side}-changes.jsonl").open('a') as journal:
                    journal.write(json.dumps({'cursor': cursor, 'transactions': transactions}) + '\n')
                    journal.flush()
                    os.fsync(journal.fileno())
                state = states[side]
                previous = getattr(state, 'capture_cursor', None)
                if previous is not None and cursor['before'] != previous:
                    state.healthy = False
                    raise RuntimeError(f'{side} PostgreSQL capture cursor changed outside the controller')
                state.apply(transactions)
                state.capture_cursor = cursor['after']
                return transactions

            def compare_transaction(write_id):
                step = evidence / "transactions" / write_id
                for side, state in states.items():
                    refresh_incremental_catalog(containers[side], state, evidence / f"{side}-catalog.json")
                return diff_compare(states['java'], states['rust'], step, approved_differences=approved)

            def approved_difference(event, kind):
                return approved_statistics_change(event, kind,
                    lambda: approval_snapshots(states, containers, evidence), approved)

            coordinator = DeterministicCoordinator(run_id, evidence, compare=compare_transaction,
                                                   cdc=changes,
                                                   exempt=ApprovalEngine(approved, approved_difference).exempt_transaction,
                                                   operation_checks=False, timeout=args.boot_timeout)
            hook_url = coordinator.start()

        for name, checkout in zip(("java", "rust"), REPOSITORIES):
            directory = directories[name]
            runtime = directory / "runtime"
            conf = evidence / f"{name}-demo.xml"
            # Phase 1, Change 4: the boot gate supplies immutable, checksum-bound launch copies.
            frozen = getattr(args, "boot_artifacts", {})
            artifact = Path(frozen.get(name, directory / "moqui.war" if name == "java" else rust_artifact(directory)))
            if name in frozen:
                with artifact.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != getattr(args, 'expected_artifact_sha256', {}).get(name):
                    raise RuntimeError(f'{name} launch artifact differs from verified copy')
            if name == "java":
                command = ["java", f"-Dmoqui.runtime={runtime}", f"-Dmoqui.conf={conf}",
                           "-jar", str(artifact), f"port={ports[name]}", "no-run-es"]
            else:
                command = [str(artifact), "--conf", str(conf),
                           "--port", str(ports[name]), "--https-port", "off", "--no-run-es",
                           "-D", "create-or-update=true"]
            log = (evidence / f"{name}-boot.log").open("wb")
            logs.append(log)
            overrides = {node.get("name"): node.get("value")
                         for node in ET.parse(conf).getroot().findall("default-property")}
            deterministic_env = ({
                "MOQUI_DETERMINISTIC": "true", "MOQUI_DETERMINISTIC_HOOK": hook_url,
                "MOQUI_DETERMINISTIC_OPERATIONS": "false",
                "MOQUI_DETERMINISTIC_ENGINE": name, "MOQUI_DETERMINISTIC_RUN": run_id,
                "MOQUI_DETERMINISTIC_LOG": str(evidence / f"{name}-deterministic.log"),
            } if coordinator else {})
            processes[name] = subprocess.Popen(
                command, cwd=directory, env={**environment, **overrides, **deterministic_env, "MOQUI_RUNTIME": str(runtime),
                    "MOQUI_CONF": str(conf), "MOQUI_FRAMEWORK": str(runtime / "base-component/framework"), "TZ": "UTC"},
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
        wait_for_ports(processes, ports, args.boot_timeout,
                       {name: evidence / f"{name}-boot.log" for name in processes},
                       failure_check=coordinator.check_health if coordinator else None)
        if readiness_check is not None:
            readiness_check(ports)
        started = True
        verification["servers_started"] = True
        print("Both engines started; stopping both processes.", flush=True)
    finally:
        shutdown = stop_engines(processes, {name: evidence / f"{name}-boot.log" for name in processes},
                                args.shutdown_timeout)
        for log in logs:
            log.close()
        if coordinator:
            coordinator.close()
            verification["deterministic"] = {key: value for key, value in coordinator.report().items()
                                             if key != "pairs"}
        verification["shutdown_verified"] = started and all(not item["errors"] for item in shutdown.values())
        (evidence / "shutdown.json").write_text(json.dumps(shutdown, indent=2) + "\n")
        try:
            if coordinator and not started:
                # Failed startup is evidence, not a parity pass. Retain stopped DB state too.
                for name, container in containers.items():
                    try:
                        capture_snapshot(container, evidence / f"{name}-snapshot.json")
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        print(f"Could not capture failed-startup database for {name}", flush=True)
            if started:
                if coordinator and not coordinator.report()["per_transaction_databases_equal"]:
                    raise RuntimeError(f"Deterministic verification failed; inspect {evidence / 'deterministic-report.json'}")
                if any(result["errors"] for result in shutdown.values()):
                    raise RuntimeError(f"Graceful shutdown verification failed; inspect {evidence / 'shutdown.json'}")
                print("Both engines shut down gracefully with verified completion evidence.", flush=True)
                # Step 4: Snapshot and compare only after verified graceful shutdown.
                for name, container in containers.items():
                    capture_snapshot(container, evidence / f"{name}-snapshot.json")
                verification["final_databases_equal"] = snapshot_compare(
                    evidence / "java-snapshot.json", evidence / "rust-snapshot.json", evidence,
                    rust_only_manifest=(RUST_ONLY_SOURCES if args.exclude_rust_only else None),
                    source_root=args.source_root, approved_differences=approved)
                if not verification["final_databases_equal"]:
                    raise SystemExit(f"Startup snapshots differ; inspect {evidence / 'comparison.json'}")
                verification["passed"] = True
                print("Startup snapshots match after approved differences (not a complete logical-equivalence proof).", flush=True)
        finally:
            (evidence / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
            for name, container in containers.items():
                with (evidence / f"{name}-postgres.log").open("wb") as log:
                    subprocess.run(["docker", "logs", container], stdout=log, stderr=subprocess.STDOUT)
                if args.keep_databases:
                    print(f"Connect to {name}: docker exec -it {container} psql -U moqui -d moqui", flush=True)
                    print(f"Remove when finished: docker rm -f -v {container}", flush=True)
                else:
                    subprocess.run(["docker", "rm", "--force", "--volumes", container], stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", help="JDK home for the Java build (Java 21 recommended)")
    parser.add_argument("--java-checkout", type=Path, help="Use an existing private Java worktree (not reset)")
    parser.add_argument("--rust-checkout", type=Path, help="Use an existing private Rust worktree (not reset)")
    parser.add_argument("--deterministic", action="store_true",
                        help="Pair transaction hooks and compare committed databases after every transaction")
    parser.add_argument("--differences", type=Path, default=ROOT / "approved-differences.json",
                        help="Reviewed differences JSON; copied into the run evidence")
    parser.add_argument("--java-port", type=int, default=8080)
    parser.add_argument("--rust-port", type=int, default=8081)
    parser.add_argument("--boot-timeout", type=float, default=600)
    parser.add_argument("--shutdown-timeout", type=float, default=120,
                        help="Seconds allowed for graceful shutdown and statistics flush (default: 120)")
    parser.add_argument("--keep-databases", action="store_true",
                        help="Keep PostgreSQL containers after application shutdown for inspection")
    parser.add_argument("--exclude-rust-only", action="store_true",
                        help="Exclude manifest-classified Rust only rows during comparison, not capture")
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="Parent of mr-moqui source checkout for Rust only source attribution")
    args = parser.parse_args()
    args.approved_differences = json.loads(args.differences.read_text())
    if not isinstance(args.approved_differences, dict) or not all(
            key in args.approved_differences for key in ("theme_resources", "full_text_indexes")):
        parser.error("--differences must contain theme_resources and full_text_indexes rules")
    if args.java_port == args.rust_port or not all(1 <= p <= 65535 for p in (args.java_port, args.rust_port)):
        parser.error("Java and Rust need distinct valid HTTP ports")
    if args.boot_timeout <= 0 or args.shutdown_timeout <= 0:
        parser.error("--boot-timeout and --shutdown-timeout must be positive")

    # Step 1: Initialize the pinned framework submodules and Java's private runtime.
    defaults = [checkout for name, checkout in zip(("java", "rust"), REPOSITORIES)
                if getattr(args, f"{name}_checkout") is None]
    if defaults:
        git("-C", ROOT, "submodule", "update", "--init", "--recursive", "--", *defaults)

    directories = engine_directories(args)
    for directory in (*directories.values(), directories["java"] / "runtime"):
        revision = subprocess.check_output(
            ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True
        ).strip()
        print(f"{directory}: {revision}", flush=True)
    # Step 2: Build Java's moqui.war and Rust's executable with separate runtimes.
    build_engines(args.java_home, directories)

    # Step 3: Start both engines, wait for HTTP ports, then stop both processes.
    boot_and_stop(args)


if __name__ == "__main__":
    (ROOT / ".runs").mkdir(exist_ok=True)
    with (ROOT / ".runs/run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another regression run is already active")
        main()
