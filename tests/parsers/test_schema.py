from __future__ import annotations

import pytest

from pfund_blocks.parsers.parser_base import BaseParser
from pfund_blocks.parsers.schema import SchemaParseError, parse_schema


class TestHardcodedValue:
    def test_copied_as_is(self):
        assert parse_schema({}, {"category": "spot"}) == {"category": "spot"}

    def test_non_str_values(self):
        schema = {"n": 1, "none": None, "flag": True, "s": {"a"}}
        assert parse_schema({}, schema) == {"n": 1, "none": None, "flag": True, "s": {"a"}}


class TestPath:
    def test_single_key(self):
        assert parse_schema({"symbol": "BTCUSDT"}, {"symbol": ("symbol",)}) == {"symbol": "BTCUSDT"}

    def test_deep_keys(self):
        payload = {"priceFilter": {"tickSize": "0.1"}}
        assert parse_schema(payload, {"tick_size": ("priceFilter", "tickSize")}) == {"tick_size": "0.1"}

    def test_list_path_same_as_tuple(self):
        payload = {"priceFilter": {"tickSize": "0.1"}}
        assert parse_schema(payload, {"tick_size": ["priceFilter", "tickSize"]}) == {"tick_size": "0.1"}

    def test_callable(self):
        assert parse_schema({"price": "1.5"}, {"price": ("price", float)}) == {"price": 1.5}

    def test_callables_applied_left_to_right(self):
        schema = {"x": ("x", int, lambda v: v * 10, str)}
        assert parse_schema({"x": "3"}, schema) == {"x": "30"}

    def test_callable_between_keys(self):
        payload = {"list": [{"symbol": "BTCUSDT"}]}
        schema = {"symbol": ("list", lambda x: x[0], "symbol")}
        assert parse_schema(payload, schema) == {"symbol": "BTCUSDT"}

    def test_callable_only_receives_root_payload(self):
        assert parse_schema({"a": 1}, {"keys": (lambda p: sorted(p),)}) == {"keys": ["a"]}

    def test_empty_path_returns_root_payload(self):
        assert parse_schema({"a": 1}, {"root": ()}) == {"root": {"a": 1}}

    def test_falsy_values_are_kept(self):
        payload = {"zero": 0, "empty": "", "false": False}
        schema = {"zero": ("zero",), "empty": ("empty",), "false": ("false",)}
        assert parse_schema(payload, schema) == payload


class TestMissing:
    def test_absent_key_gives_none(self):
        assert parse_schema({}, {"expiration": ("expiration",)}) == {"expiration": None}

    def test_null_value_gives_none(self):
        assert parse_schema({"expiration": None}, {"expiration": ("expiration",)}) == {"expiration": None}

    def test_absent_intermediate_gives_none(self):
        assert parse_schema({}, {"tick_size": ("priceFilter", "tickSize")}) == {"tick_size": None}

    def test_null_intermediate_gives_none(self):
        payload = {"priceFilter": None}
        assert parse_schema(payload, {"tick_size": ("priceFilter", "tickSize")}) == {"tick_size": None}

    def test_non_dict_parent_gives_none(self):
        payload = {"priceFilter": "0.1"}
        assert parse_schema(payload, {"tick_size": ("priceFilter", "tickSize")}) == {"tick_size": None}

    def test_skips_later_callables(self):
        def fail(_):
            raise AssertionError("should not be called")

        assert parse_schema({}, {"x": ("x", fail)}) == {"x": None}

    def test_callable_returning_none_does_not_stop_path(self):
        """Current behavior: only str steps short-circuit on None."""
        schema = {"x": ("x", lambda _: None, lambda v: v is None)}
        assert parse_schema({"x": 1}, schema) == {"x": True}

    def test_str_step_after_callable_returning_none_gives_none(self):
        schema = {"x": ("x", lambda _: None, "y")}
        assert parse_schema({"x": 1}, schema) == {"x": None}


class TestNestedSchema:
    def test_located_by_at_key(self):
        payload = {"result": {"list": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]}}
        schema = {
            "@data": ("result", "list"),
            "data": {"symbol": ("symbol",)},
        }
        assert parse_schema(payload, schema) == {"data": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]}

    def test_dict_source(self):
        payload = {"result": {"symbol": "BTCUSDT"}}
        schema = {"@data": ("result",), "data": {"symbol": ("symbol",)}}
        assert parse_schema(payload, schema) == {"data": {"symbol": "BTCUSDT"}}

    def test_at_key_path_with_callable(self):
        payload = {"result": {"list": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]}}
        schema = {
            "@data": ("result", "list", lambda x: x[0]),
            "data": {"symbol": ("symbol",)},
        }
        assert parse_schema(payload, schema) == {"data": {"symbol": "BTCUSDT"}}

    def test_nested_paths_start_from_located_part(self):
        payload = {"symbol": "ROOT", "result": {"symbol": "NESTED"}}
        schema = {"@data": ("result",), "data": {"symbol": ("symbol",)}}
        assert parse_schema(payload, schema) == {"data": {"symbol": "NESTED"}}

    def test_root_fields_beside_nested(self):
        payload = {"ts": 1752760761525, "data": [{"open": "118407.3"}]}
        schema = {
            "ts": ("ts",),
            "@data": ("data",),
            "data": {"open": ("open", float)},
        }
        assert parse_schema(payload, schema) == {"ts": 1752760761525, "data": [{"open": 118407.3}]}

    def test_multiple_nested_schemas(self):
        payload = {
            "result": {"list": [{"symbol": "BTCUSDT"}]},
            "retExtInfo": {"list": [{"code": 1}]},
        }
        schema = {
            "@data": ("result", "list"),
            "data": {"symbol": ("symbol",)},
            "@data2": ("retExtInfo", "list"),
            "data2": {"code": ("code",)},
        }
        assert parse_schema(payload, schema) == {
            "data": [{"symbol": "BTCUSDT"}],
            "data2": [{"code": 1}],
        }

    def test_deeply_nested(self):
        payload = {"a": {"b": [{"c": {"d": 1}}]}}
        schema = {
            "@outer": ("a", "b"),
            "outer": {
                "@inner": ("c",),
                "inner": {"d": ("d",)},
            },
        }
        assert parse_schema(payload, schema) == {"outer": [{"inner": {"d": 1}}]}

    def test_hardcoded_value_in_nested(self):
        payload = {"list": [{"symbol": "BTCUSDT"}]}
        schema = {"@data": ("list",), "data": {"symbol": ("symbol",), "category": "linear"}}
        assert parse_schema(payload, schema) == {"data": [{"symbol": "BTCUSDT", "category": "linear"}]}

    def test_at_keys_not_in_output(self):
        schema = {"@data": ("list",), "data": {"x": ("x",)}}
        assert "@data" not in parse_schema({"list": []}, schema)

    def test_empty_list_source(self):
        schema = {"@data": ("list",), "data": {"x": ("x",)}}
        assert parse_schema({"list": []}, schema) == {"data": []}

    def test_missing_source_gives_none(self):
        schema = {"@data": ("result", "list"), "data": {"x": ("x",)}}
        assert parse_schema({}, schema) == {"data": None}

    def test_null_source_gives_none(self):
        schema = {"@data": ("result", "list"), "data": {"x": ("x",)}}
        assert parse_schema({"result": {"list": None}}, schema) == {"data": None}


class TestListPayload:
    def test_converted_item_by_item(self):
        payload = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        assert parse_schema(payload, {"symbol": ("symbol",)}) == [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]

    def test_empty_list(self):
        assert parse_schema([], {"symbol": ("symbol",)}) == []

    def test_missing_per_item(self):
        payload = [{"expiration": 1}, {}]
        assert parse_schema(payload, {"expiration": ("expiration",)}) == [{"expiration": 1}, {"expiration": None}]


class TestErrors:
    """Errors name where they happened (output location), the rule's path, and the failed step."""

    def test_callable_raises(self):
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({"price": "abc"}, {"price": ("price", float)})
        assert str(exc_info.value) == (
            "price: (\"price\", float) failed at float: ValueError: could not convert string to float: 'abc'"
        )
        assert isinstance(exc_info.value.__cause__, ValueError)

    def test_lambda_raises(self):
        with pytest.raises(SchemaParseError, match=r'^x: \("x", <lambda>\) failed at <lambda>: TypeError: '):
            parse_schema({"x": 1}, {"x": ("x", lambda v: v["a"])})

    def test_names_failed_step_among_callables(self):
        def explode(_):
            raise RuntimeError("boom")

        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({"x": "1"}, {"x": ("x", int, explode, str)})
        assert str(exc_info.value) == 'x: ("x", int, explode, str) failed at explode: RuntimeError: boom'

    def test_names_list_item_in_nested(self):
        payload = {"result": {"list": [{"price": "1"}, {"price": "2"}, {"price": "abc"}]}}
        schema = {"@data": ("result", "list"), "data": {"price": ("price", float)}}
        with pytest.raises(SchemaParseError, match=r'^data\[2\]\.price: \("price", float\) failed at float'):
            parse_schema(payload, schema)

    def test_names_list_item_in_list_payload(self):
        with pytest.raises(SchemaParseError, match=r"^\[1\]\.price: "):
            parse_schema([{"price": "1"}, {"price": "abc"}], {"price": ("price", float)})

    def test_names_deeply_nested_location(self):
        payload = {"a": [{"b": [{"c": "z"}]}]}
        schema = {"@outer": ("a",), "outer": {"@inner": ("b",), "inner": {"c": ("c", int)}}}
        with pytest.raises(SchemaParseError, match=r'^outer\[0\]\.inner\[0\]\.c: \("c", int\) failed at int'):
            parse_schema(payload, schema)

    def test_callable_in_at_key_path_raises(self):
        schema = {"@data": ("list", lambda x: x[5]), "data": {"x": ("x",)}}
        with pytest.raises(SchemaParseError, match=r'^@data: \("list", <lambda>\) failed at <lambda>: IndexError'):
            parse_schema({"list": []}, schema)

    def test_not_wrapped_twice(self):
        schema = {"@data": ("list",), "data": {"price": ("price", float)}}
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({"list": [{"price": "abc"}]}, schema)
        assert str(exc_info.value).count("failed at") == 1
        assert isinstance(exc_info.value.__cause__, ValueError)

    def test_nested_schema_without_at_key(self):
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({}, {"data": {"x": ("x",)}})
        assert str(exc_info.value) == 'data: nested schema "data" has no "@data" path'

    def test_orphan_at_key(self):
        """Likely a typo, e.g. "@dta" for "data"."""
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({"list": [1]}, {"@data": ("list",)})
        assert str(exc_info.value) == '@data: "@data" has no nested schema "data"'

    def test_at_key_with_path_rule(self):
        schema = {"@data": ("other",), "data": ("list",)}
        with pytest.raises(SchemaParseError, match='"@data" has no nested schema "data"'):
            parse_schema({"list": [1], "other": [2]}, schema)

    def test_orphan_at_key_in_nested(self):
        schema = {"@data": ("list",), "data": {"@extra": ("x",)}}
        with pytest.raises(SchemaParseError, match=r'^data\[0\]\.@extra: "@extra" has no nested schema "extra"'):
            parse_schema({"list": [{}]}, schema)

    def test_dict_as_path_step(self):
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({"a": {}}, {"x": ("a", {"b": 1})})
        assert str(exc_info.value) == "x: (\"a\", {'b': 1}) has a dict as a path step, use a nested schema instead"

    @pytest.mark.parametrize("payload", ["str", 1, None, ("a",)])
    def test_payload_not_dict_or_list(self, payload):
        with pytest.raises(SchemaParseError, match=r"^<root>: expected a dict or a list of dicts, got "):
            parse_schema(payload, {"x": ("x",)})

    @pytest.mark.parametrize("item", [["a"], "str", 1, None])
    def test_list_item_not_dict(self, item):
        with pytest.raises(SchemaParseError, match=r"^\[1\]: expected a dict, got "):
            parse_schema([{"x": 1}, item], {"x": ("x",)})

    def test_nested_source_not_dict_or_list(self):
        schema = {"@data": ("price",), "data": {"x": ("x",)}}
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({"price": "1.5"}, schema)
        assert str(exc_info.value) == "data: expected a dict or a list of dicts, got str: '1.5'"

    def test_nested_source_list_item_not_dict(self):
        schema = {"@data": ("list",), "data": {"x": ("x",)}}
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema({"list": [{"x": 1}, ["a"]]}, schema)
        assert str(exc_info.value) == "data[1]: expected a dict, got list: ['a']"

    def test_long_payload_is_truncated(self):
        with pytest.raises(SchemaParseError) as exc_info:
            parse_schema("x" * 1000, {})
        assert len(str(exc_info.value)) < 100


class TestBaseParser:
    def test_parse_schema_is_staticmethod(self):
        assert BaseParser.parse_schema({"a": 1}, {"x": ("a",)}) == {"x": 1}

    def test_parse_schema_on_instance(self):
        class Parser(BaseParser):
            pass

        assert Parser().parse_schema({"a": 1}, {"x": ("a",)}) == {"x": 1}


class TestDocstringExample:
    def test_kline(self):
        payload = {
            "topic": "kline.1.BTCUSDT",
            "ts": 1752760761525,
            "data": [
                {"open": "118407.3", "close": "118354.3", "timestamp": 1752760761525},
            ],
        }
        schema = {
            "ts": ("ts", lambda ms: ms / 1000),
            "@data": ("data",),
            "data": {
                "open": ("open", float),
                "close": ("close", float),
                "ts": ("timestamp", float),
            },
        }
        assert parse_schema(payload, schema) == {
            "ts": 1752760761.525,
            "data": [{"open": 118407.3, "close": 118354.3, "ts": 1752760761525.0}],
        }
