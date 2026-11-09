"""Tests that ingest.py does what rules.md says. rules.md is the only source of truth.

Safety: every test works in its own temporary folder, on a database named test.db
and a log named test-ingestion-log.json. ingest.py is pointed at those files for
the length of the test, and the folder is deleted afterward, pass or fail. A guard
stops any test that tries to open a different database, and another fails the run
if the books.db or ingestion-log.json next to this file change.

Run with:  python -m pytest -v test_ingest.py
"""

import csv
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

import pytest

import ingest

HERE = Path(__file__).resolve().parent
BOOKS = HERE / "books.csv"
BATCH2 = HERE / "books-batch2.csv"
REAL_FILES = [HERE / "books.db", HERE / "ingestion-log.json"]
REAL_CONNECT = sqlite3.connect

CSV_COLUMNS = [
    "book_id", "goodreads_book_id", "best_book_id", "work_id", "books_count",
    "isbn", "isbn13", "authors", "original_publication_year", "original_title",
    "title", "language_code", "average_rating", "ratings_count",
    "work_ratings_count", "work_text_reviews_count", "ratings_1", "ratings_2",
    "ratings_3", "ratings_4", "ratings_5", "image_url", "small_image_url",
]


# ---------------------------------------------------------------------------
# Setup and teardown
# ---------------------------------------------------------------------------

def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@pytest.fixture(scope="session", autouse=True)
def real_files_are_untouched():
    """Fail the whole run if a test changed, created or removed a real file."""
    before = {path: fingerprint(path) for path in REAL_FILES}
    yield
    changed = [path.name for path in REAL_FILES if fingerprint(path) != before[path]]
    assert not changed, f"The tests touched real files: {changed}"


class Sandbox:
    """One test's private folder, and helpers for running ingest.py inside it."""

    def __init__(self, folder, monkeypatch):
        self.folder = folder
        self.db = folder / "test.db"
        self.log = folder / "test-ingestion-log.json"
        self.monkeypatch = monkeypatch
        self.connections = []

    def connect(self, database, *args, **kwargs):
        """Stands in for sqlite3.connect: allows only this test's test.db, and
        remembers each connection so teardown can close it even after a crash."""
        if Path(database).resolve() != self.db:
            raise AssertionError(f"Refused to open {database}: tests may only use test.db")
        connection = REAL_CONNECT(database, *args, **kwargs)
        self.connections.append(connection)
        return connection

    def close_connections(self):
        for connection in self.connections:
            connection.close()
        self.connections.clear()

    def reset(self):
        """Back to an empty database and no log."""
        self.close_connections()
        self.db.unlink(missing_ok=True)
        self.log.unlink(missing_ok=True)

    def write_csv(self, rows):
        path = self.folder / "input.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def run(self, csv_path):
        """Run a load the way Decision 32 describes: python ingest.py <file.csv>."""
        self.monkeypatch.setattr(sys, "argv", ["ingest.py", str(csv_path)])
        try:
            ingest.main()
        except SystemExit as stop:
            if stop.code not in (None, 0):
                pytest.fail(f"The load stopped: {stop.code}")
        finally:
            self.close_connections()

    def run_expecting_failure(self, csv_path):
        self.monkeypatch.setattr(sys, "argv", ["ingest.py", str(csv_path)])
        try:
            ingest.main()
        except SystemExit:
            pass
        finally:
            self.close_connections()

    def rows(self, table):
        connection = self.connect(self.db)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
        finally:
            connection.close()

    def warning_count(self):
        return len(self.rows("warnings"))

    def log_entries(self):
        return json.loads(self.log.read_text(encoding="utf-8"))


@pytest.fixture
def sandbox(monkeypatch):
    folder = Path(tempfile.mkdtemp(prefix="ingest-test-")).resolve()
    box = Sandbox(folder, monkeypatch)
    try:
        monkeypatch.setattr(ingest, "DB_PATH", box.db)
        monkeypatch.setattr(ingest, "LOG_PATH", box.log)
        monkeypatch.setattr(sqlite3, "connect", box.connect)
        yield box
    finally:
        box.close_connections()
        shutil.rmtree(folder)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

def book_row(title, isbn, isbn13, number=1):
    """A row where only the ISBNs can cause trouble. The other columns are made
    up but consistent: the star counts sum to 1350 and average 4.08, so
    Decision 23's recalculation has nothing to warn about."""
    return {
        "book_id": number, "goodreads_book_id": 1000 + number,
        "best_book_id": 1000 + number, "work_id": 2000 + number, "books_count": 1,
        "isbn": isbn, "isbn13": isbn13, "authors": f"Test Author {number}",
        "original_publication_year": 2000, "original_title": title, "title": title,
        "language_code": "eng", "average_rating": "4.08", "ratings_count": 1350,
        "work_ratings_count": 1350, "work_text_reviews_count": 140,
        "ratings_1": 20, "ratings_2": 60, "ratings_3": 250, "ratings_4": 480,
        "ratings_5": 540, "image_url": "", "small_image_url": "",
    }


# name:     the row number in rules.md's Examples table, and the book
# isbn:     the isbn cell going in (from the data file when the table names one)
# isbn13:   the isbn13 cell going in
# expected: database columns and the values the table and Database layout require
# warned:   True = must have a warning, False = must have none,
#           None = rules.md doesn't say, so it isn't checked
Example = namedtuple("Example", "name isbn isbn13 expected warned")

EXAMPLES = [
    Example("01-goblet-of-fire", "0439139600", "9780439139601",
            {"isbn": "0439139600", "isbn_status": "ok", "isbn_original": "0439139600"}, False),
    Example("02-prisoner-of-azkaban", "043965548X", "9.78043965548e+12",
            {"isbn": "043965548X", "isbn_status": "ok", "isbn_original": "043965548X"}, False),
    Example("03-hunger-games-isbn", "439023483", "9.78043902348e+12",
            {"isbn": "0439023483", "isbn_status": "repaired", "isbn_original": "439023483"}, False),
    Example("04-to-kill-a-mockingbird", "61120081", "9.78006112008e+12",
            {"isbn": "0061120081", "isbn_status": "repaired", "isbn_original": "61120081"}, False),
    Example("05-salt-and-ember", "0-450-19827-8", "9780450198274",
            {"isbn": "0450198278", "isbn_status": "repaired", "isbn_original": "0-450-19827-8"}, False),
    Example("06-field-guide-to-quiet-places", " 162 001 4750 ", "9781620014752",
            {"isbn": "1620014750", "isbn_status": "repaired", "isbn_original": " 162 001 4750 "}, False),
    Example("07-winter-orchard", "031200009x", "9780312000097",
            {"isbn": "031200009X", "isbn_status": "repaired", "isbn_original": "031200009x"}, False),
    Example("08-atlas-of-small-kindnesses", "9781982147600", "",
            {"isbn": "1982147601", "isbn13": "9781982147600", "isbn_status": "repaired",
             "isbn_original": "9781982147600"}, True),
    Example("09-cartographers-error", "", "9780062398123",
            {"isbn": "0062398121", "isbn_status": "repaired"}, False),
    # Example 10 needs two rows, so it has its own test below.
    Example("11-the-racketeer", "385535144", "9.78038553514e+12",
            {"isbn": "", "isbn_status": "rejected", "isbn_original": "385535144"}, True),
    Example("12-glass-aviary", "04390A3483", "",
            {"isbn": "", "isbn_status": "rejected", "isbn_original": "04390A3483"}, True),
    Example("13-borrowed-light", "15287463097", "",
            {"isbn": "", "isbn_status": "rejected", "isbn_original": "15287463097"}, True),
    Example("14-night-ferry", "", "9798351220413",
            {"isbn13": "9798351220413", "isbn13_status": "ok", "isbn": "",
             "isbn13_original": "9798351220413"}, False),
    Example("15-hunger-games-isbn13", "439023483", "9.78043902348e+12",
            {"isbn13": "9780439023481", "isbn13_status": "repaired",
             "isbn13_original": "9.78043902348e+12"}, False),
    Example("16-how-to-win-friends", "", "9.78067172365e+12",
            {"isbn13": "9780671723651", "isbn13_status": "inferred",
             "isbn13_original": "9.78067172365e+12"}, True),
    Example("17-watchers", "", "9.7804251888e+12",
            {"isbn13": "", "isbn13_status": "rejected",
             "isbn13_original": "9.7804251888e+12"}, True),
    Example("18-nights-in-rodanthe", "446612707", "9.78055381395e+12",
            {"isbn13": "9780446612708", "isbn13_status": "repaired",
             "isbn13_original": "9.78055381395e+12"}, True),
    # Examples 19, 20 and 29 are "moved". Decision 9's status list has no "moved",
    # so the status of a moved value isn't checked (19 and 29); 20 goes on to be repaired.
    Example("19-wait-for-you", "", "2.94001623192e+12",
            {"isbn13": "", "other_id": "2.94001623192e+12",
             "isbn13_original": "2.94001623192e+12"}, None),
    Example("20-anne-of-green-gables-box-set", "553609416", "76783609419.0",
            {"isbn13": "9780553609417", "isbn13_status": "repaired",
             "other_id": "076783609419", "isbn13_original": "76783609419.0"}, None),
    Example("21-secret-of-the-nagas", "9380658797", "97893806587.0",
            {"isbn13": "", "isbn13_status": "rejected", "isbn13_original": "97893806587.0"}, True),
    Example("22-bossypants", "", "",
            {"isbn": "", "isbn13": "", "isbn_status": "empty", "isbn13_status": "empty"}, False),
    Example("23-made-up-hyphens", "", "978-0-306-40615-7",
            {"isbn13": "9780306406157", "isbn13_status": "repaired",
             "isbn13_original": "978-0-306-40615-7"}, False),
    Example("24-made-up-wrong-check-digit", "", "9780306406158",
            {"isbn13": "", "isbn13_status": "rejected", "isbn13_original": "9780306406158"}, True),
    Example("25-made-up-fails-checksum", "1234567890", "",
            {"isbn": "", "isbn_status": "rejected", "isbn_original": "1234567890"}, True),
    Example("26-made-up-isbn-label", "ISBN 0-306-40615-2", "",
            {"isbn": "0306406152", "isbn_status": "repaired",
             "isbn_original": "ISBN 0-306-40615-2"}, False),
    Example("27-manual-urn-label", "", "URN:ISBN:978-92-95055-12-4",
            {"isbn13": "9789295055124", "isbn13_status": "repaired",
             "isbn13_original": "URN:ISBN:978-92-95055-12-4"}, False),
    Example("28-manual-format-label", "", "ISBN 978-951-45-9693-3 (hardback)",
            {"isbn13": "9789514596933", "isbn13_status": "repaired",
             "isbn13_original": "ISBN 978-951-45-9693-3 (hardback)"}, False),
    Example("29-made-up-ismn", "", "9790007672393",
            {"isbn13": "", "other_id": "9790007672393",
             "isbn13_original": "9790007672393"}, None),
    Example("30-made-up-price-code", "", "978-92-95055-12-4 90000",
            {"isbn13": "", "isbn13_status": "rejected",
             "isbn13_original": "978-92-95055-12-4 90000"}, True),
]


def check_columns(book, expected):
    for column, value in expected.items():
        assert column in book, f"books has no column named {column} (Database layout)"
        # rules.md says "empty" without choosing between NULL and blank text.
        assert (book[column] or "") == value, f"{column}: got {book[column]!r}, expected {value!r}"


# ---------------------------------------------------------------------------
# The Examples table in rules.md
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.name)
def test_examples_table(sandbox, example):
    sandbox.run(sandbox.write_csv([book_row(example.name, example.isbn, example.isbn13)]))

    books = sandbox.rows("books")
    assert len(books) == 1, "A bad ISBN must not stop the book from loading (Rule 8)"
    check_columns(books[0], example.expected)

    if example.warned is True:
        assert sandbox.warning_count() >= 1, "The table or Rule 8 requires a warning"
    elif example.warned is False:
        assert sandbox.warning_count() == 0, "The table lists no warning for this example"


def test_example_10_paper_moons_shares_angels_and_demons_isbn(sandbox):
    """Valid, but it's also Angels & Demons' ISBN, so both rows get a warning (Rule 7)."""
    sandbox.run(sandbox.write_csv([
        book_row("Angels & Demons", "1416524797", "9.78141652479e+12", number=1),
        book_row("Paper Moons", "1416524797", "", number=2),
    ]))

    books = {book["title"]: book for book in sandbox.rows("books")}
    assert len(books) == 2, "Both books must load"
    check_columns(books["Paper Moons"], {
        "isbn": "1416524797", "isbn_status": "ok", "isbn_original": "1416524797"})
    assert sandbox.warning_count() >= 2, "Both rows must get a warning"


# ---------------------------------------------------------------------------
# Loading the same file twice (Rule 12, step 5)
# ---------------------------------------------------------------------------

def test_running_the_same_file_twice_creates_no_duplicates(sandbox):
    sandbox.run(BATCH2)
    first = sandbox.rows("books")
    sandbox.run(BATCH2)
    second = sandbox.rows("books")

    # 31 rows in the file, and book 10001 appears twice (Rule 12, step 5).
    assert len(first) == 30
    assert len(second) == 30, "The second load added books"
    work_ids = [book["work_id"] for book in second]
    assert len(set(work_ids)) == len(work_ids), "A work_id appears more than once"
    assert second == first, "The second load changed a stored book"


# ---------------------------------------------------------------------------
# The log (Decisions 4 and 28)
# ---------------------------------------------------------------------------

def test_every_run_adds_a_log_entry_without_overwriting_earlier_ones(sandbox):
    sandbox.run(BATCH2)
    after_first = sandbox.log_entries()
    assert isinstance(after_first, list), "The log must be one JSON array (Decision 28)"
    assert len(after_first) == 1

    sandbox.run(BATCH2)
    after_second = sandbox.log_entries()
    assert len(after_second) == 2
    assert after_second[0] == after_first[0], "The earlier entry changed"


def test_a_failed_run_also_adds_a_log_entry(sandbox):
    """Decision 4: a missing file fails the run, and failed runs get a log entry."""
    sandbox.run(BATCH2)
    after_first = sandbox.log_entries()

    sandbox.run_expecting_failure(sandbox.folder / "this-file-does-not-exist.csv")
    after_failure = sandbox.log_entries()
    assert len(after_failure) == 2
    assert after_failure[0] == after_first[0], "The earlier entry changed"


# ---------------------------------------------------------------------------
# The counts add up (Rule 13, Decisions 1 and 2)
# ---------------------------------------------------------------------------

def rows_in_file(path):
    with open(path, encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_loaded_updated_skipped_and_rejected_add_up_to_rows_read(sandbox):
    """Rule 13: the total has to equal the number of rows in the file. rules.md
    doesn't name the log's count fields, so these are the names ingest.py uses,
    as agreed for this test."""
    sandbox.run(BOOKS)
    sandbox.run(BATCH2)

    entries = sandbox.log_entries()
    assert len(entries) == 2
    for entry, path in zip(entries, (BOOKS, BATCH2)):
        counts = entry["counts"]
        total = (counts["loaded"] + counts["updated"]
                 + counts["skipped_already_exists"] + counts["rejected"])
        assert counts["read"] == rows_in_file(path), f"{path.name}: rows read is wrong"
        assert total == counts["read"], f"{path.name}: {counts}"


# ---------------------------------------------------------------------------
# The same file gives the same database (Decision 34)
# ---------------------------------------------------------------------------

def database_contents(sandbox):
    """Every table except runs, which also records when the run happened
    (Decision 29), a value that's supposed to differ. Rows are sorted, because
    the rules care about what's stored, not the order SQLite returns it in."""
    return {table: sorted(json.dumps(row, sort_keys=True) for row in sandbox.rows(table))
            for table in ("books", "book_sources", "history", "warnings")}


def test_same_file_on_an_empty_database_gives_the_same_database_both_times(sandbox):
    sandbox.run(BATCH2)
    first = database_contents(sandbox)

    sandbox.reset()
    sandbox.run(BATCH2)
    second = database_contents(sandbox)

    assert first["books"], "The load put no books in the database"
    assert second == first
