# -*- mode: python -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

options = [('v', None, 'OPTION')]

imports = collect_submodules('snappy')
imports += collect_submodules('cypari')
imports += collect_submodules('jedi')

datafiles = collect_data_files('jedi')

a = Analysis(['SnapPy.py'],
             binaries=None,
             hiddenimports=imports + ['linecache'],
             datas=datafiles,
             hookspath=[],
             runtime_hooks=[],
             excludes=['gi', 'pytz', 'td', 'sphinx', 'alabaster', 'babel',
                       'idlelib', 'bsddb'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='SnapPy',
          debug=True,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='SnapPy')