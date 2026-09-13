"""The API behind a real uvicorn server, which is how the PWA reaches it.

TestClient reuses worker threads and hides the fact that a connection must be
created, used and closed on one thread; a real server does not, so this is
where that class of bug has to be caught.
"""
import datetime as dt
import socket
import threading
import time
from decimal import Decimal

import httpx
import pytest
import uvicorn

from amonhen.api import API_VERSION, create_app
from amonhen.db import open_ledger_db
from amonhen.ledger import Ledger
from amonhen.models import Account, IncomingTransaction


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    db_path = tmp_path / "ledger.db"
    app = create_app(db_path, web_dist=tmp_path / "missing")
    config = uvicorn.Config(app, host="127.0.0.1", port=free_port(), log_level="warning")
    running = uvicorn.Server(config)
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not running.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not running.started:
        raise RuntimeError("the API server did not start")
    port = running.servers[0].sockets[0].getsockname()[1]

    conn = open_ledger_db(db_path)
    ledger = Ledger(conn)
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(
        IncomingTransaction(
            account_id=account,
            date=dt.date(2026, 9, 1),
            amount=Decimal("-12.30"),
            description="EKOM | Cart",
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            raw={},
        )
    )
    conn.close()

    yield f"http://127.0.0.1:{port}"
    running.should_exit = True
    thread.join(timeout=10)


def test_health_over_a_real_server(server):
    response = httpx.get(f"{server}/api/health", timeout=10)

    assert response.status_code == 200
    # The version travels with the health check: the app uses it to refuse a
    # server older than the response shapes it reads. The test follows the
    # constant rather than a literal, or every bump would just edit a number.
    assert response.json() == {
        "status": "ok",
        "api_version": API_VERSION,
        "uncategorized": "Uncategorized",
    }


def test_repeated_requests_across_thread_pool_workers(server):
    for _ in range(10):
        response = httpx.get(f"{server}/api/transactions", timeout=10)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1

    review = httpx.get(f"{server}/api/review", timeout=10)
    assert review.status_code == 200
    assert [item["merchant"] for item in review.json()["uncategorized"]] == ["EKOM"]


def test_a_category_can_be_set_over_http(server):
    transaction_id = httpx.get(f"{server}/api/transactions", timeout=10).json()["items"][0]["id"]

    response = httpx.post(
        f"{server}/api/transactions/{transaction_id}/category",
        json={"category": "Groceries"},
        timeout=10,
    )

    assert response.status_code == 200
    assert response.json()["category"] == "Groceries"
    spend = httpx.get(
        f"{server}/api/transactions", params={"category": "Groceries"}, timeout=10
    ).json()
    assert spend["total"] == 1
