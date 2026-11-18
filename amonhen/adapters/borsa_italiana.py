"""The pension fund's unit value from the public page of its class on Borsa Italiana.

Read once a month. A page that does not parse, that names another class, or whose last
value is not of the month asked for is a `NavUnavailable`: the app then asks a person for
the value, and never reuses another month's. The class matters — classes of the same
sub-fund have different fees and so different unit values.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from decimal import Decimal, InvalidOperation

import requests

from amonhen.ports.portfolio import NavUnavailable

PAGE = "https://www.borsaitaliana.it/borsa/fondi/dettaglio/{page}.html?lang=it"


def read_page(text: str) -> tuple[Decimal, dt.date, str]:
    """The last unit value, its date and the class the page states, or ValueError.

    The page prints a table whose headers are *Ultima, Precedente, Valuta, Data, Variazione*
    followed by their values, and further down *Classe* followed by the class.
    """
    plain = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
    cells = [html.unescape(cell).strip() for cell in re.split(r"<[^>]+>", plain)]
    cells = [cell for cell in cells if cell and cell != "\xa0"]
    headers = ["Ultima", "Precedente", "Valuta", "Data", "Variazione"]
    for index in range(len(cells) - 9):
        if cells[index:index + 5] == headers:
            last, _, _, day = cells[index + 5:index + 9]
            break
    else:
        raise ValueError("la tabella Ultima / Data non c'è")
    try:
        klass = cells[cells.index("Classe") + 1]
        value = Decimal(last.replace(".", "").replace(",", "."))
        date = dt.datetime.strptime(day, "%d/%m/%y").date()
    except (ValueError, IndexError, InvalidOperation) as exc:
        raise ValueError(f"la pagina non si legge: {exc}") from exc
    return value, date, klass


class BorsaItalianaNav:
    """The `NavSource` port over the public fund pages."""

    def __init__(self, session: requests.Session | None = None, timeout: float = 30) -> None:
        self.http = session or requests.Session()
        self.timeout = timeout

    def unit_value(self, page: str, fund_class: str, month: str) -> Decimal:
        try:
            response = self.http.get(PAGE.format(page=page), timeout=self.timeout)
            response.raise_for_status()
            value, date, klass = read_page(response.text)
        except (requests.RequestException, ValueError) as exc:
            raise NavUnavailable(f"la pagina {page} non si legge: {exc}") from exc
        if klass.strip().upper() != fund_class.strip().upper():
            raise NavUnavailable(f"la pagina {page} è della classe {klass}, non della {fund_class}")
        if f"{date.year:04d}-{date.month:02d}" != month:
            raise NavUnavailable(f"la pagina dà il valore del {date.isoformat()}, non di {month}")
        return value
