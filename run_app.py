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
    # カレントディレクトリをアプリのディレクトリに設定
    if getattr(sys, 'frozen', False):
        # PyInstallerでビルドされた場合
        application_path = os.path.dirname(sys.executable)
    else:
        # 通常のPython実行
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    os.chdir(application_path)
    
    # Streamlitアプリのパス
    app_path = os.path.join(application_path, "app.py")
    
    # Streamlitをライブラリとして起動
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.port=8501",
        "--browser.gatherUsageStats=false"
    ]
    
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()


