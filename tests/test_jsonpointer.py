import pathlib
import re
from typing import List, Union

import pytest
from hypothesis import given, strategies as hs

from jschon import JSON, JSONPointer, JSONPointerError, RelativeJSONPointer, RelativeJSONPointerError
from jschon.utils import json_loadf
from tests.strategies import json, jsonpointer, jsonpointer_key, relative_jsonpointer, relative_jsonpointer_regex


@given(hs.lists(jsonpointer | hs.lists(jsonpointer_key)))
def test_create_jsonpointer(values: List[Union[str, List[str]]]):
    keys = []
    for value in values:
        keys += [jsonpointer_unescape(token) for token in value.split('/')[1:]] if isinstance(value, str) else value

    ptr0 = JSONPointer(*values)
    assert ptr0 == (ptr1 := JSONPointer(*values))
    assert ptr0 == (ptr2 := JSONPointer(keys))
    assert ptr0 == (ptr3 := JSONPointer(ptr0))
    assert ptr0 != (ptr4 := JSONPointer() if keys else JSONPointer('/'))
    assert ptr0 != (ptr5 := JSONPointer('/', keys))
    assert JSONPointer(ptr0, keys, *values) == JSONPointer(*values, keys, ptr0)

    ptrs = {ptr0, ptr1, ptr2, ptr3}
    assert ptrs == {ptr0}
    ptrs |= {ptr4, ptr5}
    assert ptrs > {ptr0}

    assert str(ptr0) == ''.join(f'/{jsonpointer_escape(key)}' for key in keys)
    assert list(ptr0) == keys
    assert bool(ptr0) == bool(keys)
    assert eval(repr(ptr0)) == ptr0


@given(jsonpointer, jsonpointer_key)
def test_extend_jsonpointer_one_key(value, newkey):
    pointer = JSONPointer(value) / newkey
    newtoken = jsonpointer_escape(newkey)
    assert pointer[-1] == newkey
    assert str(pointer) == f'{value}/{newtoken}'


@given(jsonpointer, hs.lists(jsonpointer_key))
def test_extend_jsonpointer_multi_keys(value, newkeys):
    pointer = (base_ptr := JSONPointer(value)) / newkeys
    for i in range(len(newkeys)):
        assert pointer[len(base_ptr) + i] == newkeys[i]
    assert str(pointer) == value + ''.join(f'/{jsonpointer_escape(key)}' for key in newkeys)


@given(json, jsonpointer_key)
def test_evaluate_jsonpointer(value, testkey):
    resolved_pointers = {}

    def generate_pointers(ptr, val):
        resolved_pointers[ptr] = val
        if isinstance(val, list):
            for i, item in enumerate(val):
                generate_pointers(f'{ptr}/{i}', item)
        elif isinstance(val, dict):
            for k, item in val.items():
                generate_pointers(f"{ptr}/{jsonpointer_escape(k)}", item)

    assert JSONPointer().evaluate(value) == value
    assert JSONPointer().evaluate(JSON(value)) == value

    generate_pointers('', value)
    for pointer, target in resolved_pointers.items():
        assert JSONPointer(pointer).evaluate(value) == target
        assert JSONPointer(pointer).evaluate(JSON(value)) == target

    if isinstance(value, list):
        with pytest.raises(JSONPointerError):
            JSONPointer(f'/{len(value)}').evaluate(value)
        with pytest.raises(JSONPointerError):
            JSONPointer('/-').evaluate(value)
        with pytest.raises(JSONPointerError):
            JSONPointer('/').evaluate(value)
    elif isinstance(value, dict):
        if testkey not in value:
            with pytest.raises(JSONPointerError):
                JSONPointer(f'/{jsonpointer_escape(testkey)}').evaluate(value)
    else:
        with pytest.raises(JSONPointerError):
            JSONPointer(f'/{value}').evaluate(value)


def jsonpointer_escape(key: str):
    return key.replace('~', '~0').replace('/', '~1')


def jsonpointer_unescape(token: str):
    return token.replace('~1', '/').replace('~0', '~')


@given(relative_jsonpointer)
def test_create_relative_jsonpointer(value):
    match = re.fullmatch(relative_jsonpointer_regex, value)
    up, ref = match.group('up', 'ref')
    r1 = RelativeJSONPointer(value)
    r2 = RelativeJSONPointer(up=up, ref=ref)
    assert r1 == r2
    assert str(r1) == value

    if up == 0:
        assert r1 == RelativeJSONPointer(ref=ref)
        if ref == '':
            assert r1 == RelativeJSONPointer()
        if ref != '#':
            assert r1 == RelativeJSONPointer(ref=JSONPointer(ref))
    if ref == '':
        assert r1 == RelativeJSONPointer(up=up)


# Examples from:
# https://datatracker.ietf.org/doc/html/draft-handrews-relative-json-pointer-01#section-5.1
# https://gist.github.com/geraintluff/5911303
example_file = pathlib.Path(__file__).parent / 'data' / 'relative_jsonpointer.json'


def pytest_generate_tests(metafunc):
    if metafunc.definition.name == 'test_evaluate_relative_jsonpointer':
        argnames = ('data', 'start', 'ref', 'result')
        argvalues = []
        examples = json_loadf(example_file)
        for example in examples:
            for test in example['tests']:
                argvalues += [pytest.param(
                    example['data'],
                    test['start'],
                    test['ref'],
                    test['result'],
                )]
        metafunc.parametrize(argnames, argvalues)


def test_evaluate_relative_jsonpointer(data, start, ref, result):
    data = JSON(data)
    start = JSONPointer(start)
    ref = RelativeJSONPointer(ref)
    node = start.evaluate(data)

    if result == '<data>':
        result = data
    elif result == '<fail>':
        with pytest.raises(RelativeJSONPointerError):
            ref.evaluate(node)
        return

    value = ref.evaluate(node)
    assert value == result
