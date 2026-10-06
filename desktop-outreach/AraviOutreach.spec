# Windows bundle includes Python, Tk, Playwright and Chromium.
from PyInstaller.utils.hooks import collect_all
datas, binaries, hiddenimports = collect_all('playwright')
a = Analysis(['app.py'], pathex=['.'], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports + ['openpyxl'], hookspath=[],
             runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='AraviOutreach', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='AraviOutreach')
