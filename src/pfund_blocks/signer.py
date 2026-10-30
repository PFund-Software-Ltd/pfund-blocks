from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pfund_blocks.entities.accounts.account_base import BaseAccount
    from pfund_blocks.typing import Request


class RequestSigner[AccountT: BaseAccount](Protocol):
    def sign(self, request: Request, account: AccountT) -> Request:
        """Returns a new signed request (e.g. via dataclasses.replace), the input request is left unchanged.

        e.g. Bybit adds the X-BAPI-* headers and sets content to the signed body,
        Hyperliquid adds the nonce and signature into the body.
        """
        ...
