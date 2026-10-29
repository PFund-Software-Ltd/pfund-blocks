"""Schema-based conversion of API responses into standardized data.

A schema is a dict that describes the output: each key is an output field, and each
value is a rule that says how to produce that field from the payload.

Rules
-----
A rule takes one of three shapes:

1. Path (list or tuple): a pipeline of steps, applied left to right.
   - a str step descends one dict key
   - a callable step is applied to the current value (e.g. float, a lambda)

       "symbol": ("symbol",)                         # payload["symbol"]
       "tick_size": ("priceFilter", "tickSize")      # payload["priceFilter"]["tickSize"]
       "price": ("price", float)                     # float(payload["price"])
       "ts": ("timestamp", lambda ms: ms / 1000)     # payload["timestamp"] / 1000

2. Nested schema (dict): converts a part of the payload with its own schema.
   The part is located by a sibling "@<field>" path, which follows the same rules
   as a Path (str steps and callables):

       "@data": ("result", "list"),                  # where the nested data is
       "data": {                                     # how to convert it
           "open": ("open", float),
           "close": ("close", float),
       }

   Any field name works ("data", "data2", ...), so a payload can be split into as
   many nested parts as needed. "@" keys are not included in the output.

3. Hardcoded value (anything else): copied to the output as is.

       "category": "spot"

Behavior
--------
- Root fields: Paths of top-level fields start from the root payload.
- Nested fields: Paths inside a nested schema start from its located part.
- Missing values: if a str step finds no key, a null value, or a non-dict parent,
  the field is None and the remaining steps (including callables) are skipped.
  This handles optional fields, e.g. "expiration" only exists for futures.
  A missing "@<field>" part makes the nested field None.
- Lists: a list payload (or nested part) is converted item by item into a list.
- Errors: SchemaParseError names where it happened, the rule's path, and the step that
  failed, e.g.
      data[2].price: ("price", float) failed at float: ValueError: could not convert ...
  It is raised when a callable raises, a nested schema has no "@<field>" path, an
  "@<field>" path has no nested schema, or a payload is not a dict / list of dicts.

Example
-------
    payload = {
        "topic": "kline.1.BTCUSDT",
        "ts": 1752760761525,
        "data": [
            {"open": "118407.3", "close": "118354.3", "timestamp": 1752760761525},
        ],
    }
    schema = {
        "ts": ("ts", lambda ms: ms / 1000),  # from the root payload, then transformed
        "@data": ("data",),                  # where the nested data is
        "data": {                            # nested schema, applied to each item
            "open": ("open", float),
            "close": ("close", float),
            "ts": ("timestamp", float),
        },
    }
    parse_schema(payload, schema)
    # {
    #     "ts": 1752760761.525,
    #     "data": [{"open": 118407.3, "close": 118354.3, "ts": 1752760761525.0}],
    # }
"""

from __future__ import annotations

from typing import Any, overload

import reprlib
from collections.abc import Callable, Sequence

type Step = str | Callable[[Any], Any]
type Path = Sequence[Step]
type Schema = dict[str, Any]


class SchemaParseError(Exception):
    pass


@overload
def parse_schema(payload: dict[str, Any], schema: Schema) -> dict[str, Any]: ...
@overload
def parse_schema(payload: list[dict[str, Any]], schema: Schema) -> list[dict[str, Any]]: ...
def parse_schema(payload: dict[str, Any] | list[dict[str, Any]], schema: Schema) -> dict[str, Any] | list[dict[str, Any]]:
    """Converts a payload into standardized data according to the schema (see the module docstring)."""
    return _convert(payload, schema, loc="")


def _convert(payload: Any, schema: Schema, loc: str) -> Any:
    """Converts a dict, or a list of dicts item by item. `loc` is where the payload is in the
    output (e.g. "data[2]"), used in error messages.
    """
    if isinstance(payload, dict):
        return _parse(payload, schema, loc)
    elif isinstance(payload, list):
        output: list[dict[str, Any]] = []
        for i, item in enumerate(payload):
            item_loc = f"{loc}[{i}]"
            if not isinstance(item, dict):
                raise SchemaParseError(f"{item_loc}: expected a dict, got {type(item).__name__}: {reprlib.repr(item)}")
            output.append(_parse(item, schema, item_loc))
        return output
    else:
        raise SchemaParseError(
            f"{loc or '<root>'}: expected a dict or a list of dicts, got {type(payload).__name__}: {reprlib.repr(payload)}"
        )


def _descend(obj: Any, key: str) -> Any:
    """Descends one key into a dict, giving None for an absent key or a null/non-dict parent."""
    return obj[key] if isinstance(obj, dict) and key in obj else None


def _step_name(step: Callable[[Any], Any]) -> str:
    return getattr(step, "__name__", repr(step))


def _path_repr(path: Path) -> str:
    """e.g. ('priceFilter', 'tickSize') -> ("priceFilter", "tickSize"), ('price', float) -> ("price", float)"""
    names = [f'"{step}"' if isinstance(step, str) else _step_name(step) for step in path]
    return f"({', '.join(names)}{',' if len(names) == 1 else ''})"


def _walk(value: Any, path: Path, loc: str) -> Any:
    """Walks a path left to right: str steps descend one dict key, callable steps are applied
    to the current value. A missing/null intermediate gives None before any later callable runs.
    """
    for step in path:
        if isinstance(step, str):
            value = _descend(value, step)
            if value is None:
                return None
        elif isinstance(step, dict):
            raise SchemaParseError(f"{loc}: {_path_repr(path)} has a dict as a path step, use a nested schema instead")
        else:
            try:
                value = step(value)
            except Exception as exc:
                raise SchemaParseError(
                    f"{loc}: {_path_repr(path)} failed at {_step_name(step)}: {type(exc).__name__}: {exc}"
                ) from exc
    return value


def _parse(msg: dict[str, Any], schema: Schema, loc: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, rule in schema.items():
        field_loc = f"{loc}.{key}" if loc else key
        if key.startswith("@"):
            if not isinstance(schema.get(key[1:]), dict):
                raise SchemaParseError(f'{field_loc}: "{key}" has no nested schema "{key[1:]}"')
            continue
        # Case 1: path
        if isinstance(rule, (list, tuple)):
            output[key] = _walk(msg, rule, field_loc)
        # Case 2: nested schema, located via its "@key" path
        elif isinstance(rule, dict):
            source_key = f"@{key}"
            if source_key not in schema:
                raise SchemaParseError(f'{field_loc}: nested schema "{key}" has no "{source_key}" path')
            source_loc = f"{loc}.{source_key}" if loc else source_key
            source = _walk(msg, schema[source_key], source_loc)
            output[key] = None if source is None else _convert(source, rule, field_loc)
        # Case 3: hardcoded value
        else:
            output[key] = rule
    return output
