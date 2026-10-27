from pfund_blocks.entities.products.fund.fund_product import BaseFundProduct


class MutualFundProduct(BaseFundProduct):
    """A mutual fund, bought and sold at the NAV computed once a day after the close, e.g. VFIAX."""
