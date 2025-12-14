"""
データ入出力ユーティリティ
CSV読み込み・書き出し処理を提供
"""

import pandas as pd
import streamlit as st
import os
import re
from datetime import datetime
from modules.data_loader import DataLoader
from modules.utils import get_base_path


def process_uploaded_files(monthly_plan_file, actual_file, safety_stock_file, abc_classification_file=None):
    """アップロードされたファイルを処理してDataLoaderに読み込む"""
    try:
        # 判定ロジック：
        # - アップロードエリア：ファイル名を無視し、存在のみで判定
        # - dataフォルダ：ファイル名で厳格に判定
        base_path = get_base_path()
        has_monthly_plan = (
            monthly_plan_file is not None or
            os.path.exists(os.path.join(base_path, "data/月次計画データ.csv"))
        )
        has_actual = (
            actual_file is not None or
            os.path.exists(os.path.join(base_path, "data/日次実績データ.csv"))
        )
        has_safety_stock = (
            safety_stock_file is not None or
            os.path.exists(os.path.join(base_path, "data/安全在庫データ.csv"))
        )
        
        # ケースA：①・②のどちらか、または両方が欠けている場合
        if not has_monthly_plan or not has_actual:
            # セッション状態から③のエラーをクリア（①・②が揃っていない場合は表示しない）
            if 'missing_safety_stock_error' in st.session_state:
                del st.session_state.missing_safety_stock_error
            
            # 個別のエラーメッセージを表示
            if not has_monthly_plan:
                st.markdown("""
                <div class="annotation-warning-box">
                    <span class="icon">❌</span>
                    <div class="text">必須データエラー：① 月次計画データがアップロードされていません。</div>
                </div>
                """, unsafe_allow_html=True)
            if not has_actual:
                st.markdown("""
                <div class="annotation-warning-box">
                    <span class="icon">❌</span>
                    <div class="text">必須データエラー：② 日次実績データがアップロードされていません。</div>
                </div>
                """, unsafe_allow_html=True)
            return
        
        # ケースB：③だけが欠けている場合
        if not has_safety_stock:
            # セッション状態に保存して表示し続ける（自動で消さない）
            st.session_state.missing_safety_stock_error = True
            st.markdown("""
            <div class="annotation-warning-box">
                <span class="icon">❌</span>
                <div class="text">必須データエラー：③ 安全在庫データがアップロードされていないため、現行設定との比較ができません（安全在庫の算出は可能です）。</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # ③がアップロードされた場合のみエラーをクリア
            if 'missing_safety_stock_error' in st.session_state:
                del st.session_state.missing_safety_stock_error
        
        # DataLoaderを初期化（ダミーファイルを渡す）
        data_loader = DataLoader("data/日次計画データ.csv", "data/日次実績データ.csv")
        
        # 月次計画データの処理
        if monthly_plan_file is not None:
            try:
                # CSVを読み込み（エンコーディングを自動判定）
                # まずutf-8-sigで試行、失敗した場合はshift_jisで試行
                try:
                    monthly_plan_df = pd.read_csv(monthly_plan_file, index_col=0, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    monthly_plan_file.seek(0)  # ファイルポインタをリセット
                    monthly_plan_df = pd.read_csv(monthly_plan_file, index_col=0, encoding='shift_jis')
                
                # カラム名がYYYYMM形式か確認
                # 最初のカラム名をチェック
                first_col = str(monthly_plan_df.columns[0])
                if len(first_col) == 6 and first_col.isdigit():
                    # 月次計画データとして処理し、日次計画に変換
                    data_loader.load_monthly_plan_from_dataframe(monthly_plan_df)
                    daily_plan_df = data_loader.convert_monthly_to_daily_plan(monthly_plan_df)
                    st.success(f"✅ 月次計画データを日次計画データに変換しました: {monthly_plan_file.name}")
                else:
                    st.error(f"❌ 月次計画データの形式が不正です。列名はYYYYMM形式（例: 202406）である必要があります。")
                    return
            except ValueError as e:
                st.error(f"❌ 月次計画データの処理エラー: {str(e)}")
                return
            except Exception as e:
                st.error(f"❌ 月次計画データの読み込みエラー: {str(e)}")
                return
        
        # 日次実績データの処理
        if actual_file is not None:
            try:
                # CSVを読み込み（エンコーディングを自動判定）
                # まずutf-8-sigで試行、失敗した場合はshift_jisで試行
                try:
                    actual_df = pd.read_csv(actual_file, index_col=0, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    actual_file.seek(0)  # ファイルポインタをリセット
                    actual_df = pd.read_csv(actual_file, index_col=0, encoding='shift_jis')
                
                data_loader.load_actual_from_dataframe(actual_df)
                st.success(f"✅ 日次実績データを読み込みました: {actual_file.name}")
            except Exception as e:
                st.error(f"❌ 日次実績データの読み込みエラー: {str(e)}")
                return
        
        # 安全在庫月数データの処理
        if safety_stock_file is not None:
            try:
                # CSVを読み込み（エンコーディングを自動判定）
                # まずutf-8-sigで試行、失敗した場合はshift_jisで試行
                try:
                    safety_stock_df = pd.read_csv(safety_stock_file, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    safety_stock_file.seek(0)  # ファイルポインタをリセット
                    safety_stock_df = pd.read_csv(safety_stock_file, encoding='shift_jis')
                
                data_loader.load_safety_stock_from_dataframe(safety_stock_df)
                st.success(f"✅ 安全在庫月数データを読み込みました: {safety_stock_file.name}")
                # ③が読み込まれた場合、エラーをクリア
                if 'missing_safety_stock_error' in st.session_state:
                    del st.session_state.missing_safety_stock_error
            except Exception as e:
                st.error(f"❌ 安全在庫月数データの読み込みエラー: {str(e)}")
                return
        
        # 月次計画データがアップロードされていない場合、日次計画データが必要
        if monthly_plan_file is None:
            # 既存の日次計画データを読み込む
            # ただし、日次実績データがアップロードされている場合は、load_data()を呼ばずに個別に処理
            if actual_file is not None:
                # 日次実績データは既にアップロードされているので、計画データのみ読み込む
                plan_path = os.path.join(base_path, "data/日次計画データ.csv")
                monthly_plan_path = os.path.join(base_path, "data/月次計画データ.csv")
                
                if os.path.exists(plan_path):
                    # 日次計画データを読み込む
                    try:
                        try:
                            plan_df = pd.read_csv(plan_path, index_col=0, encoding='utf-8-sig')
                        except UnicodeDecodeError:
                            plan_df = pd.read_csv(plan_path, index_col=0, encoding='shift_jis')
                        # カラム名を日付型に変換
                        plan_df.columns = pd.to_datetime(plan_df.columns, format='%Y%m%d')
                        data_loader.plan_df = plan_df
                        data_loader.working_dates = plan_df.columns
                    except Exception as e:
                        st.error(f"❌ 日次計画データの読み込みエラー: {str(e)}")
                        return
                elif os.path.exists(monthly_plan_path):
                    # 月次計画データを読み込む
                    try:
                        try:
                            monthly_plan_df = pd.read_csv(monthly_plan_path, index_col=0, encoding='utf-8-sig')
                        except UnicodeDecodeError:
                            monthly_plan_df = pd.read_csv(monthly_plan_path, index_col=0, encoding='shift_jis')
                        data_loader.load_monthly_plan_from_dataframe(monthly_plan_df)
                        data_loader.convert_monthly_to_daily_plan(monthly_plan_df)
                    except Exception as e:
                        st.error(f"❌ 月次計画データの読み込みエラー: {str(e)}")
                        return
                else:
                    st.error(f"❌ 日次計画データの読み込みエラー: 計画データファイルが見つかりません")
                    return
            else:
                # 日次実績データもアップロードされていない場合は、load_data()を呼ぶ
                # この場合、両方のファイルがdataフォルダに存在する必要がある
                try:
                    data_loader.load_data()
                except Exception as e:
                    st.error(f"❌ 日次計画データの読み込みエラー: {str(e)}")
                    return
        
        # 日次実績データがアップロードされていない場合、既存データを使用
        if actual_file is None:
            try:
                actual_path = os.path.join(base_path, "data/日次実績データ.csv")
                if os.path.exists(actual_path):
                    # エンコーディングを自動判定
                    try:
                        actual_df = pd.read_csv(actual_path, index_col=0, encoding='utf-8-sig')
                    except UnicodeDecodeError:
                        actual_df = pd.read_csv(actual_path, index_col=0, encoding='shift_jis')
                    data_loader.load_actual_from_dataframe(actual_df)
            except Exception as e:
                st.warning(f"⚠️ 既存の日次実績データの読み込みに失敗しました: {str(e)}")
        
        # 安全在庫データがアップロードされていない場合、既存データを読み込む
        if safety_stock_file is None:
            # dataフォルダにファイルが存在する場合のみ読み込む
            safety_stock_path = os.path.join(base_path, "data/安全在庫データ.csv")
            if os.path.exists(safety_stock_path):
                try:
                    data_loader.load_safety_stock_monthly()
                    # 既存データの読み込みが成功した場合、エラーをクリア
                    if 'missing_safety_stock_error' in st.session_state:
                        del st.session_state.missing_safety_stock_error
                except Exception:
                    pass

        # 現行ABC区分データ（任意）の処理
        if abc_classification_file is not None:
            try:
                abc_classification_file.seek(0)
                try:
                    abc_df = pd.read_csv(abc_classification_file, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    abc_classification_file.seek(0)
                    abc_df = pd.read_csv(abc_classification_file, encoding='shift_jis')

                if abc_df.shape[1] < 2:
                    st.error("❌ 現行ABC区分データには、商品コードとABC区分の2列が必要です。")
                    return

                normalized_df = abc_df.iloc[:, :2].copy()
                normalized_df.columns = ['商品コード', 'ABC区分']
                normalized_df['商品コード'] = normalized_df['商品コード'].astype(str).str.strip()
                normalized_df['ABC区分'] = normalized_df['ABC区分'].astype(str).str.upper().str.strip()
                normalized_df = normalized_df.dropna(subset=['商品コード', 'ABC区分'])
                normalized_df = normalized_df[normalized_df['商品コード'] != ""]

                alpha_pattern = re.compile(r'^[A-Z]+$')
                invalid_mask = ~normalized_df['ABC区分'].str.match(alpha_pattern)
                if invalid_mask.any():
                    invalid_values = ", ".join(sorted(normalized_df.loc[invalid_mask, 'ABC区分'].unique()))
                    st.error(f"❌ ABC区分はアルファベットで指定してください。不正値: {invalid_values}")
                    return

                normalized_df = normalized_df.drop_duplicates(subset='商品コード', keep='last')
                if normalized_df.empty:
                    st.error("❌ 現行ABC区分データに有効な行がありません。")
                    return

                st.session_state.existing_abc_df = normalized_df.rename(
                    columns={'商品コード': 'product_code', 'ABC区分': 'abc_category'}
                )
                st.success(f"✅ 現行ABC区分データを読み込みました: {abc_classification_file.name}")
            except Exception as e:
                st.error(f"❌ 現行ABC区分データの読み込みエラー: {str(e)}")
                return
        
        # セッション状態に保存
        st.session_state.uploaded_data_loader = data_loader
        
        # アンマッチチェックを実行（①〜③が正常に読み込めた場合のみ）
        if (data_loader.plan_df is not None and 
            data_loader.actual_df is not None and 
            data_loader.safety_stock_monthly_df is not None and 
            not data_loader.safety_stock_monthly_df.empty):
            try:
                mismatch_detail_df = check_product_code_mismatch(data_loader)
                # 詳細データとサマリーデータの両方を保存
                st.session_state.product_code_mismatch_detail_df = mismatch_detail_df
                # サマリーデータを作成
                if not mismatch_detail_df.empty:
                    mismatch_summary_df = (
                        mismatch_detail_df
                        .groupby("区分")
                        .agg(
                            対象商品コード件数=("商品コード", "nunique"),
                            例=("商品コード", "first"),
                            説明=("説明", "first"),
                        )
                        .reset_index()
                    )
                    st.session_state.product_code_mismatch_summary_df = mismatch_summary_df
                else:
                    st.session_state.product_code_mismatch_summary_df = pd.DataFrame(columns=['区分', '対象商品コード件数', '例', '説明'])
            except Exception as e:
                # アンマッチチェックでエラーが発生した場合は警告のみ表示し、処理は続行
                st.warning(f"⚠️ アンマッチチェック中にエラーが発生しました: {str(e)}")
                st.session_state.product_code_mismatch_detail_df = pd.DataFrame(columns=['区分', '商品コード', '説明'])
                st.session_state.product_code_mismatch_summary_df = pd.DataFrame(columns=['区分', '対象商品コード件数', '例', '説明'])
        else:
            # 安全在庫データがない場合もアンマッチチェックを実行（安全在庫なしのパターンは検出できないが、計画・実績のアンマッチは検出可能）
            if data_loader.plan_df is not None and data_loader.actual_df is not None:
                try:
                    mismatch_detail_df = check_product_code_mismatch(data_loader)
                    # 詳細データとサマリーデータの両方を保存
                    st.session_state.product_code_mismatch_detail_df = mismatch_detail_df
                    # サマリーデータを作成
                    if not mismatch_detail_df.empty:
                        mismatch_summary_df = (
                            mismatch_detail_df
                            .groupby("区分")
                            .agg(
                                対象商品コード件数=("商品コード", "nunique"),
                                例=("商品コード", "first"),
                                説明=("説明", "first"),
                            )
                            .reset_index()
                        )
                        st.session_state.product_code_mismatch_summary_df = mismatch_summary_df
                    else:
                        st.session_state.product_code_mismatch_summary_df = pd.DataFrame(columns=['区分', '対象商品コード件数', '例', '説明'])
                except Exception as e:
                    st.warning(f"⚠️ アンマッチチェック中にエラーが発生しました: {str(e)}")
                    st.session_state.product_code_mismatch_detail_df = pd.DataFrame(columns=['区分', '商品コード', '説明'])
                    st.session_state.product_code_mismatch_summary_df = pd.DataFrame(columns=['区分', '対象商品コード件数', '例', '説明'])
            else:
                # 計画または実績データがない場合はアンマッチチェックをスキップ
                st.session_state.product_code_mismatch_detail_df = pd.DataFrame(columns=['区分', '商品コード', '説明'])
                st.session_state.product_code_mismatch_summary_df = pd.DataFrame(columns=['区分', '対象商品コード件数', '例', '説明'])
        
        st.success("✅ 全てのデータを適用しました。画面が更新されます。")
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ データ処理エラー: {str(e)}")


def dataframe_to_csv_bytes(df: pd.DataFrame, encoding: str = 'utf-8-sig') -> bytes:
    """
    DataFrameをCSV形式のバイト列に変換
    
    Args:
        df: 変換するDataFrame
        encoding: エンコーディング（デフォルト: utf-8-sig）
    
    Returns:
        bytes: CSV形式のバイト列
    """
    csv_data = df.to_csv(index=False, encoding=encoding)
    return csv_data.encode(encoding)


def create_csv_download_filename(prefix: str, suffix: str = "") -> str:
    """
    CSVダウンロード用のファイル名を生成
    
    Args:
        prefix: ファイル名のプレフィックス
        suffix: ファイル名のサフィックス（オプション）
    
    Returns:
        str: ファイル名
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if suffix:
        return f"{prefix}_{suffix}_{timestamp}.csv"
    else:
        return f"{prefix}_{timestamp}.csv"


def check_product_code_mismatch(data_loader: DataLoader) -> pd.DataFrame:
    """
    商品コードのアンマッチをチェックする
    
    以下の4つのパターンを検出する：
    A: 計画のみ（計画はあるのに実績がない）
    B: 実績のみ（実績はあるのに計画がない）
    C: 安全在庫なし（計画・実績あり）（計画・実績はあるが安全在庫が未設定）
    D: 安全在庫あり（計画・実績なし）（安全在庫は設定されているが計画・実績がない）
    
    Args:
        data_loader: DataLoaderインスタンス（データが読み込まれていること）
    
    Returns:
        pd.DataFrame: アンマッチリスト（区分、商品コード、説明の3列）
    """
    # 各データのproduct_cdの集合を取得（すべて文字列に統一）
    # 計画データの商品コード集合
    if data_loader.plan_df is not None:
        plan_codes = set(str(code) for code in data_loader.plan_df.index)
    else:
        plan_codes = set()
    
    # 実績データの商品コード集合
    if data_loader.actual_df is not None:
        actual_codes = set(str(code) for code in data_loader.actual_df.index)
    else:
        actual_codes = set()
    
    # 安全在庫データの商品コード集合
    if data_loader.safety_stock_monthly_df is not None and not data_loader.safety_stock_monthly_df.empty:
        # 列名が'商品コード'でない場合も考慮
        if '商品コード' in data_loader.safety_stock_monthly_df.columns:
            safety_codes = set(str(code) for code in data_loader.safety_stock_monthly_df['商品コード'])
        else:
            # 最初の列を商品コードとして扱う
            safety_codes = set(str(code) for code in data_loader.safety_stock_monthly_df.iloc[:, 0])
    else:
        safety_codes = set()
    
    # アンマッチパターンの判定
    mismatch_list = []
    
    # A: 計画のみ（計画はあるのに実績がない）
    plan_only = plan_codes - actual_codes
    for code in plan_only:
        mismatch_list.append({
            '区分': '計画のみ',
            '商品コード': code,
            '説明': '実績がないため安全在庫は算出できません（算出対象外になります）。原因を確認してください。'
        })
    
    # B: 実績のみ（実績はあるのに計画がない）
    actual_only = actual_codes - plan_codes
    for code in actual_only:
        mismatch_list.append({
            '区分': '実績のみ',
            '商品コード': code,
            '説明': '実績はあるのに計画がありません。計画漏れの可能性があります。確認してください。'
        })
    
    # C: 安全在庫なし（計画・実績あり）（計画と実績の両方があるが安全在庫が未設定）
    plan_and_actual = plan_codes & actual_codes
    plan_actual_no_safety = plan_and_actual - safety_codes
    for code in plan_actual_no_safety:
        mismatch_list.append({
            '区分': '安全在庫なし（計画・実績あり）',
            '商品コード': code,
            '説明': '計画・実績はありますが安全在庫が未設定です。新規設定の候補です。'
        })
    
    # D: 安全在庫あり（計画・実績なし）（安全在庫は設定されているが計画・実績がない）
    # 計画にも実績にも存在しない商品を抽出
    plan_or_actual = plan_codes | actual_codes  # 計画または実績のいずれかに存在（和集合）
    safety_only = safety_codes - plan_or_actual
    for code in safety_only:
        mismatch_list.append({
            '区分': '安全在庫あり（計画・実績なし）',
            '商品コード': code,
            '説明': '安全在庫はありますが計画・実績がありません。設定を解除してください。'
        })
    
    # DataFrameに変換
    if mismatch_list:
        mismatch_df = pd.DataFrame(mismatch_list)
        # 区分でソート（指定された順序）
        sort_order = {
            '計画のみ': 1,
            '実績のみ': 2,
            '安全在庫なし（計画・実績あり）': 3,
            '安全在庫あり（計画・実績なし）': 4
        }
        mismatch_df['sort_key'] = mismatch_df['区分'].map(sort_order)
        mismatch_df = mismatch_df.sort_values('sort_key').drop('sort_key', axis=1).reset_index(drop=True)
        return mismatch_df
    else:
        # アンマッチがない場合は空のDataFrameを返す
        return pd.DataFrame(columns=['区分', '商品コード', '説明'])

