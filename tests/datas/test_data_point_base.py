from __future__ import annotations

import time

import msgspec
import pytest

from pfund_blocks.datas.data_point_base import BaseDataPoint


class Point(BaseDataPoint, kw_only=True, frozen=True):
    value: float


class TestBaseDataPoint:
    def test_created_at_is_stamped_automatically(self):
        before = time.time_ns()
        point = Point(value=1.0)
        assert before <= point.created_at <= time.time_ns()

    def test_server_ts_defaults_to_none(self):
        assert Point(value=1.0).server_ts is None

    def test_is_frozen(self):
        point = Point(value=1.0)
        with pytest.raises(AttributeError):
            point.value = 2.0  # ty: ignore[invalid-assignment]

    def test_fields_are_keyword_only(self):
        with pytest.raises(TypeError):
            Point(1.0)  # ty: ignore[too-many-positional-arguments, missing-argument]

    def test_to_dict(self):
        point = Point(value=1.0, server_ts=20_000_000_000)
        assert point.to_dict() == {
            "server_ts": 20_000_000_000,
            "created_at": point.created_at,
            "value": 1.0,
        }


class TestSerialization:
    def test_round_trip_keeps_all_fields(self):
        point = Point(value=1.0, server_ts=20_000_000_000)
        assert msgspec.json.decode(msgspec.json.encode(point), type=Point) == point

    def test_encodes_its_tag(self):
        assert (
            msgspec.json.decode(msgspec.json.encode(Point(value=1.0)))["type"]
            == "Point"
        )

    def test_omits_defaults(self):
        assert "server_ts" not in msgspec.json.decode(
            msgspec.json.encode(Point(value=1.0))
        )

    def test_decode_rejects_unknown_fields(self):
        with pytest.raises(msgspec.ValidationError, match="unknown"):
            msgspec.json.decode(
                b'{"type": "Point", "value": 1.0, "extra": 1}', type=Point
            )

    def test_decode_rejects_server_ts_in_seconds(self):
        with pytest.raises(msgspec.ValidationError):
            msgspec.json.decode(
                b'{"type": "Point", "value": 1.0, "server_ts": 1767225600}', type=Point
            )
