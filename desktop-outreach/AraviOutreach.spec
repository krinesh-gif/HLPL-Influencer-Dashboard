# Windows bundle includes Python, Tk, Playwright and Chromium.
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
import playwright
datas, binaries, hiddenimports = collect_all('playwright')
# collect_all may exclude browser executable files. Include the entire browser
# directory explicitly and fail the build if headed Chromium is absent.
browser_dir = Path(playwright.__file__).parent / 'driver' / 'package' / '.local-browsers'
if not list(browser_dir.glob('chromium-*/chrome-win64/chrome.exe')):
    raise RuntimeError('Full Windows Chromium is missing before packaging')
datas.append((str(browser_dir), 'playwright/driver/package/.local-browsers'))
a = Analysis(['app.py'], pathex=['.'], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports + ['openpyxl'], hookspath=[],
             runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='AraviOutreach', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='AraviOutreach')
