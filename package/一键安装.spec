# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Hyman\\OneDrive\\开发项目\\Python项目\\code880_temp_v5.11_260421\\code880_temp_v5.11_还原_标准_Web迁移\\src\\一键安装卸载.py'],
    pathex=['C:\\Users\\Hyman\\OneDrive\\开发项目\\Python项目\\code880_temp_v5.11_260421\\code880_temp_v5.11_还原_标准_Web迁移'],
    binaries=[],
    datas=[('C:\\Users\\Hyman\\OneDrive\\开发项目\\Python项目\\code880_temp_v5.11_260421\\code880_temp_v5.11_还原_标准_Web迁移\\一键安装说明.md', '.'), ('C:\\Users\\Hyman\\OneDrive\\开发项目\\Python项目\\code880_temp_v5.11_260421\\code880_temp_v5.11_还原_标准_Web迁移\\THIRD_PARTY_NOTICES.md', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='一键安装',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
