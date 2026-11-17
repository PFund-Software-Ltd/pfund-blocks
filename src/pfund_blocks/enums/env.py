from enum import StrEnum


class Environment(StrEnum):
    BACKTEST = "BACKTEST"
    SANDBOX = "SANDBOX"
    PAPER = "PAPER"
    LIVE = "LIVE"

    def is_simulated(self) -> bool:
        return self in (Environment.BACKTEST, Environment.SANDBOX)
