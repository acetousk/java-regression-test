"""Opt-in exclusions on raw snapshots; no database, schema, or file mutation."""

from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


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


def filter_snapshots(java, rust, manifest_path, source_root):
    """Return copies plus an exact audit. Only Rust rows can be excluded."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("version") != 1 or manifest.get("classification") != "Rust only":
        raise ValueError("Unsupported Rust only manifest")
    seeds, hashes = source_records(manifest, source_root)
    operational = {entry["table"]: entry for entry in manifest["operational"]}
    parsed = [[json.loads(record, parse_float=Decimal) for record in snapshot["records"]]
              for snapshot in (java, rust)]
    audit = {"classification": "Rust only", "manifest": str(manifest_path.resolve()),
             "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
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
