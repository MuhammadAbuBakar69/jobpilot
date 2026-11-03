import pytest

from jobpilot import db
from jobpilot.extract import parse_heuristic

POSTING = (
    "Frontend Developer at Acme\nLocation: Remote\nSalary: USD 4000 - 6000\n"
    "Stack: React, TypeScript, Node.js\nhttps://acme.example/jobs/1"
)


@pytest.fixture()
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_add_and_list(conn):
    record = parse_heuristic(POSTING).to_dict()
    new_id = db.add(conn, record)
    assert new_id is not None
    rows = db.list_applications(conn)
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["status"] == "applied"


def test_duplicate_posting_is_rejected(conn):
    record = parse_heuristic(POSTING).to_dict()
    assert db.add(conn, record) is not None
    assert db.add(conn, record) is None
    assert len(db.list_applications(conn)) == 1


def test_update_status(conn):
    new_id = db.add(conn, parse_heuristic(POSTING).to_dict())
    assert db.update_status(conn, new_id, "interview") is True
    assert db.list_applications(conn, status="interview")[0]["id"] == new_id


def test_unknown_status_raises(conn):
    with pytest.raises(ValueError):
        db.update_status(conn, 1, "hired")


def test_summary_counts_and_response_rate(conn):
    first = db.add(conn, parse_heuristic(POSTING).to_dict())
    db.add(conn, parse_heuristic("Backend Developer at Beta\nhttps://beta.example/jobs/7").to_dict())
    db.update_status(conn, first, "rejected")
    data = db.summary(conn)
    assert data["total"] == 2
    assert data["by_status"]["rejected"] == 1
    assert data["response_rate"] == 50.0
    assert data["top_skills"]
