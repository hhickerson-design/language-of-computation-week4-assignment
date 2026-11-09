"""Load a books CSV file into books.db, following the rules in rules.md.

Usage:
    python ingest.py books.csv
    python ingest.py books-batch2.csv

books.db and ingestion-log.json are kept next to this script (Decision 32). The
CSV file is only read, never changed. No AI and no internet: the same file always
gives the same result (Decision 34). Each run is all-or-nothing (Decision 4).
"""

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

try:
    import msvcrt   # Windows
    fcntl = None
except ImportError:
    import fcntl    # Mac and Linux
    msvcrt = None

HERE =Path(__file__).resolve().parent
DB_PATH = HERE / "books.db"
LOG_PATH = HERE / "ingestion-log.json"

CSV_COLUMNS = [
    "book_id", "goodreads_book_id", "best_book_id", "work_id", "books_count",
    "isbn", "isbn13", "authors", "original_publication_year", "original_title",
    "title", "language_code", "average_rating", "ratings_count",
    "work_ratings_count", "work_text_reviews_count", "ratings_1", "ratings_2",
    "ratings_3", "ratings_4", "ratings_5", "image_url", "small_image_url",
]

# Decision 22: every column has a kind.
ID_COLUMNS = ["work_id", "goodreads_book_id", "book_id", "best_book_id"]
DESCRIPTIVE_COLUMNS = ["title", "authors", "original_publication_year", "original_title",
                       "language_code", "image_url", "small_image_url"]
STAR_COLUMNS = ["ratings_1", "ratings_2", "ratings_3", "ratings_4", "ratings_5"]
COUNT_COLUMNS = ["books_count", "work_text_reviews_count", "ratings_count"] + STAR_COLUMNS

STATUS_ORDER = ["rejected", "inferred", "repaired", "ok", "empty"]  # Decision 9, worst first

# Decision 30's groups.
DECISION, LOOKUP, CHECK = "needs_decision", "needs_lookup", "check_this"

ASSUMPTIONS = [
    "The file loaded later is treated as the newer one, because neither file says "
    "when its data was collected (Decision 6).",
]

LABEL_AT_START = re.compile(r"^(?:URN:ISBN:?|ISBN(?:-1[03])?)\s*:?\s*", re.IGNORECASE)  # Decision 8
FORMAT_AT_END = re.compile(r"\s*\([^()]*\)\s*$")                                        # Decision 8
ROUNDED = re.compile(r"^\d(?:\.\d+)?[eE]\+\d+$")                                        # Decision 10
ENDS_IN_POINT_ZERO = re.compile(r"^\d+\.0$")                                            # Decision 11


class RunFailed(Exception):
    """The file can't be used, so the run stops and nothing changes (Decision 4)."""


# ---------------------------------------------------------------------------
# ISBN arithmetic (Rules 2-4)
# ---------------------------------------------------------------------------

def valid_isbn10(value):
    if not re.fullmatch(r"\d{9}[\dX]", value):
        return False
    return sum((10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(value)) % 11 == 0


def isbn13_total(digits):
    return sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(digits))


def is_isbn13_shaped(digits):
    """Starts with 978 or 979, and isn't an ISMN for printed music (Rule 3)."""
    return digits.startswith(("978", "979")) and not digits.startswith("9790")


def valid_isbn13(value):
    return (bool(re.fullmatch(r"\d{13}", value)) and is_isbn13_shaped(value)
            and isbn13_total(value) % 10 == 0)


def isbn13_from_isbn10(isbn10):
    core = "978" + isbn10[:9]
    return core + str((10 - isbn13_total(core) % 10) % 10)


def isbn10_from_isbn13(isbn13):
    core = isbn13[3:12]
    check = (11 - sum((10 - i) * int(ch) for i, ch in enumerate(core)) % 11) % 11
    return core + ("X" if check == 10 else str(check))


def round_like_the_file(number):
    """Decision 10: nearest 10, with an exact half going to the even ten."""
    return Decimal(number).quantize(Decimal("1E1"), rounding=ROUND_HALF_EVEN)


def rounded_candidates(rounded):
    """Every valid ISBN-13 that would round to this value."""
    found = []
    for offset in range(-5, 6):
        number = str(int(rounded) + offset)
        if valid_isbn13(number) and round_like_the_file(number) == rounded:
            found.append(number)
    return found


def valid_upc(digits):
    """A 12-digit UPC, after adding back a leading zero to an 11-digit one."""
    digits = digits.zfill(12)
    return sum((3 if i % 2 == 0 else 1) * int(ch) for i, ch in enumerate(digits)) % 10 == 0


# ---------------------------------------------------------------------------
# Reading one ISBN cell (Decisions 7, 8, 10, 11, 12)
# ---------------------------------------------------------------------------

def remove_formatting(raw):
    """Decision 7's order: labels, then spaces and hyphens."""
    text = LABEL_AT_START.sub("", raw.strip())
    text = FORMAT_AT_END.sub("", text)
    return re.sub(r"[\s-]", "", text)


def read_isbn10_cell(raw):
    """Returns (kind, value). kind: empty, ok, repaired, isbn13_here or rejected."""
    if not raw.strip():
        return "empty", None
    text = remove_formatting(raw)
    if text.endswith("x"):
        text = text[:-1] + "X"
    if re.fullmatch(r"\d{0,9}X?", text) and text:
        text = text.zfill(10)                  # add back missing leading zeros
    if valid_isbn10(text):
        return ("ok" if text == raw else "repaired"), text
    if valid_isbn13(text):
        return "isbn13_here", text             # Rule 8: an ISBN-13 in the wrong column
    return "rejected", None


def read_isbn13_cell(raw, isbn10):
    """Returns (kind, value). kind: empty, ok, repaired, rounded, other, wrong_column
    or rejected. isbn10 is the row's valid ISBN-10, if it has one."""
    stripped = raw.strip()
    if not stripped:
        return "empty", None

    if ROUNDED.fullmatch(stripped):
        rounded = Decimal(stripped)
        digits = str(int(rounded))
        if len(digits) != 13:
            return "rejected", None
        if not is_isbn13_shaped(digits):
            return "other", raw                # Decision 12: rounded stays as it arrived
        return "rounded", rounded

    if ENDS_IN_POINT_ZERO.fullmatch(stripped):
        digits = stripped[:-2]
        if len(digits) != 13:                  # Decision 11
            if isbn10 and isbn10.isdigit() and int(digits) == int(isbn10):
                return "wrong_column", None
            if len(digits) in (11, 12) and valid_upc(digits):
                return "other", digits.zfill(12)
            return "rejected", None
    else:
        digits = remove_formatting(raw)
        if re.fullmatch(r"\d{11,12}", digits) and valid_upc(digits):
            return "other", digits.zfill(12)   # Decision 12
        if not re.fullmatch(r"\d{13}", digits):
            return "rejected", None

    if not is_isbn13_shaped(digits):
        return "other", digits                 # Decision 12: store IDs and ISMNs
    if isbn13_total(digits) % 10:
        return "rejected", None
    return ("ok" if digits == raw else "repaired"), digits


# ---------------------------------------------------------------------------
# Working out a row's ISBNs (Rules 4-8, Decisions 13-15)
# ---------------------------------------------------------------------------

def clean_isbns(raw10, raw13):
    """Returns the values to store and any warnings: (group, column, value, reason, action)."""
    notes = []
    other_id = None

    def note(group, column, value, reason, action):
        notes.append((group, column, value, reason, action))

    kind10, isbn10 = read_isbn10_cell(raw10)
    usable10 = isbn10 if kind10 in ("ok", "repaired") else None
    kind13, value13 = read_isbn13_cell(raw13, usable10)

    moved = None
    if kind10 == "isbn13_here":
        if kind13 == "empty":                  # Rule 8: move it, and warn
            moved, kind10, isbn10 = isbn10, "empty", None
            kind13, value13 = "repaired", moved
            note(CHECK, "isbn", raw10, "An ISBN-13 was in the isbn column, so it was moved to isbn13.",
                 "Check that this value belongs to this book.")
        else:
            kind10, isbn10 = "rejected", None

    isbn13, status13 = None, "empty"

    if usable10:
        isbn13, status13 = isbn13_from_isbn10(usable10), "repaired"
        mismatch = False
        if kind13 in ("ok", "repaired"):
            if value13 == isbn13:
                status13 = kind13
            else:
                mismatch = True
        elif kind13 == "rounded":
            mismatch = round_like_the_file(isbn13) != value13
        elif kind13 == "other":
            other_id = value13
        elif kind13 == "wrong_column":
            note(CHECK, "isbn13", raw13, "The isbn13 column held the row's ISBN-10, so the ISBN-13 "
                 "was calculated from it.", "Nothing, unless the ISBN-10 is wrong.")
        elif kind13 == "rejected":
            note(CHECK, "isbn13", raw13, "isbn13 isn't a valid ISBN, so it was calculated from the ISBN-10.",
                 "Check that the ISBN-10 belongs to this book.")
        if mismatch:
            note(DECISION, "isbn13", raw13, f"isbn13 doesn't match the ISBN-10 {usable10}, so it was "
                 f"calculated from the ISBN-10 as {isbn13}.", "Decide which ISBN is right. "
                 "The other number might be a different edition.")
        status10 = kind10
    else:
        status10 = kind10
        if kind13 in ("ok", "repaired"):
            isbn13, status13 = value13, kind13
            if isbn13.startswith("978"):
                isbn10, status10 = isbn10_from_isbn13(isbn13), "repaired"
                if kind10 == "rejected":       # Decision 13
                    note(CHECK, "isbn", raw10, f"isbn isn't valid, so it was calculated from the ISBN-13 as {isbn10}.",
                         "Check that the ISBN-13 belongs to this book.")
        elif kind13 == "rounded":
            candidates = rounded_candidates(value13)
            if len(candidates) == 1:           # Decisions 5, 14, 15
                isbn13, status13 = candidates[0], "inferred"
                note(CHECK, "isbn13", raw13, f"Rounded value inferred as {isbn13}, the only valid ISBN-13 that "
                     "rounds to it. This only works if the original was a real ISBN.",
                     "Check it, or leave out inferred values.")
            else:
                status13 = "rejected"
                note(LOOKUP, "isbn13", raw13, f"Rounded value fits {len(candidates)} valid ISBN-13s, so none was chosen.",
                     "Find the real ISBN-13.")
        elif kind13 == "other":
            other_id = value13
        elif kind13 == "rejected":
            status13 = "rejected"
            note(LOOKUP, "isbn13", raw13, "isbn13 isn't a valid ISBN and can't be calculated.", "Find the real ISBN-13.")
        if status10 == "rejected":
            note(LOOKUP, "isbn", raw10, "isbn isn't a valid ISBN and can't be calculated.", "Find the real ISBN.")

    statuses = (status10, status13)
    return {
        "isbn": isbn10 if status10 in ("ok", "repaired") else None,
        "isbn13": isbn13,
        "isbn_status": status10,
        "isbn13_status": status13,
        "isbn_original": raw10 or None,
        "isbn13_original": raw13 or None,
        "other_id": other_id,
        "isbn_row_status": next(s for s in STATUS_ORDER if s in statuses),
    }, notes


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def whole(text):
    """The whole number in a cell, or None."""
    text = (text or "").strip()
    return int(text) if re.fullmatch(r"\d+", text) else None


def as_number_or_text(text):
    """Whole-number IDs and counts are stored as numbers, anything else as it arrived."""
    number = whole(text)
    return number if number is not None else (text or None)


def as_decimal(text):
    try:
        return Decimal((text or "").strip())
    except InvalidOperation:
        return None


def clean_title(title):
    """Rule 10: lowercase, no series tag, no extra spaces."""
    title = re.sub(r"\([^()]*#[^()]*\)\s*$", "", title or "")
    return " ".join(title.lower().split())


def first_author(authors):
    return (authors or "").split(",")[0].strip().lower()


def recalculate(row):
    """Decision 23. Returns (average_rating, work_ratings_count, warning notes)."""
    stars = [whole(row[column]) for column in STAR_COLUMNS]
    file_average, file_total = row["average_rating"], row["work_ratings_count"]
    if None in stars or sum(stars) == 0:
        reason = ("A star count is missing or isn't a whole number, so the file's "
                  "average_rating and work_ratings_count were kept.")
        return (file_average or None, as_number_or_text(file_total),
                [("average_rating", file_average, reason, "Check the star counts.")])

    total = sum(stars)
    weighted = sum(star * count for star, count in enumerate(stars, start=1))
    average = (Decimal(weighted) / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    notes = []
    if file_average.strip() and as_decimal(file_average) != average:
        notes.append(("average_rating", file_average, f"File said {file_average}, star counts give {average}.",
                      "Nothing, unless the star counts are wrong."))
    if file_total.strip() and as_decimal(file_total) != total:
        notes.append(("work_ratings_count", file_total, f"File said {file_total}, star counts give {total}.",
                      "Nothing, unless the star counts are wrong."))
    return float(average), total, notes


# ---------------------------------------------------------------------------
# The input file (Decision 4)
# ---------------------------------------------------------------------------

def read_csv_file(path):
    """Returns (header, [(line, fields)], size, sha256), or raises RunFailed."""
    if not path.is_file():
        raise RunFailed(f"File not found: {path}.")
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RunFailed(f"{path.name} isn't UTF-8 text ({error}).") from error
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader, None)
        rows = [(reader.line_num, fields) for fields in reader if fields]
    except csv.Error as error:
        raise RunFailed(f"{path.name} can't be parsed as CSV ({error}).") from error
    missing = [column for column in CSV_COLUMNS if column not in (header or [])]
    if missing:
        raise RunFailed(f"{path.name} is missing expected columns: {', '.join(missing)}.")
    return header, rows, len(data), hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# The database (Database layout, Decision 21)
# ---------------------------------------------------------------------------

def create_tables(conn):
    text_columns = ["authors", "original_publication_year", "original_title", "title",
                    "language_code", "image_url", "small_image_url"]
    # IDs and counts have no declared type, so a whole number stays a number and
    # anything else stays as it arrived.
    books = ["book_key INTEGER PRIMARY KEY AUTOINCREMENT"] + ID_COLUMNS + [
        "isbn TEXT", "isbn13 TEXT", "isbn_status TEXT", "isbn13_status TEXT",
        "isbn_original TEXT", "isbn13_original TEXT", "other_id TEXT", "isbn_row_status TEXT",
        "average_rating", "work_ratings_count",
    ] + [f"{column} TEXT" for column in text_columns] + COUNT_COLUMNS + ["created_run INTEGER"]
    conn.execute(f"CREATE TABLE IF NOT EXISTS books ({', '.join(books)})")

    existing = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
    if "book_key" not in existing:
        raise RunFailed(f"{DB_PATH.name} has an older layout that this script can't update. "
                        f"Move or delete {DB_PATH.name}, then run the load again.")

    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS books_work_id ON books (work_id) "
                 "WHERE typeof(work_id) = 'integer'")
    for column in ("goodreads_book_id", "book_id", "isbn", "isbn13"):
        conn.execute(f"CREATE INDEX IF NOT EXISTS books_{column} ON books ({column})")
    conn.execute("""CREATE TABLE IF NOT EXISTS runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, file TEXT, file_path TEXT,
        full_path TEXT, file_size INTEGER, sha256 TEXT, read INTEGER, loaded INTEGER,
        updated INTEGER, skipped_already_exists INTEGER, rejected INTEGER, flagged INTEGER,
        books_before INTEGER, books_after INTEGER, isbn_status_counts TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS book_sources (
        run_id INTEGER, book_key INTEGER, line INTEGER, outcome TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS history (
        run_id INTEGER, book_key INTEGER, column_name TEXT, old_value, new_value, reason TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS warnings (
        run_id INTEGER, book_key INTEGER, warning_group TEXT, line INTEGER, column_name TEXT,
        value TEXT, reason TEXT, action TEXT)""")


# ---------------------------------------------------------------------------
# One load
# ---------------------------------------------------------------------------

class Load:
    def __init__(self, conn, run_id, file_name):
        self.conn = conn
        self.run_id = run_id
        self.file_name = file_name
        self.counts = Counter(read=0, loaded=0, updated=0, skipped_already_exists=0, rejected=0)
        self.groups = {DECISION: [], LOOKUP: [], CHECK: []}
        self.decision_issues = set()
        self.handled = Counter()
        self.status_counts = {"isbn": Counter(), "isbn13": Counter()}
        self.changes = []
        self.not_loaded = []
        self.lines_seen = {}  # book_key -> first line in this file

    # -- Recording ----------------------------------------------------------

    def warn(self, group, book, line, column, value, reason, action, issue=None):
        book_key = book["book_key"] if book else None
        self.conn.execute("INSERT INTO warnings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (self.run_id, book_key, group, line, column, value, reason, action))
        self.groups[group].append({
            "line": line, "book_key": book_key, "book_id": book["book_id"] if book else None,
            "title": book["title"] if book else None, "column": column, "value": value,
            "reason": reason, "action": action,
        })
        if group == DECISION:
            self.decision_issues.add(issue or (line, column, reason))

    def reject(self, line, book_id, title, reason):
        self.counts["rejected"] += 1
        self.not_loaded.append({"line": line, "book_id": book_id, "title": title,
                                "outcome": "rejected", "reason": reason})

    def book(self, book_key):
        return self.conn.execute("SELECT * FROM books WHERE book_key = ?", (book_key,)).fetchone()

    # -- The whole file -----------------------------------------------------

    def run(self, header, rows):
        self.counts["read"] = len(rows)
        for line, row in self.usable_rows(header, rows):
            self.load_row(line, row)
        self.warn_about_shared_isbns()

    def usable_rows(self, header, rows):
        """Decisions 1, 2, 17, 18: reject what can't be loaded at all."""
        seen = {}
        kept = []
        for line, fields in rows:
            if len(fields) != len(header):
                self.reject(line, None, None, f"Wrong number of fields: {len(fields)}, expected {len(header)}.")
                continue
            row = dict(zip(header, fields))
            key = tuple(fields)
            if key in seen:
                self.reject(line, row["book_id"], row["title"], f"exact duplicate of line {seen[key]}")
                self.handled["duplicate_rows_rejected"] += 1
                continue
            seen[key] = line
            kept.append((line, row))

        by_work_id = {}
        for line, row in kept:
            work_id = whole(row["work_id"])
            if work_id is not None:
                by_work_id.setdefault(work_id, []).append((line, row))

        conflicting = set()
        for work_id, copies in by_work_id.items():
            if len(copies) < 2:
                continue
            differing = [c for c in header if len({row[c] for _, row in copies}) > 1]
            reason = f"work_id {work_id} appears on {len(copies)} rows that differ in: {', '.join(differing)}."
            for line, row in copies:
                conflicting.add(line)
                self.reject(line, row["book_id"], row["title"], reason)
                self.warn(DECISION, None, line, "work_id", str(work_id), reason,
                          "Decide which copy is right and fix the file.", issue=("work_id", work_id))
        return [(line, row) for line, row in kept if line not in conflicting]

    # -- Matching (Rule 9, Decisions 19 and 20) -----------------------------

    def find(self, column, value):
        return self.conn.execute(f"SELECT * FROM books WHERE {column} = ?", (value,)).fetchall()

    def match(self, row, clean):
        work_id = whole(row["work_id"])
        if work_id is not None:
            found = self.find("work_id", work_id)
            return (found[0] if found else None), None
        candidates = [("goodreads_book_id", whole(row["goodreads_book_id"])),
                      ("book_id", whole(row["book_id"])),
                      ("isbn", clean["isbn"]), ("isbn13", clean["isbn13"])]
        for column, value in candidates:
            if value is not None:
                found = self.find(column, value)
                if len(found) == 1:
                    return found[0], column
        return None, None

    def load_row(self, line, row):
        clean, notes = clean_isbns(row["isbn"], row["isbn13"])
        self.status_counts["isbn"][clean["isbn_status"]] += 1
        self.status_counts["isbn13"][clean["isbn13_status"]] += 1
        for column in ("isbn", "isbn13"):
            if clean[f"{column}_status"] == "repaired":
                self.handled["isbn_values_repaired"] += 1

        existing, matched_on = self.match(row, clean)
        if existing is None:
            book = self.insert(line, row, clean)
            outcome = "created"
            self.counts["loaded"] += 1
        else:
            if matched_on:
                self.warn(CHECK, existing, line, matched_on, row.get(matched_on),
                          f"Row has no work_id, so it was matched to this book on {matched_on}.",
                          "Check that this is the same book.")
            book = existing
            changed = self.update(line, row, clean, existing)
            outcome = "updated" if changed else "unchanged"
            self.counts["updated" if changed else "skipped_already_exists"] += 1

        for group, column, value, reason, action in notes:
            self.warn(group, book, line, column, value, reason, action)
        self.lines_seen.setdefault(book["book_key"], line)
        self.conn.execute("INSERT INTO book_sources VALUES (?, ?, ?, ?)",
                          (self.run_id, book["book_key"], line, outcome))

    # -- A new book ---------------------------------------------------------

    def insert(self, line, row, clean):
        values = {column: as_number_or_text(row[column]) for column in ID_COLUMNS + COUNT_COLUMNS}
        values.update({column: row[column] or None for column in DESCRIPTIVE_COLUMNS})
        values.update(clean)
        average, total, notes = recalculate(row)
        values.update(average_rating=average, work_ratings_count=total, created_run=self.run_id)
        columns = list(values)
        cursor = self.conn.execute(
            f"INSERT INTO books ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            [values[column] for column in columns])
        book = self.book(cursor.lastrowid)

        for column, value, reason, action in notes:
            self.warn(CHECK, book, line, column, value, reason, action)

        if whole(row["work_id"]) is None:
            self.warn_about_possible_matches(line, row, book)
        else:
            for column in ("goodreads_book_id", "book_id"):       # Decision 19
                value = whole(row[column])
                others = [b for b in self.find(column, value) if b["book_key"] != book["book_key"]] if value is not None else []
                if others:
                    self.warn(DECISION, book, line, column, row[column],
                              f"New work_id, but {column} {value} belongs to '{others[0]['title']}'.",
                              "Decide whether these are the same book.")
        return book

    def warn_about_possible_matches(self, line, row, book):
        """Decision 20: a possible match is flagged, never merged."""
        year = row["original_publication_year"] or None
        possible = [other["title"] for other in self.find("original_publication_year", year) if year
                    and other["book_key"] != book["book_key"]
                    and clean_title(other["title"]) == clean_title(row["title"])
                    and first_author(other["authors"]) == first_author(row["authors"])]
        listed = f"Possible matches: {', '.join(possible)}." if possible else "No possible matches."
        self.warn(DECISION, book, line, "work_id", row["work_id"],
                  f"No ID matches any book, so it was added as a new book. {listed}",
                  "Decide whether this is a new book.")

    # -- A book that's already loaded (Rule 12, Decisions 22-25) ------------

    def update(self, line, row, clean, book):
        new_values = {}
        reasons = {}

        def change(column, value, reason):
            new_values[column] = value
            reasons[column] = reason

        def check(column, value, reason, action="Check that the new value is right."):
            self.warn(CHECK, book, line, column, None if value is None else str(value), reason, action)

        for column in ID_COLUMNS:                                 # never changed
            incoming = as_number_or_text(row[column])
            if incoming is not None and incoming != book[column]:
                check(column, incoming, f"{column} differs: stored {book[column]}, file has {incoming}. "
                      "It wasn't changed.", "Check that the match is right.")

        for column in DESCRIPTIVE_COLUMNS:                        # never replaced with empty
            incoming = row[column] or None
            if incoming is None:
                if book[column] is not None:
                    self.handled["empty_values_ignored"] += 1
            elif incoming != book[column]:
                change(column, incoming, f"Descriptive value changed in {self.file_name}.")
                check(column, incoming, f"{column} changed from {book[column]!r} to {incoming!r}.")

        for column in ("isbn", "isbn13"):                         # Decision 24
            incoming = clean[column]
            if incoming is None:
                if book[column] is not None:
                    self.handled["empty_values_ignored"] += 1
            elif incoming != book[column]:
                reason = f"Different ISBN in {self.file_name}."
                change(column, incoming, reason)
                change(f"{column}_status", clean[f"{column}_status"], reason)
                change(f"{column}_original", clean[f"{column}_original"], reason)
                check(column, incoming, f"{column} changed from {book[column]} to {incoming}.")

        if clean["other_id"] and clean["other_id"] != book["other_id"]:
            change("other_id", clean["other_id"], f"Descriptive value changed in {self.file_name}.")
            check("other_id", clean["other_id"], f"other_id changed from {book['other_id']} to {clean['other_id']}.")

        if "isbn_status" in new_values or "isbn13_status" in new_values:
            statuses = (new_values.get("isbn_status", book["isbn_status"]),
                        new_values.get("isbn13_status", book["isbn13_status"]))
            worst = next(s for s in STATUS_ORDER if s in statuses)
            if worst != book["isbn_row_status"]:
                change("isbn_row_status", worst, "Worse of the two ISBN statuses.")

        for column in COUNT_COLUMNS:                              # the newer value is taken
            incoming = whole(row[column])
            if incoming is None or incoming == book[column]:
                continue
            change(column, incoming, f"Newer count in {self.file_name}.")
            if isinstance(book[column], int) and incoming < book[column]:
                check(column, incoming, f"{column} went down from {book[column]} to {incoming}.",
                      "Check that this file really is newer.")

        average, total, notes = recalculate(row)                  # recalculated, never copied
        for column, value in (("average_rating", average), ("work_ratings_count", total)):
            if value is not None and value != book[column]:
                change(column, value, "Recalculated from the star counts.")
        for column, value, reason, action in notes:
            self.warn(CHECK, book, line, column, value, reason, action)

        if not new_values:
            return False

        assignments = ", ".join(f"{column} = ?" for column in new_values)
        self.conn.execute(f"UPDATE books SET {assignments} WHERE book_key = ?",
                          [*new_values.values(), book["book_key"]])
        changed = []
        for column, value in new_values.items():                  # Decision 27
            self.conn.execute("INSERT INTO history VALUES (?, ?, ?, ?, ?, ?)",
                              (self.run_id, book["book_key"], column, book[column], value, reasons[column]))
            changed.append({"column": column, "old": book[column], "new": value, "reason": reasons[column]})
        self.changes.append({"line": line, "book_id": book["book_id"], "title": book["title"], "changes": changed})
        return True

    # -- Shared ISBNs (Rule 7, Decision 16) ---------------------------------

    def warn_about_shared_isbns(self):
        for column in ("isbn", "isbn13"):
            shared = self.conn.execute(
                f"SELECT {column}, GROUP_CONCAT(book_key) FROM books WHERE {column} IS NOT NULL "
                f"GROUP BY {column} HAVING COUNT(*) > 1 ORDER BY {column}").fetchall()
            for value, keys in shared:
                keys = sorted(int(key) for key in keys.split(","))
                if not any(key in self.lines_seen for key in keys):
                    continue
                books = [self.book(key) for key in keys]
                for book in books:
                    others = ", ".join(repr(b["title"]) for b in books if b["book_key"] != book["book_key"])
                    self.warn(DECISION, book, self.lines_seen.get(book["book_key"]), column, value,
                              f"{column} {value} is also on {others}.",
                              "Decide which book really owns this ISBN.", issue=("shared", tuple(keys)))


# ---------------------------------------------------------------------------
# The log (Decisions 28-30) and the result line (Rule 13)
# ---------------------------------------------------------------------------

def read_log():
    """Decision 28: stop before touching the database if the log can't be read."""
    if not LOG_PATH.exists():
        return []
    try:
        entries = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        sys.exit(f"{LOG_PATH.name} can't be read ({error}). It and the database were left untouched.")
    if not isinstance(entries, list):
        sys.exit(f"{LOG_PATH.name} isn't a JSON array. It and the database were left untouched.")
    return entries


def write_log(entries):
    """Written to a temporary file first, so a crash can't leave half a log."""
    temporary = LOG_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, LOG_PATH)


def result_line(load):
    counts = load.counts
    decisions, lookups = len(load.decision_issues), len(load.groups[LOOKUP])
    needs_attention = counts["rejected"] or any(load.groups.values())
    summary = f"{counts['read']} rows. {counts['loaded']} new books, {counts['updated']} updated"
    if not needs_attention:
        return "loaded", f"Loaded: {summary}."
    return "loaded_with_warnings", (f"Loaded with warnings: {summary}, {decisions} need a decision, "
                                    f"{lookups} ISBNs need looking up.")


def flagged_books(groups):
    """The same warnings, one entry per book, for report.html's list of flagged rows."""
    books = {}
    for group in (DECISION, LOOKUP, CHECK):
        for warning in groups[group]:
            key = warning["book_key"] if warning["book_key"] is not None else f"line {warning['line']}"
            entry = books.setdefault(key, {"line": warning["line"], "book_id": warning["book_id"],
                                           "title": warning["title"], "reasons": []})
            entry["reasons"].append(warning["reason"])
    return list(books.values())


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------

def run_load(typed_path, full_path, run_at, entries):
    header, rows, size, sha256 = read_csv_file(full_path)
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        try:
            create_tables(conn)
            books_before = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            run_id = conn.execute(
                "INSERT INTO runs (run_at, file, file_path, full_path, file_size, sha256) VALUES (?, ?, ?, ?, ?, ?)",
                (run_at, full_path.name, typed_path, str(full_path), size, sha256)).lastrowid

            load = Load(conn, run_id, full_path.name)
            load.run(header, rows)

            books_after = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            flagged = flagged_books(load.groups)
            counts = dict(load.counts, flagged=len(flagged))
            status_counts = {column: dict(sorted(c.items())) for column, c in load.status_counts.items()}
            conn.execute(
                "UPDATE runs SET read = ?, loaded = ?, updated = ?, skipped_already_exists = ?, rejected = ?, "
                "flagged = ?, books_before = ?, books_after = ?, isbn_status_counts = ? WHERE run_id = ?",
                (counts["read"], counts["loaded"], counts["updated"], counts["skipped_already_exists"],
                 counts["rejected"], counts["flagged"], books_before, books_after,
                 json.dumps(status_counts), run_id))

            status, result = result_line(load)
            entry = {
                "run_at": run_at, "status": status, "result": result, "file": full_path.name,
                "file_path": typed_path, "full_path": str(full_path), "file_size": size,
                "sha256": sha256, "database": DB_PATH.name, "counts": counts,
                "books_before": books_before, "books_after": books_after,
                "isbn_status_counts": status_counts,
                "warnings": {**load.groups, "decisions_needed": len(load.decision_issues),
                             "handled_automatically": dict(sorted(load.handled.items()))},
                "changes": load.changes, "assumptions": ASSUMPTIONS,
                "not_loaded": load.not_loaded, "flagged": flagged,
            }
            write_log(entries + [entry])
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return entry


def wait_for_lock(lock_file):
    """Take the lock, waiting if another run has it. The operating system
    releases it if a run crashes, so a crash can't block later runs."""
    waiting = "Another load is running. Waiting for it to finish..."
    lock_file.seek(0)
    if msvcrt:
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            print(waiting, flush=True)
        while True:
            try:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)   # gives up after 10 seconds
                return
            except OSError:
                continue
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(waiting, flush=True)
        fcntl.flock(lock_file, fcntl.LOCK_EX)


@contextmanager
def one_run_at_a_time():
    """Decision 28: earlier log entries are never changed. Each run holds this lock
    from before it reads the log until after it writes it, so overlapping runs
    can't overwrite each other's entries."""
    with open(LOG_PATH.with_name(LOG_PATH.name + ".lock"), "a+b") as lock_file:
        wait_for_lock(lock_file)
        try:
            yield
        finally:
            if msvcrt:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python ingest.py <file.csv>")
    with one_run_at_a_time():
        run_once(sys.argv[1])


def run_once(typed_path):
    full_path = Path(typed_path).resolve()
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entries = read_log()

    try:
        entry = run_load(typed_path, full_path, run_at, entries)
    except (RunFailed, sqlite3.Error) as problem:
        result = f"Failed: {problem} Nothing changed, and it's safe to run again."
        size, sha256 = None, None
        if full_path.is_file():
            data = full_path.read_bytes()
            size, sha256 = len(data), hashlib.sha256(data).hexdigest()
        write_log(entries + [{
            "run_at": run_at, "status": "failed", "result": result, "reason": str(problem),
            "file": full_path.name, "file_path": typed_path, "full_path": str(full_path),
            "file_size": size, "sha256": sha256, "database": DB_PATH.name,
        }])
        sys.exit(result)

    print(entry["result"])
    counts = entry["counts"]
    print(f"Read {counts['read']}: {counts['loaded']} new, {counts['updated']} updated, "
          f"{counts['skipped_already_exists']} already loaded, {counts['rejected']} rejected. "
          f"Books: {entry['books_before']} -> {entry['books_after']}.")
    print(f"Logged to {LOG_PATH.name}")


if __name__ == "__main__":
    main()
