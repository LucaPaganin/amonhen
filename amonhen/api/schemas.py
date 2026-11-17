"""The request bodies the API accepts, one Pydantic model per shape."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CategoryRequest(BaseModel):
    category: str


class NotesRequest(BaseModel):
    """The local note of a movement: the only field the app may write on it."""

    notes: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["confirm", "reject"]


class TransferPassthroughRequest(BaseModel):
    transaction_id: int
    destination: str


class TransferPairRequest(BaseModel):
    leg_a: int
    leg_b: int


class TransferUnlinkRequest(BaseModel):
    transaction_id: int


class RuleRequest(BaseModel):
    """A rule to write. `category` is the old form of `target` for a category rule.

    `id` changes that rule; without it, a rule with the same text and conditions
    is the one changed. The amounts are sizes, as text, so "12,50" reads too.
    """

    pattern: str
    action: str = "category"
    target: str | None = None
    category: str | None = None
    account_id: int | None = None
    amount_min: str | None = None
    amount_max: str | None = None
    id: int | None = None


class RuleRemoveRequest(BaseModel):
    """The rule to drop: by id, or by the text of a rule without conditions."""

    pattern: str | None = None
    id: int | None = None


class TransactionIdsRequest(BaseModel):
    ids: list[int]


class BatchCategoryRequest(BaseModel):
    ids: list[int]
    category: str


class BatchTagRequest(BaseModel):
    ids: list[int]
    tag: str


class TagsRequest(BaseModel):
    tags: list[str]


class CategoryNameRequest(BaseModel):
    name: str


class CategoryFlagsRequest(BaseModel):
    name: str | None = None
    episodic: bool | None = None
    essential: bool | None = None
    income: bool | None = None
    contribution: bool | None = None
    description: str | None = None


class AccountFlagsRequest(BaseModel):
    investment: bool | None = None
    reimport_deleted: bool | None = None
    computed_balance: bool | None = None
    unreported_funding: bool | None = None


class SplitItem(BaseModel):
    category: str
    amount: str


class SplitsRequest(BaseModel):
    splits: list[SplitItem]


class AccountRequest(BaseModel):
    name: str
    institution: str | None = None
    currency: str | None = None
    opening_balance: str | None = None
    opening_date: str | None = None


class DeclarationRequest(BaseModel):
    """A balance read off the bank, and which of its two figures it is."""

    date: str
    balance: str
    kind: Literal["available", "booked"] = "available"


class ValuationRequest(BaseModel):
    """What an investment account is worth on a day: cash and securities together."""

    date: str
    value: str


class BudgetRequest(BaseModel):
    amount: str | None = None


class BudgetItemRequest(BaseModel):
    """A planned expense, whole: an edit may move it to another month or category.

    Without `category_id` a category rule matching the description assigns one,
    or the item waits in the month's `unassigned`.
    """

    category_id: int | None = None
    month: str
    description: str
    amount: str
    date: str | None = None
    priority: Literal["essential", "important", "deferrable"] = "important"
    note: str | None = None


class BudgetCopyRequest(BaseModel):
    from_month: str
    to_month: str


class SuggestionDecisionRequest(BaseModel):
    merchant: str
    decision: Literal["accept", "dismiss"]
    # The category a person chose instead of the proposed one. Absent (or empty)
    # means the proposal was right; on a dismissal it is not read at all.
    category: str | None = None
    # The text of a rule to write for this merchant, when one was asked for.
    # Absent means the decision is about the movements alone: `rules` is not
    # touched, and the next movements of that merchant come back to the queue.
    rule: str | None = None


class SetupCredentialsRequest(BaseModel):
    """The Enable Banking credentials the first-setup screen collected.

    `private_key` is the pasted PEM, present only when the key is being written.
    Where it goes is not the caller's to choose: it is `pem_path` on the file, or
    `./private.pem` beside it, which is also what the Enable Banking client and
    the container's `/config` mount expect.
    """

    application_id: str
    redirect_url: str
    account_holder_name: str | None = None
    private_key: str | None = None


class SetupConnectRequest(BaseModel):
    bank: str
    country: str = "IT"


class SetupAccountRequest(BaseModel):
    name: str
    start_sync_date: str | None = None


class CsvMapping(BaseModel):
    """The column map the import screen built, one field per choice it offered.

    An empty column means "not chosen": a statement carries either one signed
    amount column or a debit and a credit pair, and the half left blank is what
    the preview reports back as a problem.
    """

    delimiter: str = Field(",", min_length=1, max_length=1)
    skip_rows: int = Field(0, ge=0)
    date_column: str = ""
    date_format: str = "%Y-%m-%d"
    amount_column: str = ""
    debit_column: str = ""
    credit_column: str = ""
    decimal_separator: Literal[".", ","] = "."
    description_columns: list[str] = []
    external_id_column: str = ""
    invert_sign: bool = False


class PeriodSyncRequest(BaseModel):
    """One connected account over a period a person chose, both days included."""

    model_config = ConfigDict(populate_by_name=True)

    account_id: int
    date_from: str = Field(alias="from")
    date_to: str = Field(alias="to")
    preview: bool = False


class CsvImportRequest(BaseModel):
    """A statement pasted as text, the account it belongs to, and its map."""

    filename: str = ""
    content: str
    account: str
    mapping: CsvMapping


class GoalRequest(BaseModel):
    """A goal from `valid_from` on; with `series`, a new version of that goal."""

    series: int | None = None
    name: str
    amount: str
    target_date: str
    liquidity: str
    valid_from: str


class ProfileFactRequest(BaseModel):
    value: str
    valid_from: str


class TaxParameterRequest(BaseModel):
    value: str
    source: str


class AllocationRequest(BaseModel):
    fund: str
    pac: str


class ComparisonRequest(BaseModel):
    """Two allocations a person wrote, a year each, at one annual return they wrote."""

    series: int
    return_rate: str
    allocations: list[AllocationRequest] = Field(min_length=2, max_length=2)


class ScenarioRequest(BaseModel):
    real_return: str
    inflation: str


class ProjectionRequest(BaseModel):
    """The capital already there and the monthly payment, both written for the run and never stored.

    Without `monthly` the pace is the one the ledger shows over the 12 complete months.
    `scenario` is the one Coast FI is read in.
    """

    start: str = "0"
    monthly: str | None = None
    scenario: str
