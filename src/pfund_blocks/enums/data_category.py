from enum import StrEnum


class DataCategory(StrEnum):
    """The kind of data, declared by each data class (e.g. MarketData.category), shared by pfeed and pfund."""

    MARKET_DATA = "MARKET_DATA"
    # NEWS_DATA = "NEWS_DATA"
