"""Compare every packaged file to the actual downloaded GitHub artifact."""
import hashlib
import sys
from pathlib import Path

def files(root):
    return {p.relative_to(root).as_posix(): hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
            for p in root.rglob('*') if p.is_file()}

if __name__ == '__main__':
    original, downloaded = map(Path, sys.argv[1:])
    expected, actual = files(original), files(downloaded)
    assert expected, 'Empty package'
    assert any('/.local-browsers/chromium-' in p and p.endswith('/chrome.exe') for p in actual), 'Full Chromium missing from downloaded artifact'
    assert expected == actual, f'Artifact changed: missing={set(expected)-set(actual)}, unexpected={set(actual)-set(expected)}, modified={[p for p in expected.keys() & actual.keys() if expected[p] != actual[p]]}'
    print(f'Verified {len(actual)} files byte-for-byte in downloaded artifact.')
