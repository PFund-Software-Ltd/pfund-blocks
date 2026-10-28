from enum import StrEnum


class PublicChannel(StrEnum):
    orderbook = quote = "orderbook"
    tradebook = tick = "tradebook"
    candlestick = kline = "candlestick"


class PrivateChannel(StrEnum):
    balance = "balance"
    position = "position"
    order = "order"
    trade = "trade"


class Channel(StrEnum):
    orderbook = quote = PublicChannel.orderbook
    tradebook = tick = PublicChannel.tradebook
    candlestick = kline = PublicChannel.candlestick
    balance = PrivateChannel.balance
    position = PrivateChannel.position
    order = PrivateChannel.order
    trade = PrivateChannel.trade


class ChannelType(StrEnum):
    public = "public"
    private = "private"
