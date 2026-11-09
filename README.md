# Language of Computation: Week 4 Assignment

This is my Module 4 assignment for MSAI-5523.

Partner: John Hu

## Commands

Run these in PowerShell on Windows. Start each session by going to this folder:

```powershell
cd "$HOME\workspace\language-of-computation\week4-assignment"
```

### Run the tests

Install pytest, which the tests need. You only have to do this once:

```powershell
python -m pip install pytest
```

Run the tests:

```powershell
python -m pytest -v test_ingest.py
```

The tests use their own temporary `test.db` and log, and never touch `books.db` or `ingestion-log.json`.

### Run the ingestion

Run these in order. They write to `books.db` and `ingestion-log.json` in this folder.

Load `books.csv`:

```powershell
python ingest.py books.csv
```

Load `books.csv` again:

```powershell
python ingest.py books.csv
```

Load `books-batch2.csv`:

```powershell
python ingest.py books-batch2.csv
```
