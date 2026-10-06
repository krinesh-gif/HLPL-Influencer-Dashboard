import csv
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

RESERVED = {'p', 'reel', 'reels', 'stories', 'explore', 'direct', 'accounts', 'about'}

def username(value):
    value = str(value).strip()
    if not value:
        raise ValueError('Empty profile')
    if value.startswith('@'):
        value = value[1:]
    elif '/' in value or '://' in value:
        u = urlparse(value if '://' in value else 'https://' + value)
        parts = u.path.strip('/').split('/')
        if u.scheme != 'https' or u.hostname not in {'instagram.com', 'www.instagram.com'} or len(parts) != 1:
            raise ValueError('Use an Instagram profile URL')
        value = parts[0]
    if not re.fullmatch(r'[A-Za-z0-9._]{1,30}', value) or value.lower() in RESERVED:
        raise ValueError('Invalid Instagram username')
    return value.lower()

def load_profiles(path):
    if path.lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            rows = list(wb.active.values)
        finally:
            wb.close()
    else:
        with open(path, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))
    valid, invalid = [], []
    for row in rows:
        for cell in row:
            if cell and 'instagram.com/' in str(cell).lower():
                try:
                    valid.append(username(cell))
                except ValueError:
                    invalid.append(str(cell))
    return list(dict.fromkeys(valid)), invalid

class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS outreach (sender TEXT, recipient TEXT, status TEXT, message TEXT, updated TEXT, PRIMARY KEY(sender,recipient))')
        self.db.commit()

    def status(self, sender, recipient):
        r = self.db.execute('SELECT status FROM outreach WHERE sender=? AND recipient=?', (sender, recipient)).fetchone()
        return r[0] if r else None

    def record(self, sender, recipient, status, message):
        self.db.execute('INSERT OR REPLACE INTO outreach VALUES (?,?,?,?,?)', (sender, recipient, status, message, datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def export(self, path):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['sender','recipient','status','message','updated_utc'])
            for row in self.db.execute('SELECT * FROM outreach ORDER BY updated DESC'):
                # Prevent spreadsheet formula execution in exported free text.
                w.writerow(["'" + x if x and x[0] in '=+-@' else x for x in row])

    def close(self):
        self.db.close()
