"""Current beta product-truth gates for Help Center/RAG.

These gates keep future/implemented-but-disabled capabilities out of customer-facing
Loomi retrieval without deleting their documentation from the repository.
"""

BETA_PAYMENT_MODE = "pay_at_salon_only"

BETA_INACTIVE_HELP_ARTICLE_KEYS = frozenset(
    {
        "customer.wallet.overview",
        "customer.wallet.disabled",
        "customer.wallet.charge",
        "customer.wallet.transactions",
        "customer.wallet.withdraw",
        "customer.booking.pay-in-salon",
        "customer.payment.pending-review",
        "customer.payment.expired",
    }
)
