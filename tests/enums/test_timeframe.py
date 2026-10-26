from __future__ import annotations

import re

import pytest

from pfund_blocks.enums.timeframe import _TIMEFRAME_ALIASES, Timeframe

ALL_ALIASES = [
    (alias, Timeframe[name])
    for name, aliases in _TIMEFRAME_ALIASES.items()
    for alias in aliases
]


class TestAliases:
    @pytest.mark.parametrize("alias, expected", ALL_ALIASES)
    def test_alias_resolves(self, alias: str, expected: Timeframe):
        assert Timeframe(alias) is expected

    def test_every_member_has_aliases(self):
        assert {timeframe for _, timeframe in ALL_ALIASES} == set(Timeframe)

    def test_alias_is_case_insensitive(self):
        assert Timeframe("MINUTE") is Timeframe.MINUTE
        assert Timeframe("Mo") is Timeframe.MONTH

    def test_uppercase_m_is_minute_not_month(self):
        assert Timeframe("M") is Timeframe.MINUTE

    def test_int_value_resolves(self):
        assert Timeframe(60) is Timeframe.MINUTE
        assert Timeframe(-2) is Timeframe.QUOTE

    @pytest.mark.parametrize("value", ["x", "", "minutely", 2])
    def test_invalid_value_raises(self, value: object):
        with pytest.raises(ValueError):
            Timeframe(value)

    def test_member_aliases(self):
        assert Timeframe.m is Timeframe.MINUTE
        assert Timeframe.mo is Timeframe.MONTH


class TestPattern:
    @pytest.mark.parametrize("alias", [alias for alias, _ in ALL_ALIASES])
    def test_pattern_matches_alias(self, alias: str):
        assert re.fullmatch(f"({Timeframe.pattern()})", alias)

    def test_pattern_rejects_unknown(self):
        assert not re.fullmatch(f"({Timeframe.pattern()})", "x")


class TestRotation:
    def test_order_is_finest_to_coarsest(self):
        assert list(Timeframe) == [
            Timeframe.QUOTE,
            Timeframe.TICK,
            Timeframe.SECOND,
            Timeframe.MINUTE,
            Timeframe.HOUR,
            Timeframe.DAY,
            Timeframe.WEEK,
            Timeframe.MONTH,
            Timeframe.YEAR,
        ]

    def test_higher(self):
        assert Timeframe.MINUTE.higher() is Timeframe.HOUR
        assert Timeframe.QUOTE.higher() is Timeframe.TICK
        assert Timeframe.MONTH.coarser() is Timeframe.YEAR

    def test_higher_stops_at_year(self):
        assert Timeframe.YEAR.higher() is Timeframe.YEAR

    def test_lower(self):
        assert Timeframe.HOUR.lower() is Timeframe.MINUTE
        assert Timeframe.SECOND.lower() is Timeframe.TICK
        assert Timeframe.TICK.finer() is Timeframe.QUOTE

    def test_lower_stops_at_quote(self):
        assert Timeframe.QUOTE.lower() is Timeframe.QUOTE


class TestPredicates:
    @pytest.mark.parametrize("timeframe", list(Timeframe))
    def test_exactly_one_predicate_is_true(self, timeframe: Timeframe):
        predicates = [
            timeframe.is_quote(),
            timeframe.is_tick(),
            timeframe.is_second(),
            timeframe.is_minute(),
            timeframe.is_hour(),
            timeframe.is_day(),
            timeframe.is_week(),
            timeframe.is_month(),
            timeframe.is_year(),
        ]
        assert predicates.count(True) == 1
        assert getattr(timeframe, f"is_{timeframe.name.lower()}")()


class TestStrings:
    @pytest.mark.parametrize(
        "timeframe, canonical",
        [
            (Timeframe.QUOTE, "q"),
            (Timeframe.TICK, "t"),
            (Timeframe.SECOND, "s"),
            (Timeframe.MINUTE, "m"),
            (Timeframe.HOUR, "h"),
            (Timeframe.DAY, "d"),
            (Timeframe.WEEK, "w"),
            (Timeframe.MONTH, "mo"),
            (Timeframe.YEAR, "y"),
        ],
    )
    def test_canonical_and_repr(self, timeframe: Timeframe, canonical: str):
        assert timeframe.canonical == canonical
        assert repr(timeframe) == canonical
        assert Timeframe(canonical) is timeframe

    def test_str_is_name(self):
        assert str(Timeframe.MINUTE) == "MINUTE"
