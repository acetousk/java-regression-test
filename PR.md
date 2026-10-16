# PR title and body

## Title
fix: compare entity and field names across engines

## Destination
- Repository: `acetousk/java-regression-test`.
- Branch: `fix/schema-name-mapping`; base: `master`.
- `origin` became available during the session. Its default branch HEAD matches
  the local snapshot commit (`18f590ae16f830c28bc973fca355f937df536285`).
- Publication outcome and actual PR URL are recorded in
  `/home/user/moqui/java-regression-test-schema-mapping-result.md`.

## Body
### Summary
- Map Java underscore entity/field names and Rust quoted camel-case names
  conservatively in snapshot rows and supported pg_dump DDL.
- Reject identifier collisions; never rewrite SQL expressions, data values,
  nested JSON, schema namespaces, sequence names/state, or constraint names.
- Separate logical pass/fail from physical evidence in `comparison.json`;
  retain original snapshots, exact physical byte/record differences and
  `schema.diff`, and add `logical-schema.diff`.
- Unsupported DDL remains physical; complete logical equivalence is not claimed.
- Keep all source-data/runtime-write differences visible; no exclusions added.

### Validation
- `python -m unittest discover -v`: 30 tests passed.
- Read-only comparison of all four existing snapshot pairs under the main
  checkout's `.runs`: all remain failures for both logical schema and rows;
  no mapping collisions. Reports were generated only in temporary directories.
- Confirmed acronym handling against Java's `EntityJavaUtil.camelCaseToUnderscored`
  source, read-only.
- No submodule initialization, application startup, database reset, or runtime
  changes. No changes to the other agents' checkouts.
