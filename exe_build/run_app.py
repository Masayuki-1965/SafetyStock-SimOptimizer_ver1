"""
安全在庫最適化シミュレーションツール - 起動スクリプト

PyInstaller EXE配布用のエントリポイント
Streamlitをライブラリとして起動
"""

import sys
import os
from streamlit.web import cli as stcli


def main():
    """Streamlitアプリケーションを起動"""
    if getattr(sys, 'frozen', False):
        # PyInstallerでビルドされた場合: 同梱ファイルは _internal (MEIPASS)
        application_path = os.path.dirname(sys.executable)
        base_path = sys._MEIPASS  # app.py, config, data はここ
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        base_path = application_path
    
    os.chdir(application_path)
    
    # Streamlitアプリのパス（EXE時は _internal 内の app.py）
    app_path = os.path.join(base_path, "app.py")
    
    # Streamlitをライブラリとして起動
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.headless=false",
        "--server.port=8501",
        "--browser.gatherUsageStats=false"
    ]
    
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()


