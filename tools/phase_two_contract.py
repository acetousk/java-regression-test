"""Phase 2 Change 18: fixed paired inputs and independently checked result contracts."""
from copy import deepcopy
from decimal import Decimal

BUSINESS_CASES = [
    ('create-type', 'create#moqui.basic.EnumerationType', {'enumTypeId': 'PHASE2_TYPE', 'description': 'Phase two enum type'}, 'enumeration_type', 'enum_type_id', 'PHASE2_TYPE', 'description', 'Phase two enum type'),
    ('create-enum', 'create#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'enumTypeId': 'PHASE2_TYPE', 'description': 'Created', 'sequenceNum': '7'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Created'),
    ('duplicate-enum-refused', 'create#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'enumTypeId': 'PHASE2_TYPE', 'description': 'Must not overwrite'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Created'),
    ('update-enum', 'update#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'description': 'Updated'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Updated'),
    ('store-enum', 'store#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'description': 'Stored'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Stored'),
    ('delete-enum', 'delete#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', None, None),
    ('delete-type', 'delete#moqui.basic.EnumerationType', {'enumTypeId': 'PHASE2_TYPE'}, 'enumeration_type', 'enum_type_id', 'PHASE2_TYPE', None, None),
    ('create-unit-a', 'create#moqui.basic.Uom', {'uomId': 'PHASE2_M', 'uomTypeEnumId': 'UT_LENGTH_MEASURE', 'description': 'Phase two metres'}, 'uom', 'uom_id', 'PHASE2_M', 'description', 'Phase two metres'),
    ('create-unit-b', 'create#moqui.basic.Uom', {'uomId': 'PHASE2_CM', 'uomTypeEnumId': 'UT_LENGTH_MEASURE', 'description': 'Phase two centimetres'}, 'uom', 'uom_id', 'PHASE2_CM', 'description', 'Phase two centimetres'),
    ('create-conversion', 'create#moqui.basic.UomConversion', {'uomConversionId': 'PHASE2_CONV', 'uomId': 'PHASE2_M', 'toUomId': 'PHASE2_CM', 'conversionFactor': '100', 'fromDate': '2020-01-01 00:00:00'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 100),
    ('convert-forward', 'org.moqui.impl.BasicServices.convert#Uom', {'uomId': 'PHASE2_M', 'toUomId': 'PHASE2_CM', 'amount': '2', 'effectiveDate': '2026-01-01 00:00:00'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 100),
    ('convert-reverse', 'org.moqui.impl.BasicServices.convert#Uom', {'uomId': 'PHASE2_CM', 'toUomId': 'PHASE2_M', 'amount': '200', 'effectiveDate': '2026-01-01 00:00:00'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 100),
    ('update-conversion', 'org.moqui.impl.BasicServices.update#UomConversion', {'uomConversionId': 'PHASE2_CONV', 'conversionFactor': '200'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 200),
    ('delete-conversion', 'delete#moqui.basic.UomConversion', {'uomConversionId': 'PHASE2_CONV'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', None, None),
    ('delete-unit-b', 'delete#moqui.basic.Uom', {'uomId': 'PHASE2_CM'}, 'uom', 'uom_id', 'PHASE2_CM', None, None),
    ('delete-unit-a', 'delete#moqui.basic.Uom', {'uomId': 'PHASE2_M'}, 'uom', 'uom_id', 'PHASE2_M', None, None),
]

CONVERSION_OUTPUTS = {
    'convert-forward': {'convertedAmount': '200.0'},
    'convert-reverse': {'convertedAmount': '2.0'},
}
CONVERSION_NUMBERS = {'convert-forward': Decimal(200), 'convert-reverse': Decimal(2)}
# Java demo-user oracle: the submitted local midnight is stored at 06:00 UTC.
CREATION_FIELDS = {
    'create-enum': {'enum_type_id': 'PHASE2_TYPE', 'sequence_num': 7},
    'create-unit-a': {'uom_type_enum_id': 'UT_LENGTH_MEASURE'},
    'create-unit-b': {'uom_type_enum_id': 'UT_LENGTH_MEASURE'},
    'create-conversion': {'uom_id': 'PHASE2_M', 'to_uom_id': 'PHASE2_CM', 'from_date': '2020-01-01T06:00:00'},
}


def business_contracts():
    states, contracts = {}, {}
    for name, service, params, table, pk, key, field, expected in BUSINESS_CASES:
        target = (table, pk, key)
        before = deepcopy(states.get(target))
        after = deepcopy(before)
        if name.startswith('create-'):
            after = {pk: key, field: expected, **CREATION_FIELDS.get(name, {})}
        elif name.startswith(('update-', 'store-')):
            after[field] = expected
        elif name.startswith('delete-'):
            after = None
        states[target] = after
        contracts[name] = {'service': service, 'parameters': deepcopy(params), 'target': target, 'before': before, 'after': deepcopy(after)}
    return contracts


def selected_rows_match(rows, expected):
    if expected is None:
        return rows == []
    return (len(rows) == 1 and isinstance(rows[0], dict)
            and all(key in rows[0] and rows[0][key] == value for key, value in expected.items()))
