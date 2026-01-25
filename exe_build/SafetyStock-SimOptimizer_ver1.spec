# -*- mode: python ; coding: utf-8 -*-
"""
SafetyStock-SimOptimizer PyInstaller spec file
onefolder方式（--onedir）でビルド
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


block_cipher = None

# データファイルの収集
datas = [
    ('config', 'config'),
    ('assets', 'assets'),
    ('data', 'data'),
    ('VERSION.txt', '.'),
    ('app.py', '.'),  # run_app が exe 同梱 dir から app.py を起動するため必須
]

# Streamlit関連のデータファイルを収集
streamlit_datas = collect_data_files('streamlit')
datas.extend(streamlit_datas)

# numpy 2.x の .libs フォルダと data files を収集（DLL とバイナリが必要）
try:
    numpy_datas = collect_data_files('numpy')
    datas.extend(numpy_datas)
    # numpy.libs フォルダを明示的に追加（numpy 2.x は .libs に DLL を配置）
    import numpy
    numpy_path = os.path.dirname(numpy.__file__)
    numpy_libs_path = os.path.join(numpy_path, '.libs')
    if os.path.exists(numpy_libs_path):
        datas.append((numpy_libs_path, 'numpy/.libs'))
except Exception:
    pass

# scipy の data files を収集（.libs の DLL 等）
try:
    scipy_datas = collect_data_files('scipy')
    datas.extend(scipy_datas)
except Exception:
    pass

# Streamlit と主要依存パッケージの metadata を確実に同梱
# recursive=True で依存パッケージの metadata も含める
metadata_packages = [
    'streamlit',
    'altair',
    'pydeck',
    'protobuf',
    'watchdog',
    'requests',
    'pandas',
    'numpy',
    'scipy',
    'plotly',
    'pyarrow',
    'PIL',
]
for pkg in metadata_packages:
    try:
        datas += copy_metadata(pkg, recursive=True)
    except Exception:
        # パッケージが存在しない場合はスキップ
        pass

# 隠しインポート（必要なモジュールを明示的に指定）
hiddenimports = [
    'streamlit',
    'streamlit.web.cli',
    'streamlit.runtime.scriptrunner.script_runner',
    'streamlit.runtime.state.session_state',
    'pandas',
    'numpy',
    'numpy.core',
    'numpy.core._multiarray_umath',
    'numpy.core.multiarray',
    'numpy.core.umath',
    'plotly',
    'scipy',
    'scipy._cyutility',
    'scipy.sparse._csparsetools',
    'scipy.sparse._sparsetools',
    'scipy.sparse.csgraph._shortest_path',
    'scipy.special._ufuncs_cxx',
    'scipy.spatial.transform._rotation_groups',
    'scipy.linalg.cython_blas',
    'scipy.linalg.cython_lapack',
    'scipy.stats',
    'scipy.stats._stats',
    'altair',
    'pyarrow',
    'PIL',
    # カスタムモジュール
    'modules.data_loader',
    'modules.safety_stock_models',
    'modules.safety_stock_theoretical',
    'modules.safety_stock_empirical',
    'modules.abc_analysis',
    'modules.outlier_handler',
    'modules.utils',
    'views.sidebar',
    'views.step1_view',
    'views.step2_view',
    'views.step3_view',
    'utils.common',
    'utils.data_io',
    'charts.safety_stock_charts',
]

# 追加の隠しインポート（Streamlit関連）
# langchain が無い場合の警告を抑制するため try-except で囲む
try:
    streamlit_submodules = collect_submodules('streamlit')
    hiddenimports.extend(streamlit_submodules)
except Exception:
    # 収集に失敗した場合はスキップ（警告は出るがビルドは続行）
    pass

# numpy の submodules を収集（numpy 2.x で必要）
try:
    numpy_submodules = collect_submodules('numpy')
    hiddenimports.extend(numpy_submodules)
except Exception:
    pass

# scipy の submodules を収集（_cyutility, _csparsetools 等を含める）
try:
    scipy_submodules = collect_submodules('scipy')
    hiddenimports.extend(scipy_submodules)
except Exception:
    pass

# numpy のパスを pathex に追加（numpy 2.x のパス解決問題を回避）
try:
    import numpy
    numpy_path = os.path.dirname(numpy.__file__)
    numpy_pathex = [numpy_path]
except Exception:
    numpy_pathex = []

a = Analysis(
    ['run_app.py'],
    pathex=numpy_pathex,  # numpy のパスを追加
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # scipy.special._cdflib は存在しない場合があるため除外
        # （警告は出るが、ビルドには影響しない）
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onefolder方式（--onedir）でビルド
# EXEは単一ファイルではなく、フォルダ内に配置される
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # バイナリをEXEに含めない（フォルダに配置）
    name='SafetyStock-SimOptimizer_ver1',
    debug=True,  # 一時的に有効化（エラー確認用）
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX圧縮を無効化（エラー回避）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 一時的に有効化（エラー確認用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# フォルダ内にすべてのファイルを収集
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # UPX圧縮を無効化（エラー回避）
    upx_exclude=[],
    name='SafetyStock-SimOptimizer_ver1',
)
