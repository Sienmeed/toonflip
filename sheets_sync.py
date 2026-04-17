#\!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Sheets Glossary Sync
- Read: CSV export (no extra deps, sheet must be public/anyone with link)
- Write: gspread + service account (optional)

Sheet format:
  Column A: Manga_Title
  Column B: Original_Name
  Column C: Translated_Name
  Column D: description
"""
import csv, io, re, logging

logger = logging.getLogger(__name__)


def extract_sheet_id(url_or_id):
    """Extract sheet ID from URL or return as-is if already an ID."""
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
    if m:
        return m.group(1)
    return url_or_id.strip()


def pull_glossary_from_sheet(sheet_id, manga_title, sheet_name=None):
    """
    Pull glossary entries from a public Google Sheet.
    Returns dict: {original_name: {"translated": ..., "description": ...}}
    Sheet must be 'Anyone with the link can view'.
    """
    import urllib.request
    import urllib.parse

    sheet_id = extract_sheet_id(sheet_id)
    base = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
    params = {"tqx": "out:csv"}
    if sheet_name:
        params["sheet"] = sheet_name
    url = base + "?" + urllib.parse.urlencode(params)

    logger.info(f"Pulling glossary from sheet: {sheet_id}, filter: {manga_title}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ManhwaTranslator/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to fetch sheet: {e}")
        raise ConnectionError(f"Cannot fetch Google Sheet: {e}")

    glossary = {}
    reader = csv.DictReader(io.StringIO(raw))

    for row in reader:
        title = (row.get("Manga_Title") or row.get("manga_title") or "").strip()
        orig = (row.get("Original_Name") or row.get("original_name") or "").strip()
        trans = (row.get("Translated_Name") or row.get("translated_name") or "").strip()
        desc = (row.get("description") or row.get("Description") or "").strip()

        if not orig or not trans:
            continue

        if manga_title and title.lower() != manga_title.lower():
            continue

        glossary[orig] = {"translated": trans, "description": desc}

    logger.info(f"Pulled {len(glossary)} entries for {manga_title}")
    return glossary


def pull_all_titles_from_sheet(sheet_id, sheet_name=None):
    """Get all unique Manga_Title values from the sheet."""
    import urllib.request
    import urllib.parse

    sheet_id = extract_sheet_id(sheet_id)
    base = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
    params = {"tqx": "out:csv"}
    if sheet_name:
        params["sheet"] = sheet_name
    url = base + "?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ManhwaTranslator/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        raise ConnectionError(f"Cannot fetch Google Sheet: {e}")

    titles = set()
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        title = (row.get("Manga_Title") or row.get("manga_title") or "").strip()
        if title:
            titles.add(title)
    return sorted(titles)


def _get_gspread_client(creds_path):
    """Get authenticated gspread client."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError("pip install gspread google-auth")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)


def push_glossary_to_sheet(sheet_id, manga_title, glossary, creds_path, sheet_name=None):
    """
    Push glossary entries to Google Sheet.
    Only adds NEW entries (not already in sheet).
    Requires gspread + service account credentials.
    """
    sheet_id = extract_sheet_id(sheet_id)
    gc = _get_gspread_client(creds_path)
    spreadsheet = gc.open_by_key(sheet_id)

    if sheet_name:
        ws = spreadsheet.worksheet(sheet_name)
    else:
        ws = spreadsheet.sheet1

    existing = set()
    records = ws.get_all_records()
    for rec in records:
        title = str(rec.get("Manga_Title", "")).strip()
        orig = str(rec.get("Original_Name", "")).strip()
        if title.lower() == manga_title.lower() and orig:
            existing.add(orig)

    new_count = 0
    for orig, info in glossary.items():
        if orig not in existing:
            row = [manga_title, orig, info["translated"], info.get("description", "")]
            ws.append_row(row, value_input_option="USER_ENTERED")
            new_count += 1

    logger.info(f"Pushed {new_count} new entries for {manga_title}")
    return new_count
