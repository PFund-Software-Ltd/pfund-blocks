from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pfund_blocks.entities.products.product_base import BaseProduct


class StockMixin:
    def _create_symbol(self: StockMixin | BaseProduct) -> str:
        return self.base_asset
