"""Exact, user-approved exceptions. Raw snapshots are never modified."""

from collections import Counter
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
import re


def apply_approved_differences(java, rust, approved):
    snapshots = [
        {"schema": snapshot["schema"], "records": [
            json.loads(record, parse_int=Decimal, parse_float=Decimal)
            for record in snapshot["records"]]}
        for snapshot in (java, rust)
    ]
    applied = []
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
    applied.extend(apply_java_restart(snapshots, approved.get("java_restart")))
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
        # Both approved index definitions and the generated column must exist before accepting either.
        snapshots[0]["schema"] = table_pattern.sub(
            lambda m: m.group(1) + ",\n".join(c for c in m.group(2).split(",\n") if c != declaration)
            + m.group(3), snapshots[0]["schema"], count=1)
        for snapshot, block in zip(snapshots, index_blocks):
            snapshot["schema"] = snapshot["schema"].replace(block, "", 1)
        metadata[0]["columns"].remove(expected_metadata)
        for item in snapshots[0]["records"]:
            if item.get("table") == table:
                item["row"].pop(column, None)
        applied.append({"kind": "full_text_storage", **deepcopy(rule)})
    return snapshots, applied


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
    no bin of these sub types, and Rust gives them the ids after every bin Java also has, so no other id moves."""
    if not rule:
        return []
    sub_types = set(rule["artifact_sub_types"])
    if any(item["row"].get("artifact_sub_type") in sub_types for item in bin_rows(snapshots[0])):
        return []
    rust_only = [item for item in bin_rows(snapshots[1]) if item["row"].get("artifact_sub_type") in sub_types]
    others = [int(item["row"]["hit_bin_id"]) for item in bin_rows(snapshots[1]) if item not in rust_only]
    if not rust_only or (others and min(int(item["row"]["hit_bin_id"]) for item in rust_only) < max(others)):
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


def apply_java_restart(snapshots, rule):
    """Java restarts its factory after the empty-database load; Rust does not. The second Java factory starts
    with no counts and a fresh hit bin id bank, so its bins are written after an id gap. Only the exact
    approved bins, after a gap, are set aside; then the ArtifactHitBin sequence
    row may be exactly one bank ahead of Rust's."""
    if not rule:
        return []
    identity = ("artifact_type", "artifact_sub_type", "artifact_name", "hit_count")
    java = sorted(bin_rows(snapshots[0]), key=lambda item: int(item["row"]["hit_bin_id"]))
    expected = rule["post_restart_bins"]
    if len(java) <= len(expected):
        return []
    before, after = java[:-len(expected)], java[-len(expected):]
    found = [{field: (int(item["row"][field]) if field == "hit_count" else item["row"][field])
              for field in identity} for item in after]
    if (sorted(found, key=repr) != sorted(expected, key=repr)
            or int(after[0]["row"]["hit_bin_id"]) <= int(before[-1]["row"]["hit_bin_id"]) + 1):
        return []
    for item in after:
        snapshots[0]["records"].remove(item)
    applied = [{"kind": "java_restart_bins", "rows": found}]
    sequence = rule.get("sequence")
    if sequence:
        rows = [[item for item in snapshot["records"] if item.get("table") == "public.sequence_value_item"
                 and item["row"].get("seq_name") == sequence["seq_name"]] for snapshot in snapshots]
        if all(len(side) == 1 for side in rows):
            java_num, rust_num = (int(side[0]["row"]["seq_num"]) for side in rows)
            if java_num - rust_num == sequence["java_ahead_by"]:
                rows[0][0]["row"]["seq_num"] = rows[1][0]["row"]["seq_num"]
                applied.append({"kind": "java_restart_sequence", "seq_name": sequence["seq_name"],
                                "java_seq_num": java_num, "rust_seq_num": rust_num})
    return applied
