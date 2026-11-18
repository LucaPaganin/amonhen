"""The composition root: where the concrete implementations are chosen.

This is the only module that knows both sides: the ports the application speaks
(`amonhen.ports`) and the adapters that implement them. The API and the command
line get their bank from here and from nowhere else, and a test swaps it here —
`app.dependency_overrides[bank_factory]` for the API, `cli.bank_provider` for the
command line — instead of patching whatever function happened to build a client.

Lifetime: a provider is built for one run (one request, one pass of the sync
loop, one command), from the configuration read for that run. Nothing here is a
process-wide singleton, because `accounts.json` can change while the server runs
(the first-setup wizard writes it) and the next run must see the new file.
"""
from __future__ import annotations

from collections.abc import Callable

from amonhen.adapters.enable_banking import EnableBankingClient, EnableBankingProvider
from amonhen.config import MonitorConfig
from amonhen.ports.bank import BankProvider
from amonhen.ports.portfolio import DocumentSource, NavSource

BankFactory = Callable[[MonitorConfig], BankProvider]


def enable_banking_client(config: MonitorConfig) -> EnableBankingClient:
    """The Enable Banking client itself, for the consent flow the port leaves out.

    Reading the private key happens here: a missing or unreadable key raises
    `OSError` or `ValueError`, which the callers report as "cannot sync yet".
    """
    return EnableBankingClient(
        application_id=config.application_id,
        pem_path=config.pem_path,
        redirect_url=config.redirect_url,
    )


def bank_provider(config: MonitorConfig) -> BankProvider:
    """The bank the sync and the `balances` command speak to."""
    return EnableBankingProvider(enable_banking_client(config), own_names=config.own_names)


def bank_factory() -> BankFactory:
    """FastAPI dependency: how a route gets a bank for the configuration it read.

    It hands over the factory, not a provider, because the route reads the
    configuration itself and answers 503 when it cannot: building the provider
    has to happen inside that same `try`.
    """
    return bank_provider


def document_source() -> DocumentSource | None:
    """Paperless, when its address and token are configured; None otherwise."""
    from amonhen import settings
    from amonhen.adapters.paperless import PaperlessDocuments

    if not (settings.PAPERLESS_URL and settings.PAPERLESS_TOKEN):
        return None
    return PaperlessDocuments(settings.PAPERLESS_URL, settings.PAPERLESS_TOKEN, {
        "busta_paga": settings.PAPERLESS_PAYSLIP_TYPE, "prospetto": settings.PAPERLESS_STATEMENT_TYPE})


def nav_source() -> NavSource:
    """The fund's unit value from the public page of its class."""
    from amonhen.adapters.borsa_italiana import BorsaItalianaNav

    return BorsaItalianaNav()
