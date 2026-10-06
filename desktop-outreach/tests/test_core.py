import csv
import tempfile
import unittest
from pathlib import Path
from core import username, load_profiles, Ledger

class Tests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(username('https://www.instagram.com/Creator.Name/?igsh=123'), 'creator.name')
        for bad in ['https://evil.com/person/', 'https://instagram.com/p/abc/', 'https://instagram.com/direct/', 'https://instagram.com@evil.com/a/', 'http://instagram.com/a/', 'bad name']:
            with self.assertRaises(ValueError): username(bad)

    def test_import_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'input.csv'
            p.write_text('profile\nhttps://instagram.com/TEST/\nhttps://www.instagram.com/test/\nhttps://instagram.com/p/123/\n')
            valid, bad = load_profiles(str(p))
            self.assertEqual(valid, ['test'])
            self.assertEqual(len(bad), 1)

    def test_ledger_recovers_and_sender_scopes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'db'
            l = Ledger(p)
            l.record('aravi','creator','uncertain','=danger')
            l.close()
            l = Ledger(p)
            self.assertEqual(l.status('aravi','creator'), 'uncertain')
            self.assertIsNone(l.status('other','creator'))
            out = Path(d)/'out.csv'
            l.export(out)
            with out.open() as f: rows = list(csv.reader(f))
            self.assertEqual(rows[1][3], "'=danger")
            l.close()

if __name__ == '__main__': unittest.main()
