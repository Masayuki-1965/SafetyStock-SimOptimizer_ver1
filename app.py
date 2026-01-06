"""
安全在庫最適化シミュレーションツール
Streamlitアプリケーション
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime
import io
import html

# モジュールのインポート
from modules.data_loader import DataLoader
from modules.safety_stock_models import SafetyStockCalculator
from modules.abc_analysis import ABCAnalysis
from modules.utils import get_base_path
from modules.outlier_handler import OutlierHandler

# 新しいモジュール構造のインポート
from views.sidebar import display_sidebar
from views.step1_view import display_step1, display_safety_stock_definitions
from views.step2_view import display_step2
from views.step3_view import display_step3
# グラフ生成関数は各viewsから直接インポートされるため、ここではインポート不要
from utils.common import (
    slider_with_number_input,
    get_representative_products_by_abc,
    classify_inventory_days_bin
)

# ページ設定
st.set_page_config(
    page_title="安全在庫最適化シミュレーションツール",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS
st.markdown("""
<style>
    /* Streamlitの標準マージンを削減 */
    .main .block-container {
        padding-top: 1rem;
    }
    /* メインタイトルバナー */
    .title-banner {
        background-color: #1A73E8;
        color: white;
        padding: 2rem 2.5rem;
        border-radius: 8px;
        margin: 0 0 1.5rem 0;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        width: 100%;
    }
    .title-main {
        font-size: 2.8rem;
        font-weight: bold;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        margin: 0;
        line-height: 1.2;
        margin-bottom: 0.8rem;
        text-align: center;
    }
    .title-sub {
        font-size: 1.4rem;
        font-weight: normal;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        margin: 0;
        line-height: 1.4;
        opacity: 0.95;
        text-align: left;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .sub-header + .safety-stock-table,
    .sub-header + div .safety-stock-table {
        margin-top: 0.5rem;
    }
    .product-header {
        font-size: 1.3rem;
        font-weight: bold;
        color: #e74c3c;
        margin-top: 2rem;
        margin-bottom: 1rem;
        background-color: #fdf2f2;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #e74c3c;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }
    .footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background-color: #2c3e50;
        color: white;
        text-align: center;
        padding: 0.5rem;
        font-size: 0.8rem;
    }
    /* Primaryボタンのスタイルを赤背景・白文字・角丸に統一 */
    div.stButton > button[kind="primary"] {
        background-color: #ef4444 !important; /* red-500 */
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.75rem 1rem !important;
        font-weight: 600 !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #dc2626 !important; /* red-600 */
    }
    /* サイドバーSTEPボタンの改行制御とレイアウト調整（削除 - 新しいスタイルで上書き） */
    /* グラフと統計情報テーブルの間隔を詰める */
    div[data-testid="stPlotlyChart"] {
        margin-bottom: 0.3rem !important;
    }
    .statistics-table-container {
        margin-top: 0.3rem;
        margin-bottom: 1rem;
    }
    .statistics-table-container > div {
        margin-top: 0 !important;
    }
    /* ステップ見出しボックス（Causal Impactアプリ風） */
    .step-header-box {
        background-color: #E8F0FE;
        border-radius: 8px;
        padding: 1.2rem 1.5rem;
        margin: 0 0 1.5rem 0;
        width: 100%;
    }
    .step-header-title {
        font-size: 1.5rem; /* 1.54rem → 1.5rem（四捨五入） */
        font-weight: bold;
        color: #1A73E8;
        margin: 0 0 0.5rem 0;
        line-height: 1.3;
    }
    /* サイドメニューの「分析フロー」タイトル */
    section[data-testid="stSidebar"] .sidebar-analysis-flow-title {
        font-size: 1.25rem;
        font-weight: bold;
        color: #1A73E8;
        margin: 0 0 0.8rem 0;
        line-height: 1.3;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    /* サイドメニューのステップ名 */
    section[data-testid="stSidebar"] div.stButton > button > div {
        white-space: pre-line !important;
        line-height: 1.5 !important;
        text-align: left !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif !important;
        font-size: 1.25rem !important;
        font-weight: bold !important;
    }
    /* サイドバーの説明文スタイル（メイン画面の説明文と同じ仕様） */
    section[data-testid="stSidebar"] .step-description {
        font-size: 1.0rem;
        line-height: 1.6;
        margin: 0.3rem 0;
        color: #555555;
        font-weight: 400;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    /* サイドバーの小項目スタイル（メイン画面の小項目と同じ仕様） */
    section[data-testid="stSidebar"] .step-sub-section {
        font-size: 1.1rem;
        font-weight: 600;
        color: #333333;
        margin: 1rem 0 0.5rem 0;
        line-height: 1.4;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    section[data-testid="stSidebar"] .step-sub-section::before {
        content: "■ ";
        color: #333333;
    }
    .step-header-description {
        font-size: 1rem;
        color: #1A73E8;
        margin: 0;
        line-height: 1.6;
    }
    /* テキストボックス型注釈 */
    .annotation-info-box {
        background-color: #E9F2FF;
        color: #1A4DB3;
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        margin: 0.8rem 0;
        line-height: 1.6;
        font-size: 1.0rem;
    }
    .annotation-success-box {
        background-color: #ECF8F2;
        color: #2E7D32;
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        margin: 0.8rem 0;
        line-height: 1.6;
        font-size: 1.0rem;
        display: flex;
        gap: 0.5rem;
        align-items: flex-start;
    }
    .annotation-success-box .icon {
        font-size: 1rem;
        line-height: 1.4;
    }
    .annotation-success-box .text {
        flex: 1;
    }
    .annotation-warning-box {
        background-color: #FFEBEE;
        color: #D32F2F;
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        margin: 0.8rem 0;
        line-height: 1.6;
        font-size: 1.0rem;
        display: flex;
        gap: 0.5rem;
        align-items: flex-start;
    }
    .annotation-warning-box .icon {
        font-size: 1rem;
        line-height: 1.4;
    }
    .annotation-warning-box .text {
        flex: 1;
    }
    /* STEP共通のフォント階層スタイル */
    /* 大項目：中項目フォントサイズ × 1.1 = 1.4rem × 1.1 = 1.54rem → 1.5rem（四捨五入）、STEP名スタイルで統一 */
    .step-main-section {
        font-size: 1.5rem; /* 1.54rem → 1.5rem（小数点第1位で四捨五入） */
        font-weight: bold;
        color: #1A73E8;
        margin: 0 0 1rem 0;
        line-height: 1.3;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    /* 中項目：左青線＋フォントデザイン */
    .step-middle-section {
        border-left: 4px solid #1A73E8;
        padding-left: 10px;
        margin-bottom: 0.5rem;
        margin-top: 1.5rem;
    }
    .step-middle-section p {
        color: #1A73E8;
        margin: 0;
        font-size: 1.4rem;
        font-weight: bold;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    /* 小項目：中項目フォントサイズ × 0.8 = 1.4rem × 0.8 = 1.12rem → 1.1rem（四捨五入）、■＋#333333太字 */
    .step-sub-section {
        font-size: 1.1rem; /* 1.12rem → 1.1rem（小数点第1位で四捨五入） */
        font-weight: 600;
        color: #333333;
        margin: 1rem 0 0.5rem 0;
        line-height: 1.4;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    .step-sub-section::before {
        content: "■ ";
        color: #333333;
    }
    /* 注釈：小項目フォントサイズ × 0.85 = 1.1rem × 0.85 = 0.935rem → 0.9rem（四捨五入）、#555555の通常フォント */
    .step-annotation {
        font-size: 0.9rem; /* 0.935rem → 0.9rem（小数点第1位で四捨五入） */
        font-weight: 400;
        color: #555555;
        margin: 0.3rem 0;
        line-height: 1.6;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    /* 説明文：ステップ説明テキスト用、#555555の通常フォント */
    .step-description {
        font-size: 1.0rem;
        line-height: 1.6;
        margin: 0.3rem 0;
        color: #555555;
        font-weight: 400;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif;
    }
    /* st.caption（💡付き補足説明）のスタイル統一 */
    div[data-testid="stCaption"] {
        color: #555555 !important;
        font-weight: 400 !important;
        line-height: 1.6 !important;
    }
    /* STEP1互換性のためのエイリアス */
    .step1-main-section { font-size: 1.5rem; font-weight: bold; color: #1A73E8; margin: 0 0 1rem 0; line-height: 1.3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif; }
    .step1-middle-section { border-left: 4px solid #1A73E8; padding-left: 10px; margin-bottom: 0.5rem; margin-top: 1.5rem; }
    .step1-middle-section p { color: #1A73E8; margin: 0; font-size: 1.4rem; font-weight: bold; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif; }
    .step1-sub-section { font-size: 1.1rem; font-weight: 600; color: #333333; margin: 1rem 0 0.5rem 0; line-height: 1.4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif; }
    /* 番号（①②③④）がついていない小項目のみ「■」を追加（JavaScriptで動的に処理） */
    .step1-sub-section.with-bullet::before {
        content: "■ ";
        color: #333333;
    }
    .step1-annotation { font-size: 0.9rem; font-weight: 400; color: #555555; margin: 0.3rem 0; line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Arial', sans-serif; }
    /* サイドバーSTEPボタンの改善（左揃え、角丸、アクティブ/非アクティブの色分け） */
    section[data-testid="stSidebar"] div.stButton > button {
        width: 100%;
        align-items: flex-start !important;
        text-align: left !important;
        padding: 0.9rem 1rem !important;
        border-radius: 8px !important;
        justify-content: flex-start !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
        background-color: #1A73E8 !important;
        color: white !important;
        border: none !important;
        font-weight: bold !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
        background-color: #E8F0FE !important;
        color: #1A73E8 !important;
        border: none !important;
        font-weight: bold !important;
    }
    /* ボタン内のすべてのテキスト要素を太字にする */
    section[data-testid="stSidebar"] div.stButton > button * {
        font-weight: bold !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {
        background-color: #D2E3FC !important;
    }
</style>
""", unsafe_allow_html=True)

STD_METHOD_FIXED = "population"  # 母分散（推奨）を固定使用


# slider_with_number_input と関連関数は utils/common.py に移動済み

def main():
    """メイン関数"""
    
    # セッション状態の初期化
    init_session_state()
    
    # ヘッダー（タイトルバナー）
    st.markdown("""
    <div class="title-banner">
        <div class="title-main">安全在庫最適化シミュレーションツール</div>
        <div class="title-sub">理論と実データを融合したデータドリブンなアプローチにより、PSI運用の実態に即して安全在庫を最適化し、計画精度に応じて適切な在庫水準を設定できるようにする</div>
    </div>
    """, unsafe_allow_html=True)
    
    # サイドバー：STEPナビゲーション
    display_sidebar()
    
    # メインコンテンツ：ステップごとの表示
    display_step_content()
    
    # フッター
    st.markdown('<div class="footer">SafetyStock-SimOptimizer_ver1</div>', unsafe_allow_html=True)

def init_session_state():
    """セッション状態を初期化"""
    # ステップ管理の初期化
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 1

    # 算出条件の初期値
    default_settings = {
        "shared_lead_time_type": "working_days",
        "shared_lead_time": 5,
        "shared_stockout_tolerance": 1.0,
        "shared_std_method": STD_METHOD_FIXED
    }
    for key, value in default_settings.items():
        if key not in st.session_state:
            st.session_state[key] = value
    
    # ファイルアップロード関連
    if 'uploaded_monthly_plan_file' not in st.session_state:
        st.session_state.uploaded_monthly_plan_file = None
    if 'uploaded_actual_file' not in st.session_state:
        st.session_state.uploaded_actual_file = None
    if 'uploaded_safety_stock_file' not in st.session_state:
        st.session_state.uploaded_safety_stock_file = None
    if 'uploaded_data_loader' not in st.session_state:
        st.session_state.uploaded_data_loader = None

# display_step_navigation は views/sidebar.py に移動済み

def display_step_content():
    """現在のステップに応じたコンテンツを表示"""
    current_step = st.session_state.current_step
    
    if current_step == 1:
        # STEP 1: データ取り込みと前処理
        st.markdown("""
        <div class="step-header-box">
            <div class="step-header-title">STEP 1：データ取り込みと前処理</div>
            <div class="step-header-description">安全在庫最適化に必要なデータを読み込み、前処理（稼働日マスタの適用など）を行います。また、データ量に応じて ABC 区分を自動生成します。</div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()
        
        # STEP 1のコンテンツ（新しいビューから呼び出し）
        display_step1()
    
    elif current_step == 2:
        # STEP 2: 安全在庫算出ロジック体感（選定機種）
        # ページ最上部にスクロールするための処理
        if st.session_state.get('scroll_to_top', False):
            st.markdown("""
            <script>
            window.scrollTo(0, 0);
            </script>
            """, unsafe_allow_html=True)
            st.session_state.scroll_to_top = False
        st.markdown("""
        <div class="step-header-box">
            <div class="step-header-title">STEP 2：安全在庫算出ロジック体感（選定機種）</div>
            <div class="step-header-description">任意の商品コードを選び、3種類の安全在庫モデルで【需要変動・計画誤差の把握】→【安全在庫の算出】→【異常値処理】→【上限カット】の一連のプロセスを、実際に手を動かしながら操作することで、「安全在庫算定」「異常値処理」「上限カット」の機能と動作を直感的に理解できます。</div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()
        
        # STEP 2のコンテンツ（views/step2_view.pyから呼び出し）
        display_step2()
    
    elif current_step == 3:
        # STEP 3: 安全在庫算出と登録値作成（全機種） - STEP3とSTEP4を統合
        # ページ最上部にスクロールするための処理
        if st.session_state.get('scroll_to_top', False):
            st.markdown("""
            <script>
            window.scrollTo(0, 0);
            </script>
            """, unsafe_allow_html=True)
            st.session_state.scroll_to_top = False
        st.markdown("""
        <div class="step-header-box">
            <div class="step-header-title">STEP 3：安全在庫算出と登録値作成（全機種）</div>
            <div class="step-header-description">すべての商品コードに STEP2 で理解したロジックを適用し、安全在庫を算出します。現行設定と比較し、サマリーで全体傾向を把握します。続いて、異常値処理と上限日数カットを実施し、最終安全在庫を確定します。最後に、確定した安全在庫を SCP 登録用データとして出力します。</div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()
        
        # STEP 3のコンテンツ（views/step3_view.pyから呼び出し）
        display_step3()

# get_representative_products_by_abc は utils/common.py に移動済み
# display_safety_stock_analysis_representative は views/step2_view.py に移動済み
# classify_inventory_days_bin は utils/common.py に移動済み


# display_abc_matrix_comparison は views/step3_view.py に移動済み
# display_plan_actual_statistics, display_delta_statistics, display_safety_stock_comparison,
# display_outlier_processing_results, display_outlier_lt_delta_comparison,
# display_after_processing_comparison, display_after_cap_comparison は views/step2_view.py に移動済み
# display_order_volume_comparison_chart_before と display_order_volume_comparison_chart_after は charts/safety_stock_charts.py に移動済み
# display_safety_stock_analysis_all は views/step3_view.py に移動済み
# display_file_upload_section と process_uploaded_files は views/step1_view.py と utils/data_io.py に移動済み
# display_safety_stock_definitions は views/step1_view.py に移動済み
# display_time_series_chart, display_time_series_delta_bar_chart, display_histogram_with_unified_range, display_product_analysis, display_export_buttons は削除（未使用）

def display_abc_classification_section():
    """ABC区分自動生成セクションを表示"""
    st.markdown('<div class="sub-header">📊 ABC区分自動生成</div>', unsafe_allow_html=True)
    
    # データローダーの取得
    try:
        if hasattr(st.session_state, 'uploaded_data_loader') and st.session_state.uploaded_data_loader is not None:
            data_loader = st.session_state.uploaded_data_loader
        else:
            data_loader = DataLoader("data/日次計画データ.csv", "data/日次実績データ.csv")
            data_loader.load_data()
    except Exception as e:
        st.error(f"データ読み込みエラー: {str(e)}")
        return
    
    # セッション状態の初期化
    if 'abc_categories' not in st.session_state:
        st.session_state.abc_categories = ['A', 'B', 'C']
    if 'abc_method' not in st.session_state:
        st.session_state.abc_method = 'ratio'  # 'ratio' or 'range'
    if 'abc_ratio_settings' not in st.session_state:
        st.session_state.abc_ratio_settings = {'A': {'start': 0, 'end': 50}, 'B': {'start': 50, 'end': 80}, 'C': {'start': 80, 'end': 100}}
    if 'abc_range_settings' not in st.session_state:
        st.session_state.abc_range_settings = {}
    if 'abc_classification_unit' not in st.session_state:
        st.session_state.abc_classification_unit = "全て"
    if 'abc_analysis_result' not in st.session_state:
        st.session_state.abc_analysis_result = None
    if 'uploaded_data_loader' not in st.session_state:
        st.session_state.uploaded_data_loader = None
    
    # 分類単位選択（現時点では固定で全商品）
    st.session_state.abc_classification_unit = "全て"
    st.caption("現在は全商品を対象にABC分析を実行します（分類機能は将来対応）。")
    
    # 設定方法セクション
    st.markdown("### 設定方法")
    st.markdown("#### 区分設定方式")
    
    method = st.radio(
        "区分設定方式",
        options=["ratio", "range"],
        format_func=lambda x: "構成比率で区分" if x == "ratio" else "数量範囲で区分",
        index=0 if st.session_state.abc_method == "ratio" else 1,
        key="abc_method_radio"
    )
    st.session_state.abc_method = method
    
    # 説明文
    if method == "ratio":
        st.info("""
        **構成比率で区分**：
        商品コードを「実績値」の多い順にソートし、指定した累積構成比率に基づいてABC分析を行います。
        ※実績値＝全期間の実績値合計
        """)
    else:
        st.info("""
        **数量範囲で区分**：
        商品コードを「月平均実績値」の多い順にソートし、指定した数量範囲に基づいてABC分析を行います。
        ※月平均実績値＝全期間の実績値合計 ÷ 対象月数
        """)
    
    # 構成比率で区分の場合
    if method == "ratio":
        display_abc_ratio_settings()
    else:
        display_abc_range_settings()
    
    # 実行ボタン
    st.markdown("---")
    if st.button("ABC区分を自動生成する", type="primary", width='stretch'):
        execute_abc_analysis(data_loader)
    
    # 結果表示
    if st.session_state.abc_analysis_result is not None:
        display_abc_results(st.session_state.abc_analysis_result)

def display_abc_ratio_settings():
    """構成比率で区分の設定UI"""
    st.markdown("#### 構成比率設定")
    
    # 区分追加セクション
    col1, col2 = st.columns([3, 1])
    with col1:
        available_categories = ABCAnalysis.get_available_categories(st.session_state.abc_categories)
        if available_categories:
            new_category = st.selectbox(
                "追加する区分",
                options=[""] + [f"{cat}区分" for cat in available_categories],
                key="abc_add_category_ratio"
            )
        else:
            new_category = ""
            st.info("追加できる区分がありません（A〜Zまで全て使用中）")
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("区分を追加する", key="abc_add_ratio") and new_category:
            cat_label = new_category.replace("区分", "")
            if cat_label not in st.session_state.abc_categories:
                st.session_state.abc_categories.append(cat_label)
                # 新しい区分の設定を追加（前の区分の終了％を開始％、100%を終了％とする）
                prev_end = st.session_state.abc_ratio_settings[st.session_state.abc_categories[-2]]['end']
                st.session_state.abc_ratio_settings[cat_label] = {'start': prev_end, 'end': 100}
                # 前の区分の終了％を調整（最終区分は100%固定）
                if len(st.session_state.abc_categories) > 1:
                    prev_cat = st.session_state.abc_categories[-2]
                    if prev_cat != cat_label:
                        st.session_state.abc_ratio_settings[prev_cat]['end'] = prev_end
                st.rerun()
    
    # 区分設定の表示と編集
    for i, cat in enumerate(st.session_state.abc_categories):
        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])
        
        with col1:
            st.markdown(f"**{cat}区分**")
        
        with col2:
            start_val = st.session_state.abc_ratio_settings.get(cat, {}).get('start', 0)
            if i == 0:
                st.number_input("開始％", min_value=0, max_value=100, value=int(start_val), 
                               key=f"abc_ratio_start_{cat}", disabled=True)
            else:
                # 前の区分の終了％が開始％になる（自動計算）
                prev_cat = st.session_state.abc_categories[i-1]
                prev_end = st.session_state.abc_ratio_settings.get(prev_cat, {}).get('end', 0)
                st.number_input("開始％", min_value=0, max_value=100, value=int(prev_end), 
                               key=f"abc_ratio_start_{cat}", disabled=True)
                st.session_state.abc_ratio_settings[cat]['start'] = prev_end
        
        with col3:
            end_val = st.session_state.abc_ratio_settings.get(cat, {}).get('end', 100)
            if i == len(st.session_state.abc_categories) - 1:
                # 最終区分は100%固定
                st.number_input("終了％", min_value=0, max_value=100, value=100, 
                               key=f"abc_ratio_end_{cat}", disabled=True)
                st.session_state.abc_ratio_settings[cat]['end'] = 100
            else:
                new_end = st.number_input("終了％", min_value=0, max_value=100, value=int(end_val), 
                                         key=f"abc_ratio_end_{cat}")
                st.session_state.abc_ratio_settings[cat]['end'] = new_end
        
        with col4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("ℹ️", key=f"abc_info_{cat}", help=f"{cat}区分の説明"):
                pass
        
        with col5:
            st.markdown("<br>", unsafe_allow_html=True)
            if len(st.session_state.abc_categories) > 1 and st.button("🗑️", key=f"abc_delete_{cat}"):
                # 区分を削除
                st.session_state.abc_categories.remove(cat)
                if cat in st.session_state.abc_ratio_settings:
                    del st.session_state.abc_ratio_settings[cat]
                # 最終区分の終了％を100%に設定
                if st.session_state.abc_categories:
                    last_cat = st.session_state.abc_categories[-1]
                    st.session_state.abc_ratio_settings[last_cat]['end'] = 100
                st.rerun()

def display_abc_range_settings():
    """数量範囲で区分の設定UI"""
    st.markdown("#### 数量範囲設定")
    
    # 動的デフォルト値の計算と適用
    if st.session_state.abc_method == "range":
        # 動的デフォルト値を計算
        try:
            if hasattr(st.session_state, 'uploaded_data_loader') and st.session_state.uploaded_data_loader is not None:
                data_loader = st.session_state.uploaded_data_loader
            else:
                data_loader = DataLoader("data/日次計画データ.csv", "data/日次実績データ.csv")
                data_loader.load_data()
            
            abc_analyzer = ABCAnalysis(data_loader, st.session_state.abc_classification_unit)
            dynamic_defaults = abc_analyzer.calculate_dynamic_defaults(st.session_state.abc_categories)
            
            # デフォルト値が設定されていない場合、動的デフォルト値を適用
            if not st.session_state.abc_range_settings or any(
                cat not in st.session_state.abc_range_settings 
                for cat in st.session_state.abc_categories
            ):
                st.session_state.abc_range_settings = dynamic_defaults.copy()
                st.info("""
                **デフォルト値**：
                A区分・B区分の下限値は、選択した対象の月平均実績値に基づき、累積構成比率50%・80%に相当する値として自動計算されます。必要に応じて手動で調整可能です。
                """)
        except Exception:
            pass
    
    # 区分追加セクション
    col1, col2 = st.columns([3, 1])
    with col1:
        available_categories = ABCAnalysis.get_available_categories(st.session_state.abc_categories)
        if available_categories:
            new_category = st.selectbox(
                "追加する区分",
                options=[""] + [f"{cat}区分" for cat in available_categories],
                key="abc_add_category_range"
            )
        else:
            new_category = ""
            st.info("追加できる区分がありません（A〜Zまで全て使用中）")
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("区分を追加する", key="abc_add_range") and new_category:
            cat_label = new_category.replace("区分", "")
            if cat_label not in st.session_state.abc_categories:
                st.session_state.abc_categories.append(cat_label)
                st.session_state.abc_range_settings[cat_label] = 0.0
                st.rerun()
    
    # 区分設定の表示と編集
    for i, cat in enumerate(st.session_state.abc_categories):
        col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 1, 1])
        
        with col1:
            st.markdown(f"**{cat}区分**")
        
        with col2:
            st.markdown("上限<br>**ーー**", unsafe_allow_html=True)
        
        with col3:
            lower_limit = st.session_state.abc_range_settings.get(cat, 0.0)
            # 最終区分は0で固定し、編集不可
            if i == len(st.session_state.abc_categories) - 1:
                st.number_input(
                    "下限値",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key=f"abc_range_lower_{cat}",
                    label_visibility="collapsed",
                    disabled=True
                )
                st.session_state.abc_range_settings[cat] = 0.0
            else:
                col_sub1, col_sub2, col_sub3 = st.columns([1, 3, 1])
                with col_sub1:
                    if st.button("−", key=f"abc_range_minus_{cat}"):
                        st.session_state.abc_range_settings[cat] = max(0.0, lower_limit - 1)
                        st.rerun()
                with col_sub2:
                    new_lower = st.number_input(
                        "下限値",
                        min_value=0.0,
                        value=float(lower_limit),
                        step=1.0,
                        key=f"abc_range_lower_{cat}",
                        label_visibility="collapsed"
                    )
                    st.session_state.abc_range_settings[cat] = new_lower
                with col_sub3:
                    if st.button("＋", key=f"abc_range_plus_{cat}"):
                        st.session_state.abc_range_settings[cat] = lower_limit + 1
                        st.rerun()
        
        with col4:
            if i < len(st.session_state.abc_categories) - 1:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("ℹ️", key=f"abc_info_range_{cat}"):
                    pass
        
        with col5:
            st.markdown("<br>", unsafe_allow_html=True)
            if len(st.session_state.abc_categories) > 1 and st.button("🗑️", key=f"abc_delete_range_{cat}"):
                st.session_state.abc_categories.remove(cat)
                if cat in st.session_state.abc_range_settings:
                    del st.session_state.abc_range_settings[cat]
                st.rerun()

def execute_abc_analysis(data_loader):
    """ABC分析を実行"""
    try:
        abc_analyzer = ABCAnalysis(data_loader, st.session_state.abc_classification_unit)
        
        if st.session_state.abc_method == "ratio":
            # 構成比率で区分
            end_ratios = {cat: st.session_state.abc_ratio_settings[cat]['end'] 
                         for cat in st.session_state.abc_categories}
            analysis_result = abc_analyzer.analyze_by_ratio(st.session_state.abc_categories, end_ratios)
        else:
            # 数量範囲で区分
            lower_limits = {cat: st.session_state.abc_range_settings.get(cat, 0.0) 
                           for cat in st.session_state.abc_categories}
            analysis_result = abc_analyzer.analyze_by_range(st.session_state.abc_categories, lower_limits)
        
        # 集計結果を計算
        aggregation = abc_analyzer.calculate_aggregation_results(analysis_result)
        
        st.session_state.abc_analysis_result = {
            'analysis': analysis_result,
            'aggregation': aggregation
        }
        
        st.success("✅ ABC区分の自動生成が完了しました。以下に、ABC区分の集計結果を表示します。")
        
    except Exception as e:
        st.error(f"エラー: {str(e)}")

def display_abc_results(results):
    """ABC分析結果を表示"""
    st.markdown("---")
    st.markdown("### ABC区分の集計結果")
    
    # 不要メッセージを削除（見出しのみ表示）
    
    # 集計結果テーブル
    aggregation_df = results['aggregation'].copy()
    aggregation_df.columns = ['ABC区分', '件数', '実績合計', '構成比率（％）']
    
    # 数値のフォーマット
    aggregation_df['実績合計'] = aggregation_df['実績合計'].apply(lambda x: f"{x:,.0f}")
    aggregation_df['構成比率（％）'] = aggregation_df['構成比率（％）'].apply(lambda x: f"{x:.2f}")
    
    st.dataframe(aggregation_df, width='stretch', hide_index=True)

if __name__ == "__main__":
    main()