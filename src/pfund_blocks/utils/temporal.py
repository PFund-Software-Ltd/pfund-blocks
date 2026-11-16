from __future__ import annotations

from typing import Literal, NamedTuple

from datetime import UTC, datetime, timedelta

NS_PER_SECOND = 1_000_000_000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class Timestamp(NamedTuple):
    value: int  # nanoseconds since epoch
    source: str | Literal['pfund']  # trading venue, or "pfund" if it is generated internally


def ns_to_dt(ts: int) -> datetime:
    # NOTE: datetime has no nanoseconds, so this truncates to microseconds
    return _EPOCH + timedelta(microseconds=ts // 1_000)
