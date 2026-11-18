"""From what `payslip_parser` reads to AmonHen's own types, at the edge.

The parser is a pure library (bytes in, a validated document out, or a `ParseError` that
says what does not balance), so it is called here directly and is not a port. None of its
types crosses this module: the use cases see `PayslipContribution` and `ReadStatement`.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import payslip_parser

from amonhen.core.portfolio import StatementOperation
from amonhen.ports.portfolio import FetchedDocument, PayslipContribution, ReadStatement

Parse = Callable[[bytes], "payslip_parser.Document"]


def read_document(source_id: int, kind: str, pdf: bytes, parse: Parse = payslip_parser.parse) -> FetchedDocument:
    """Read one document of ``kind``; a refusal comes back as an error, never as a guess."""
    try:
        document = parse(pdf)
    except payslip_parser.ParseError as exc:
        return FetchedDocument(source_id, kind, error=f"{type(exc).__name__}: {exc}")
    if kind == "busta_paga" and isinstance(document, payslip_parser.Payslip):
        return FetchedDocument(source_id, kind, layout=document.layout, payslip=contribution(source_id, document))
    if kind == "prospetto" and isinstance(document, payslip_parser.PensionStatement):
        return FetchedDocument(source_id, kind, layout=document.layout, statement=statement(source_id, document))
    return FetchedDocument(
        source_id, kind, layout=document.layout,
        error=f"il documento è un {type(document).__name__}, non un {kind}: tipo sbagliato in Paperless",
    )


def contribution(source_id: int, payslip: "payslip_parser.Payslip") -> PayslipContribution:
    """What the payslip withheld for the fund; zero when it carries no pension flows."""
    pension = payslip.pension
    zero = Decimal(0)
    return PayslipContribution(
        reference=f"paperless:{source_id}",
        period=f"{payslip.period.year:04d}-{payslip.period.month:02d}",
        own=pension.employee_contribution if pension else zero,
        employer=pension.employer_contribution if pension else zero,
        tfr=pension.tfr_to_fund if pension else zero,
    )


def statement(source_id: int, document: "payslip_parser.PensionStatement") -> ReadStatement:
    """The statement's contribution operations, matched later against the payslips by their amount.

    The amount is what was contributed (own, employer, TFR), the figure a payslip withholds;
    the fees the fund takes are in the units it assigns, not in the match.
    """
    operations = []
    for index, op in enumerate(document.operations):
        amount = op.employee + op.employer + op.tfr
        if amount <= 0:
            continue  # a switch, a fee or a withdrawal: not a contribution to match
        operations.append(StatementOperation(op.valuation_date, amount, op.nav, op.units, f"paperless:{source_id}:{index}"))
    return ReadStatement(year=document.year, operations=tuple(operations), units_end=document.units_end)
