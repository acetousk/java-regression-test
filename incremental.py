"""Replay PostgreSQL-origin change events; never trust application-reported write sets."""
from collections import Counter
from decimal import Decimal
import json
import re


TRACKING_SCHEMA = "moqui_regression"
EVENT_PREFIX = f"table {TRACKING_SCHEMA}.events: INSERT: payload[text]:"

# Installed before creating the logical slot. The queue is WAL-logged and transactional:
# rollback removes its events as well as the original writes. Logical decoding supplies
# transaction boundaries and commit order. JSON text preserves PostgreSQL numeric values.
INSTALL_SQL = r"""
CREATE SCHEMA moqui_regression;
CREATE TABLE moqui_regression.events (payload text NOT NULL);
CREATE FUNCTION moqui_regression.row_change() RETURNS trigger LANGUAGE plpgsql
SET timezone = 'UTC' SET datestyle = 'ISO, YMD' SET intervalstyle = 'postgres'
SET extra_float_digits = '3' SET bytea_output = 'hex' AS $$
BEGIN
  IF TG_OP = 'TRUNCATE' THEN
    INSERT INTO moqui_regression.events VALUES (json_build_object(
      'kind', 'truncate', 'table', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME)::text);
    RETURN NULL;
  END IF;
  INSERT INTO moqui_regression.events VALUES (json_build_object(
    'kind', lower(TG_OP), 'table', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
    'old', CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN row_to_json(OLD)::text END,
    'new', CASE WHEN TG_OP IN ('UPDATE', 'INSERT') THEN row_to_json(NEW)::text END)::text);
  RETURN NULL;
END $$;
CREATE FUNCTION moqui_regression.attach_triggers() RETURNS void LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  FOR r IN SELECT c.oid, n.nspname, c.relname FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.relkind IN ('r', 'p') AND n.nspname !~ '^pg_'
        AND n.nspname NOT IN ('information_schema', 'moqui_regression')
  LOOP
    IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = r.oid AND tgname = 'moqui_regression_row') THEN
      EXECUTE format('CREATE TRIGGER moqui_regression_row AFTER INSERT OR UPDATE OR DELETE ON %I.%I '
                     'FOR EACH ROW EXECUTE FUNCTION moqui_regression.row_change()', r.nspname, r.relname);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = r.oid AND tgname = 'moqui_regression_truncate') THEN
      EXECUTE format('CREATE TRIGGER moqui_regression_truncate AFTER TRUNCATE ON %I.%I '
                     'FOR EACH STATEMENT EXECUTE FUNCTION moqui_regression.row_change()', r.nspname, r.relname);
    END IF;
  END LOOP;
END $$;
CREATE FUNCTION moqui_regression.schema_change() RETURNS event_trigger LANGUAGE plpgsql AS $$
DECLARE affected_tables json; table_only boolean;
BEGIN
  -- Do not recurse when attaching the observation triggers themselves.
  IF TG_TAG = 'CREATE TRIGGER' THEN RETURN; END IF;
  SELECT json_agg(DISTINCT n.nspname || '.' || t.relname),
         coalesce(bool_and(coalesce(c.relkind IN ('r','p','i','I') AND t.relkind IN ('r','p')
           AND n.nspname !~ '^pg_' AND n.nspname NOT IN ('information_schema','moqui_regression'), false)), true)
    INTO affected_tables, table_only
    FROM pg_event_trigger_ddl_commands() d
    LEFT JOIN pg_class c ON d.classid='pg_class'::regclass AND d.objid=c.oid
    LEFT JOIN pg_index i ON i.indexrelid=c.oid
    LEFT JOIN pg_class t ON t.oid=coalesce(i.indrelid,c.oid)
    LEFT JOIN pg_namespace n ON n.oid=t.relnamespace;
  INSERT INTO moqui_regression.events VALUES (json_build_object('kind', 'schema', 'tag', TG_TAG,
    'tables', affected_tables, 'table_only', table_only,
    'readback', CASE WHEN TG_TAG IN ('ALTER TABLE', 'CREATE TABLE AS', 'SELECT INTO') THEN
      (SELECT json_agg(DISTINCT n.nspname || '.' || c.relname)
       FROM pg_event_trigger_ddl_commands() d JOIN pg_class c ON d.objid=c.oid AND d.classid='pg_class'::regclass
       JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE c.relkind IN ('r','p') AND n.nspname !~ '^pg_'
         AND n.nspname NOT IN ('information_schema','moqui_regression')) END)::text);
  PERFORM moqui_regression.attach_triggers();
END $$;
CREATE FUNCTION moqui_regression.schema_drop() RETURNS event_trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO moqui_regression.events VALUES (json_build_object('kind', 'schema', 'tag', 'DROP',
    'dropped', (SELECT json_agg(schema_name || '.' || object_name) FROM pg_event_trigger_dropped_objects()
                WHERE object_type IN ('table','partitioned table') AND schema_name <> 'moqui_regression'))::text);
END $$;
CREATE EVENT TRIGGER moqui_regression_ddl ON ddl_command_end EXECUTE FUNCTION moqui_regression.schema_change();
CREATE EVENT TRIGGER moqui_regression_drop ON sql_drop EXECUTE FUNCTION moqui_regression.schema_drop();
"""


def typed(value):
    if isinstance(value, dict):
        return ["object", [[key, typed(item)] for key, item in sorted(value.items())]]
    if isinstance(value, list):
        return ["array", [typed(item) for item in value]]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite numeric change")
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return ["number", "0" if value == 0 else text]
    return [type(value).__name__, value]


def key(record):
    return json.dumps(typed(json.loads(record, parse_int=Decimal, parse_float=Decimal)), separators=(",", ":"))


def events(transaction):
    """Decode only our PostgreSQL trigger events; verify ordinary row changes are covered.

    Raw application changes are retained in the journal too, but are not parsed as
    authoritative rows (test_decoding omits unchanged TOAST values and old full rows).
    """
    result, raw_counts, captured_counts = [], Counter(), Counter()
    for line in transaction:
        if line.startswith(EVENT_PREFIX):
            literal = line[len(EVENT_PREFIX):]
            if not re.fullmatch(r"'(?:[^']|'')*'", literal, re.DOTALL):
                raise ValueError("Malformed PostgreSQL change event")
            event = json.loads(literal[1:-1].replace("''", "'"))
            if not isinstance(event, dict) or event.get("kind") not in ("insert", "update", "delete", "truncate", "schema"):
                raise ValueError("Unknown PostgreSQL change event")
            result.append(event)
            if event["kind"] != "schema":
                captured_counts[(event["table"], event["kind"])] += 1
        elif line.startswith("table "):
            head, separator, rest = line.partition(": ")
            table = head[6:]
            # Canonical qualified names are deliberately bounded for the first adapter.
            # Refuse quoted identifiers rather than silently omit their changes.
            if not re.fullmatch(r"[a-z_][a-z_0-9]*\.[a-z_][a-z_0-9]*", table):
                raise ValueError("Unsupported CDC relation identifier")
            kind = rest.partition(":")[0].lower()
            if not separator or kind not in ("insert", "update", "delete", "truncate"):
                raise ValueError("Unsupported PostgreSQL row change")
            raw_counts[(table, kind)] += 1
        else:
            raise ValueError("Unknown PostgreSQL logical decoding message")
    readback = {table for event in result if event['kind'] == 'schema' for table in event.get('readback', ()) or ()}
    raw_counts = Counter({item: count for item, count in raw_counts.items() if item[0] not in readback})
    captured_counts = Counter({item: count for item, count in captured_counts.items() if item[0] not in readback})
    if raw_counts != captured_counts:
        raise ValueError(f"PostgreSQL change capture coverage mismatch: raw={raw_counts}, captured={captured_counts}")
    return result


class DatabaseState:
    """An exact row multiset initialized once, then updated exclusively from PostgreSQL CDC."""
    def __init__(self, baseline):
        self.schema = baseline["schema"]
        self.catalog = []
        self.rows = {}
        self.dirty = set()
        self.schema_dirty = False
        self.readback = set()
        self.transactions = 0
        self.healthy = True
        for record in baseline["records"]:
            item = json.loads(record)
            if "table" in item:
                self._add(item["table"], record)
            else:
                self.catalog.append(record)

    def _add(self, table, record):
        identity = key(record)
        stored = self.rows.setdefault(table, {})
        previous, count = stored.get(identity, (record, 0))
        stored[identity] = (previous, count + 1)

    def _remove(self, table, record):
        identity = key(record)
        stored = self.rows.get(table, {})
        if identity not in stored:
            raise ValueError(f"CDC old row missing from verified state: {table}")
        previous, count = stored[identity]
        if count == 1:
            del stored[identity]
        else:
            stored[identity] = (previous, count - 1)

    def apply(self, transactions):
        if not self.healthy:
            raise ValueError("Incremental state is poisoned; restart from a verified baseline")
        try:
            for transaction in transactions:
                for event in events(transaction):
                    kind = event["kind"]
                    if kind == "schema":
                        self.schema_dirty = True
                        self.readback.update(event.get('readback', ()) or ())
                        for table in event.get('dropped', ()) or ():
                            self.rows.pop(table, None)
                            self.readback.discard(table)
                            self.dirty.add(table)
                        continue
                    table = event["table"]
                    self.dirty.add(table)
                    if table in self.readback:
                        continue
                    if kind == "truncate":
                        self.rows.pop(table, None)
                        continue
                    for field, work in (("old", self._remove), ("new", self._add)):
                        row = event.get(field)
                        required = kind in (("update", "delete") if field == "old" else ("update", "insert"))
                        if required and not isinstance(row, str):
                            raise ValueError("Incomplete PostgreSQL old/new row image")
                        if row is not None:
                            if not isinstance(json.loads(row), dict):
                                raise ValueError("Expected PostgreSQL row object")
                            work(table, '{"table":' + json.dumps(table) + ',"row":' + row + '}')
                self.transactions += 1
        except Exception:
            self.healthy = False
            raise

    def refresh_catalog(self, catalog, reload_rows=None):
        """Catalog/sequence reads only: no user-table scans after the baseline."""
        if not self.healthy:
            raise ValueError("Incremental state is poisoned")
        old_columns = {item['relation']: item.get('columns') for item in map(json.loads, self.catalog)
                       if 'relation' in item}
        self.schema = catalog["schema"]
        self.catalog = catalog["records"]
        live = set()
        for record in self.catalog:
            item = json.loads(record)
            if "table" in item:
                raise ValueError("Catalog refresh must not contain table rows")
            if item.get("kind") in ("m", "f"):
                raise ValueError("Materialized views and foreign tables need a dedicated incremental adapter")
            if "relation" in item:
                table = item['relation']
                live.add(table)
                if table in self.readback or (table in old_columns and old_columns[table] != item.get('columns')):
                    self.dirty.add(table)
                    if self.rows.get(table) or table in self.readback:
                        if reload_rows is None:
                            self.healthy = False
                            raise ValueError('DDL changed stored rows; affected-relation readback is required')
                        self.rows.pop(table, None)
                        for record in reload_rows(table):
                            self._add(table, record)
        for table in set(self.rows) - live:
            del self.rows[table]
            self.dirty.add(table)
        self.schema_dirty = False
        self.readback.clear()

    def snapshot(self):
        if self.schema_dirty:
            raise ValueError('Schema changes require catalog refresh before comparison')
        if not self.healthy:
            raise ValueError("Incremental state is poisoned")
        return {"schema": self.schema, "records": self.catalog + [
            record for table in sorted(self.rows) for record, count in self.rows[table].values()
            for _ in range(count)]}
