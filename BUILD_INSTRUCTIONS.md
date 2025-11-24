# 安全在庫最適化シミュレーションツール - ビルド手順書

## 概要

本ドキュメントでは、安全在庫最適化シミュレーションツールをPyInstallerを使用してEXE化する手順を説明します。

## 前提条件

- Python 3.13.x がインストールされていること
- 仮想環境（venv）が作成されていること
- 必要な依存関係がインストールされていること

## ビルド手順

### 1. 仮想環境の準備

```bash
# 仮想環境の作成（既に作成済みの場合はスキップ）
python -m venv venv

# 仮想環境の有効化
venv\Scripts\activate

# 依存関係のインストール
pip install -r requirements.txt
```

### 2. PyInstallerでのビルド

#### 方法1: .specファイルを使用（推奨）

```bash
pyinstaller SafetyStock-SimOptimizer_ver1.spec
```

#### 方法2: コマンドライン直接実行

```bash
pyinstaller run_app.py --name SafetyStock-SimOptimizer_ver1 --noconsole --clean ^
  --add-data "config;config" --add-data "assets;assets" --add-data "data;data" ^
  --add-data "modules;modules" --add-data "logs;logs" --add-data "tmp;tmp"
```

### 3. ビルド結果の確認

ビルドが完了すると、以下のディレクトリが作成されます：

```
dist/
└── SafetyStock-SimOptimizer_ver1/
    ├── SafetyStock-SimOptimizer_ver1.exe  # メイン実行ファイル
    ├── config/                            # 設定ファイル
    ├── assets/                           # アセットファイル
    ├── data/                             # データファイル
    ├── modules/                          # モジュールファイル
    ├── logs/                             # ログファイル
    └── tmp/                              # 一時ファイル
```

### 4. 動作確認

```bash
# ビルドされたEXEの実行
cd dist\SafetyStock-SimOptimizer_ver1
SafetyStock-SimOptimizer_ver1.exe
```

## トラブルシューティング

### よくある問題と解決方法

#### 1. モジュールインポートエラー

**問題**: `ModuleNotFoundError` が発生する

**解決方法**:
- `.spec`ファイルの`hiddenimports`に不足しているモジュールを追加
- 依存関係が正しくインストールされているか確認

#### 2. データファイルが見つからない

**問題**: データファイルが読み込めない

**解決方法**:
- `.spec`ファイルの`datas`に必要なファイルパスを追加
- 相対パスが正しく設定されているか確認

#### 3. メモリ不足エラー

**問題**: ビルド中にメモリ不足が発生する

**解決方法**:
- 不要な依存関係を除外
- ビルド時に他のアプリケーションを終了

#### 4. 実行時エラー

**問題**: EXE実行時にエラーが発生する

**解決方法**:
- 必要なデータファイルが同梱されているか確認
- 依存関係が正しく含まれているか確認
- ログファイルでエラー詳細を確認

## 配布用パッケージの作成

### 1. 配布用ディレクトリの作成

```bash
mkdir SafetyStock-SimOptimizer_ver1_Distribution
```

### 2. 必要ファイルのコピー

```bash
# 実行ファイルとデータをコピー
xcopy dist\SafetyStock-SimOptimizer_ver1 SafetyStock-SimOptimizer_ver1_Distribution\ /E /I

# READMEファイルをコピー
copy README.md SafetyStock-SimOptimizer_ver1_Distribution\
```

### 3. 配布用ZIPファイルの作成

```bash
# PowerShellを使用してZIPファイルを作成
Compress-Archive -Path SafetyStock-SimOptimizer_ver1_Distribution -DestinationPath SafetyStock-SimOptimizer_ver1_v1.0.0.zip
```

## パフォーマンス最適化

### 1. ビルドサイズの削減

- 不要なライブラリを除外
- 使用していないモジュールを`excludes`に追加

### 2. 起動時間の短縮

- 必要最小限の依存関係のみ含める
- 遅延インポートを使用

## バージョン管理

### 1. バージョン情報の更新

- `VERSION.txt`ファイルを更新
- `.spec`ファイルのバージョン情報を更新

### 2. リリースノートの作成

- 新機能の追加
- バグ修正
- 既知の問題

## 注意事項

1. **Pythonバージョンの固定**: 開発環境とビルド環境で同じPythonバージョンを使用
2. **依存関係の固定**: `requirements.txt`でバージョンを固定
3. **テスト環境での動作確認**: 異なる環境でEXEの動作を確認
4. **セキュリティ**: 配布前にウイルススキャンを実行

## サポート

技術的な問題や要望については、開発チームまでお問い合わせください。
