from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

import copy
import itertools
import pickle

import pydantic
import pytest

from pfund_blocks.enums.timeframe import Timeframe
from pfund_blocks.resolution import Resolution


class TestParsing:
    @pytest.mark.parametrize(
        "value, period, timeframe, orderbook_level",
        [
            ("1m", 1, Timeframe.MINUTE, None),
            ("5m", 5, Timeframe.MINUTE, None),
            ("15min", 15, Timeframe.MINUTE, None),
            ("1h", 1, Timeframe.HOUR, None),
            ("2days", 2, Timeframe.DAY, None),
            ("1w", 1, Timeframe.WEEK, None),
            ("3mo", 3, Timeframe.MONTH, None),
            ("1y", 1, Timeframe.YEAR, None),
            ("30s", 30, Timeframe.SECOND, None),
            ("1t", 1, Timeframe.TICK, None),
            ("1q", 1, Timeframe.QUOTE, 1),
            ("1quote_L1", 1, Timeframe.QUOTE, 1),
            ("1quote_L2", 1, Timeframe.QUOTE, 2),
            ("1q_L3", 1, Timeframe.QUOTE, 3),
            ("1q_l3", 1, Timeframe.QUOTE, 3),
            ("1Q", 1, Timeframe.QUOTE, 1),
            ("1MO", 1, Timeframe.MONTH, None),
            ("1M", 1, Timeframe.MINUTE, None),
            ("100m", 100, Timeframe.MINUTE, None),
        ],
    )
    def test_valid(
        self, value: str, period: int, timeframe: Timeframe, orderbook_level: int | None
    ):
        resolution = Resolution(value)
        assert resolution.period == period
        assert resolution.timeframe is timeframe
        assert resolution.orderbook_level == orderbook_level

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("minute", "1m"),
            ("day", "1d"),
            ("quote", "1q_L1"),
            ("tick", "1t"),
        ],
    )
    def test_data_type_without_period(self, value: str, expected: str):
        assert repr(Resolution(value)) == expected

    @pytest.mark.parametrize("value", ["5_minute", "5-minute", "5-m"])
    def test_separator_after_period_is_removed(self, value: str):
        assert repr(Resolution(value)) == "5m"

    @pytest.mark.parametrize("value", [" 1m", "1m ", "\t1h\n"])
    def test_surrounding_whitespace_is_stripped(self, value: str):
        assert Resolution(value) == Resolution(value.strip())

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "-1m",
            " -1m",
            "0m",
            "01m",
            "1x",
            "m1",
            "1 m",
            "1.5m",
            "1quote_L0",
            "1quote_L4",
            "1q_2",
            "1m_",
            "daily",
        ],
    )
    def test_invalid(self, value: str):
        with pytest.raises(ValueError):
            Resolution(value)

    @pytest.mark.parametrize("value", ["1tick_L2", "1m_L1", "1d_L3"])
    def test_orderbook_level_only_for_quotes(self, value: str):
        with pytest.raises(ValueError, match="only quotes have orderbook levels"):
            Resolution(value)

    @pytest.mark.parametrize(
        "value, period", [("2q", 2), ("5q_L1", 5), ("10quote", 10)]
    )
    def test_l1_quote_supports_period(self, value: str, period: int):
        resolution = Resolution(value)
        assert resolution.is_quote_l1()
        assert resolution.period == period

    @pytest.mark.parametrize("value", ["2q_L2", "5q_L3", "10quote_L2"])
    def test_l2_l3_quote_rejects_period(self, value: str):
        with pytest.raises(ValueError, match="only L1 quotes support period > 1"):
            Resolution(value)

    def test_default_orderbook_level(self):
        assert Resolution("1q").orderbook_level == Resolution.DEFAULT_ORDERBOOK_LEVEL


class TestStrings:
    @pytest.mark.parametrize(
        "value, expected_repr, expected_str",
        [
            ("1minute", "1m", "1_MINUTE"),
            ("5m", "5m", "5_MINUTE"),
            ("1month", "1mo", "1_MONTH"),
            ("1quote", "1q_L1", "1_QUOTE_L1"),
            ("1q_L3", "1q_L3", "1_QUOTE_L3"),
            ("1tick", "1t", "1_TICK"),
        ],
    )
    def test_repr_and_str(self, value: str, expected_repr: str, expected_str: str):
        resolution = Resolution(value)
        assert repr(resolution) == expected_repr
        assert str(resolution) == expected_str

    @pytest.mark.parametrize("value", ["1m", "5h", "1mo", "1q_L2", "1t", "2w"])
    def test_repr_round_trips(self, value: str):
        resolution = Resolution(value)
        assert Resolution(repr(resolution)).is_strict_equal(resolution)


class TestPredicates:
    @pytest.mark.parametrize(
        "value, is_bar",
        [
            ("1s", True),
            ("1m", True),
            ("1h", True),
            ("1d", True),
            ("1w", False),
            ("1mo", False),
            ("1y", False),
            ("1t", False),
            ("1q", False),
        ],
    )
    def test_is_bar(self, value: str, is_bar: bool):
        assert Resolution(value).is_bar() is is_bar

    def test_timeframe_predicates(self):
        assert Resolution("1q").is_quote()
        assert Resolution("1t").is_tick()
        assert Resolution("1s").is_second()
        assert Resolution("1m").is_minute()
        assert Resolution("1h").is_hour()
        assert Resolution("1d").is_day()
        assert Resolution("1w").is_week()
        assert Resolution("1mo").is_month()
        assert Resolution("1y").is_year()

    @pytest.mark.parametrize(
        "value, l1, l2, l3",
        [
            ("1q", True, False, False),
            ("1q_L2", False, True, False),
            ("1q_L3", False, False, True),
            ("1t", False, False, False),
        ],
    )
    def test_quote_levels(self, value: str, l1: bool, l2: bool, l3: bool):
        resolution = Resolution(value)
        assert resolution.is_quote_l1() is l1
        assert resolution.is_quote_l2() is l2
        assert resolution.is_quote_l3() is l3


class TestToSeconds:
    @pytest.mark.parametrize(
        "value, seconds",
        [("1s", 1), ("30s", 30), ("1m", 60), ("5m", 300), ("2h", 7200), ("1d", 86400)],
    )
    def test_bar(self, value: str, seconds: int):
        assert Resolution(value).to_seconds() == seconds

    @pytest.mark.parametrize("value", ["1q", "1t", "1w", "1mo", "1y"])
    def test_non_bar_raises(self, value: str):
        with pytest.raises(ValueError, match="is not a bar resolution"):
            Resolution(value).to_seconds()


class TestEquality:
    def test_equal(self):
        assert Resolution("1m") == Resolution("1minute")
        assert Resolution("1q") == Resolution("1quote_L1")

    def test_same_duration_is_equal(self):
        assert Resolution("1h") == Resolution("60m")
        assert Resolution("1d") == Resolution("24h")
        assert Resolution("1w") == Resolution("7d")

    def test_strict_equal(self):
        assert Resolution("1h").is_strict_equal(Resolution("1hour"))
        assert not Resolution("1h").is_strict_equal(Resolution("60m"))

    def test_strict_equal_non_resolution(self):
        assert not Resolution("1m").is_strict_equal("1m")
        assert not Resolution("1m").is_strict_equal(None)

    def test_not_equal(self):
        assert Resolution("1m") != Resolution("2m")
        assert Resolution("1q_L1") != Resolution("1q_L2")
        assert Resolution("1q") != Resolution("1t")
        assert Resolution("2t") != Resolution("1t")

    def test_non_resolution_is_not_equal(self):
        assert Resolution("1m") != "1m"
        assert Resolution("1m") != Timeframe.MINUTE
        assert Resolution("1m").__eq__("1m") is NotImplemented

    def test_hash_consistent_with_eq(self):
        assert hash(Resolution("1h")) == hash(Resolution("60m"))
        assert len({Resolution("1h"), Resolution("60m"), Resolution("1hour")}) == 1

    def test_usable_as_dict_key(self):
        mapping = {Resolution("1m"): "minute"}
        assert mapping[Resolution("1minute")] == "minute"


class TestOrdering:
    """`a > b` means a is a higher (finer) resolution than b."""

    def test_finest_to_coarsest(self):
        ordered = [
            Resolution(value)
            for value in [
                "1q_L3",
                "1q_L2",
                "1q_L1",
                "1t",
                "1s",
                "1m",
                "1h",
                "1d",
                "1w",
                "1mo",
                "1y",
            ]
        ]
        for finer, coarser in itertools.pairwise(ordered):
            assert finer > coarser
            assert coarser < finer
            assert finer >= coarser
            assert coarser <= finer

    def test_period_within_unit(self):
        assert Resolution("1m") > Resolution("5m")
        assert Resolution("2t") < Resolution("1t")
        assert Resolution("1q") > Resolution("2q")

    def test_quote_with_period_still_finer_than_tick(self):
        assert Resolution("2q") > Resolution("1t")

    def test_compares_by_duration_across_units(self):
        assert Resolution("120m") < Resolution("1h")
        assert Resolution("25h") < Resolution("1d")
        assert Resolution("90s") > Resolution("2m")

    def test_quote_and_tick_finer_than_any_bar(self):
        assert Resolution("1t") > Resolution("1s")
        assert Resolution("100t") > Resolution("1s")
        assert Resolution("1q") > Resolution("1t")

    def test_equal_durations_are_le_and_ge(self):
        assert Resolution("1h") <= Resolution("60m")
        assert Resolution("1h") >= Resolution("60m")

    def test_sorted_coarsest_first(self):
        resolutions = [Resolution(value) for value in ["1d", "1m", "120m", "1h", "1q"]]
        assert [repr(r) for r in sorted(resolutions)] == [
            "1d",
            "120m",
            "1h",
            "1m",
            "1q_L1",
        ]

    def test_max_is_finest(self):
        assert repr(max(Resolution("1h"), Resolution("1t"), Resolution("1d"))) == "1t"

    def test_compare_with_non_resolution_raises(self):
        with pytest.raises(TypeError):
            _ = Resolution("1m") < "1h"


class TestRotation:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("1y", "1mo"),
            ("1mo", "1w"),
            ("1d", "1h"),
            ("5m", "1s"),
            ("1s", "1t"),
            ("1t", "1q_L1"),
            ("1q_L1", "1q_L2"),
            ("1q_L2", "1q_L3"),
            ("1q_L3", "1q_L3"),
        ],
    )
    def test_higher(self, value: str, expected: str):
        assert repr(Resolution(value).higher()) == expected
        assert repr(Resolution(value).finer()) == expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("1q_L3", "1q_L2"),
            ("1q_L2", "1q_L1"),
            ("1q_L1", "1t"),
            ("1t", "1s"),
            ("5s", "1m"),
            ("1d", "1w"),
            ("1mo", "1y"),
            ("1y", "1y"),
        ],
    )
    def test_lower(self, value: str, expected: str):
        assert repr(Resolution(value).lower()) == expected
        assert repr(Resolution(value).coarser()) == expected

    @pytest.mark.parametrize(
        "value, expected",
        [("5m", "1m"), ("1m", "1m"), ("3d", "1d"), ("1q_L2", "1q_L2"), ("10t", "1t")],
    )
    def test_to_unit(self, value: str, expected: str):
        assert repr(Resolution(value).to_unit()) == expected


class TestHigherResolutions:
    def test_from_day(self):
        assert [repr(r) for r in Resolution("1d").get_higher_resolutions()] == [
            "1h",
            "1m",
            "1s",
            "1t",
            "1q_L1",
            "1q_L2",
            "1q_L3",
        ]

    def test_includes_unit_when_period_gt_1(self):
        assert [repr(r) for r in Resolution("5m").get_higher_resolutions()] == [
            "1m",
            "1s",
            "1t",
            "1q_L1",
            "1q_L2",
            "1q_L3",
        ]

    def test_ignore_period(self):
        assert [
            repr(r) for r in Resolution("5m").get_higher_resolutions(ignore_period=True)
        ] == ["1s", "1t", "1q_L1", "1q_L2", "1q_L3"]

    def test_exclude_quote(self):
        assert [
            repr(r) for r in Resolution("5m").get_higher_resolutions(exclude_quote=True)
        ] == ["1m", "1s", "1t"]

    def test_from_quote(self):
        assert [repr(r) for r in Resolution("1q_L1").get_higher_resolutions()] == [
            "1q_L2",
            "1q_L3",
        ]
        assert Resolution("1q_L3").get_higher_resolutions() == []

    def test_from_tick(self):
        assert [repr(r) for r in Resolution("5t").get_higher_resolutions()] == [
            "1t",
            "1q_L1",
            "1q_L2",
            "1q_L3",
        ]
        assert Resolution("1t").get_higher_resolutions(exclude_quote=True) == []

    def test_alias(self):
        assert Resolution.get_finer_resolutions is Resolution.get_higher_resolutions


class TestLowerResolutions:
    def test_from_quote(self):
        assert [repr(r) for r in Resolution("1q_L2").get_lower_resolutions()] == [
            "1q_L1",
            "1t",
            "1s",
            "1m",
            "1h",
            "1d",
            "1w",
            "1mo",
            "1y",
        ]

    def test_exclude_quote(self):
        assert [
            repr(r)
            for r in Resolution("1q_L3").get_lower_resolutions(exclude_quote=True)
        ] == ["1t", "1s", "1m", "1h", "1d", "1w", "1mo", "1y"]

    def test_from_minute(self):
        assert [repr(r) for r in Resolution("5m").get_lower_resolutions()] == [
            "1h",
            "1d",
            "1w",
            "1mo",
            "1y",
        ]

    def test_from_year(self):
        assert Resolution("1y").get_lower_resolutions() == []

    def test_alias(self):
        assert Resolution.get_coarser_resolutions is Resolution.get_lower_resolutions


class _Model(pydantic.BaseModel):
    resolution: Resolution


class _UnionModel(pydantic.BaseModel):
    value: Resolution | Timeframe


class TestPydantic:
    def test_from_str(self):
        model = _Model(resolution="1quote")
        assert isinstance(model.resolution, Resolution)
        assert repr(model.resolution) == "1q_L1"

    def test_from_resolution_keeps_instance(self):
        resolution = Resolution("5m")
        assert _Model(resolution=resolution).resolution is resolution

    def test_invalid_str(self):
        with pytest.raises(pydantic.ValidationError):
            _Model(resolution="1x")

    def test_non_str_rejected(self):
        with pytest.raises(pydantic.ValidationError):
            _Model(resolution=60)

    def test_serializes_as_repr(self):
        model = _Model(resolution=Resolution("1q_L2"))
        assert model.model_dump() == {"resolution": "1q_L2"}
        assert model.model_dump_json() == '{"resolution":"1q_L2"}'

    def test_json_round_trip(self):
        model = _Model(resolution=Resolution("15m"))
        restored = _Model.model_validate_json(model.model_dump_json())
        assert restored.resolution.is_strict_equal(model.resolution)

    def test_json_schema(self):
        assert _Model.model_json_schema()["properties"]["resolution"] == {
            "title": "Resolution",
            "type": "string",
        }

    def test_union_falls_through_to_timeframe(self):
        assert _UnionModel(value=Timeframe.MINUTE).value is Timeframe.MINUTE
        assert isinstance(_UnionModel(value="5m").value, Resolution)


class TestImmutability:
    @pytest.mark.parametrize(
        "name, value",
        [("period", 5), ("timeframe", Timeframe.HOUR), ("orderbook_level", 2)],
    )
    def test_cannot_set_attribute(self, name: str, value: object):
        resolution = Resolution("1m")
        with pytest.raises(AttributeError, match="immutable"):
            setattr(resolution, name, value)
        assert repr(resolution) == "1m"

    def test_cannot_add_attribute(self):
        with pytest.raises(AttributeError, match="immutable"):
            Resolution("1m").foo = 1

    def test_cannot_delete_attribute(self):
        with pytest.raises(AttributeError, match="immutable"):
            del Resolution("1m").period

    def test_no_instance_dict(self):
        assert not hasattr(Resolution("1m"), "__dict__")

    def test_copy_constructor_copies_all_slots(self):
        original = Resolution("2q")
        copied = Resolution(original)
        assert copied is not original
        assert (copied.period, copied.timeframe, copied.orderbook_level) == (
            2,
            Timeframe.QUOTE,
            1,
        )

    @pytest.mark.parametrize("value", ["1m", "5h", "2q", "1q_L3", "10t", "1mo"])
    def test_pickle_round_trip(self, value: str):
        resolution = Resolution(value)
        restored = pickle.loads(pickle.dumps(resolution))
        assert restored.is_strict_equal(resolution)
        assert restored.orderbook_level == resolution.orderbook_level

    @pytest.mark.parametrize("copier", [copy.copy, copy.deepcopy])
    def test_copy_module(self, copier: Callable[[Resolution], Resolution]):
        resolution = Resolution("1q_L2")
        assert copier(resolution).is_strict_equal(resolution)
