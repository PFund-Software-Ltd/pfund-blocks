from __future__ import annotations

from typing import Annotated, Any

import time

from msgspec import Meta, Struct, field, structs


# NOTE: kw_only is not inherited and frozen must be repeated for type checkers, subclasses must set both
class BaseDataPoint(
    Struct,
    kw_only=True,
    frozen=True,
    omit_defaults=True,
    forbid_unknown_fields=True,
    array_like=False,  # NOTE: setting array_like=True will boost performance by 1.5-2x
    gc=True,  # OPTIMIZE: consider setting gc=False for performance boost (but then you can't use lists, dicts etc.)
    tag=True,
):
    """A single point of market data, e.g. a bar or a tick."""

    # timestamps below are int64 ns since epoch; gt-bound catches passing seconds by mistake
    server_ts: Annotated[int, Meta(gt=10_000_000_000)] | None = None  # when the server (venue or data source) sent this update
    created_at: int = field(default_factory=time.time_ns)  # stamped automatically by our system, don't set it manually

    def to_dict(self) -> dict[str, Any]:
        return structs.asdict(self)
