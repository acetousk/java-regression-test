"""Conservative identifier mapping; never rewrite SQL expressions or data values."""

import re


# Match Moqui EntityJavaUtil.camelCaseToUnderscored (including acronyms).
def entity_name(name):
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
        return re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()
    return name


class MappingCollision(ValueError):
    pass


class NameMapping:
    def __init__(self):
        self.names = {}

    def identifier(self, scope, physical):
        logical = entity_name(physical)
        key = (scope, logical)
        previous = self.names.setdefault(key, physical)
        if previous != physical:
            raise MappingCollision(f"Identifier collision in {scope}: {previous!r} and {physical!r} -> {logical!r}")
        return logical

    def table(self, physical):
        # Snapshot relation names are schema.name, not SQL-quoted identifiers.
        # Ambiguous dotted names cannot safely be inferred from that envelope.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", physical):
            return physical
        schema, table = physical.split(".")
        return schema + "." + self.identifier(("table", schema), table)

    def record(self, record):
        # Only the snapshot envelope's identifiers, not nested JSON keys/values.
        if isinstance(record, dict) and isinstance(record.get("table"), str) and isinstance(record.get("row"), dict):
            table = self.table(record["table"])
            return {**record, "table": table, "row": {
                self.identifier(("column", table), key): value
                for key, value in record["row"].items()
            }}
        # Sequence names/state are deliberately not inferred from entity names.
        return record

    def schema(self, sql):
        """Normalize only a small, explicit pg_dump DDL grammar.

        Unrecognized statements stay token-for-token physical, so unsupported DDL
        can cause false negatives, never a silently ignored schema difference.
        Only consecutive supported DDL statements are order-independent;
        unsupported statements (including SET) remain ordering barriers.
        """
        token_pattern = re.compile(
            r"--[^\n]*|/\*.*?\*/|"
            r"[eE]'(?:''|\\.|[^'\\])*'|'(?:''|[^'])*'|"
            r'"(?:""|[^"])*"|'
            r"\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*|)\$.*?\$(?P=tag)\$|"
            r"[A-Za-z_][A-Za-z0-9_$]*|[^\s]", re.S,
        )
        tokens = [match.group() for match in token_pattern.finditer(sql)
                  if not match.group().startswith(("--", "/*"))]
        statements, statement, group = [], [], []
        for token in tokens:
            statement.append(token)
            if token == ";":
                normalized = self.statement(statement)
                if normalized is not None:
                    group.append(normalized)
                else:
                    statements.extend(sorted(group))
                    group = []
                    statements.append(tuple(statement))
                statement = []
        statements.extend(sorted(group))
        if statement:
            statements.append(tuple(statement))
        return statements

    @staticmethod
    def unquote(token):
        if token.startswith('"'):
            return token[1:-1].replace('""', '"')
        if re.fullmatch(r"[a-z_][a-z0-9_$]*", token):
            return token
        raise ValueError("Not an identifier")

    def statement(self, tokens):
        result = list(tokens)

        def table_at(index):
            # Only schema-qualified relation references as emitted by pg_dump.
            schema = self.unquote(tokens[index])
            if tokens[index + 1] != ".":
                raise ValueError("Unqualified table")
            physical = self.unquote(tokens[index + 2])
            if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (schema, physical)):
                raise ValueError("Unsupported relation identifier")
            table = self.table(schema + "." + physical)
            result[index + 2] = '"' + table.rsplit(".", 1)[-1].replace('"', '""') + '"'
            return table, index + 3

        def column_at(index, table):
            physical = self.unquote(tokens[index])
            logical = self.identifier(("column", table), physical)
            result[index] = '"' + logical.replace('"', '""') + '"'

        def columns_at(index, table):
            if tokens[index] != "(":
                raise ValueError("Expected column list")
            index += 1
            while True:
                column_at(index, table)
                index += 1
                if tokens[index] == ")":
                    return index + 1
                if tokens[index] != ",":
                    raise ValueError("Not a simple column list")
                index += 1

        # Syntax failures fall back to the original statement. Collisions must
        # propagate rather than allowing a many-to-one mapping.
        try:
            if tokens[:2] == ["CREATE", "TABLE"]:
                table, index = table_at(2)
                if tokens[index] != "(" or tokens[-2:] != [")", ";"]:
                    return None
                index += 1
                depth, at_column = 0, True
                for position in range(index, len(tokens) - 2):
                    token = tokens[position]
                    if at_column:
                        if token in ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "EXCLUDE", "LIKE"):
                            return None
                        column_at(position, table)
                        at_column = False
                    elif token in ("REFERENCES", "CHECK", "GENERATED"):
                        return None
                    if token == "(":
                        depth += 1
                    elif token == ")":
                        depth -= 1
                    elif token == "," and depth == 0:
                        at_column = True
            elif tokens[:2] == ["ALTER", "TABLE"]:
                table, index = table_at(3 if tokens[2] == "ONLY" else 2)
                tail = tokens[index:]
                if tail[:2] == ["OWNER", "TO"]:
                    pass
                elif tail[:2] == ["ADD", "CONSTRAINT"]:
                    # Constraint names are physical evidence, not entity names.
                    index += 3
                    if tokens[index:index + 2] in (["PRIMARY", "KEY"], ["FOREIGN", "KEY"]):
                        foreign = tokens[index] == "FOREIGN"
                        index = columns_at(index + 2, table)
                        if foreign:
                            if tokens[index] != "REFERENCES":
                                return None
                            referenced, index = table_at(index + 1)
                            columns_at(index, referenced)
                    elif tokens[index] == "UNIQUE":
                        columns_at(index + 1, table)
                    else:
                        return None
                else:
                    return None
            else:
                return None
        except MappingCollision:
            raise
        except (IndexError, ValueError):
            return None
        return tuple(result)
