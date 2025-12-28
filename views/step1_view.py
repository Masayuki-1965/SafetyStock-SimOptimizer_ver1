"""
STEP1 ビュー
データ取り込みと前処理のUI
"""

import os
import streamlit as st
from modules.data_loader import DataLoader
from modules.abc_analysis import ABCAnalysis
from modules.utils import get_base_path
from utils.common import has_existing_abc_data
from utils.data_io import process_uploaded_files


def display_safety_stock_definitions():
    """安全在庫モデルの定義を表示"""
    st.markdown('<div class="safety-stock-definitions-section">', unsafe_allow_html=True)
    st.markdown('<div class="sub-header" style="margin-top: 0 !important; margin-bottom: 0.1rem !important; padding-top: 0 !important; padding-bottom: 0 !important;">📘 安全在庫モデルの定義</div>', unsafe_allow_html=True)
    
    # カスタムCSS for レスポンシブ対応と改行
    st.markdown("""
    <style>
    .safety-stock-definitions-section {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    .safety-stock-definitions-section > div {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
    .safety-stock-table {
        width: 100%;
        border-collapse: collapse;
        margin: 0.2rem 0 !important;
        font-size: 17px;
        line-height: 1.6;
    }
    .safety-stock-definitions-section .sub-header {
        margin-top: 0 !important;
        margin-bottom: 0.1rem !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    /* app.pyの.sub-headerスタイルを上書き */
    div.safety-stock-definitions-section div.sub-header {
        margin-top: 0 !important;
        margin-bottom: 0.1rem !important;
    }
    /* Streamlitのデフォルトマージンを強制的に上書き */
    div[data-testid="stMarkdownContainer"] .safety-stock-definitions-section .sub-header,
    div[data-testid="stMarkdownContainer"] .safety-stock-definitions-section + *,
    .safety-stock-definitions-section .sub-header + * {
        margin-top: 0 !important;
    }
    .safety-stock-definitions-section .safety-stock-table:first-of-type {
        margin-top: 0.1rem !important;
    }
    .safety-stock-table {
        margin-top: 0.1rem !important;
    }
    .safety-stock-table th {
        background-color: #1f77b4;
        color: white;
        font-weight: bold;
        text-align: center;
        padding: 12px 8px;
        border: 1px solid #ddd;
    }
    .safety-stock-table td {
        text-align: left;
        vertical-align: top;
        padding: 12px 8px;
        border: 1px solid #ddd;
        word-wrap: break-word;
        word-break: break-word;
        white-space: normal;
    }
    .model-cell {
        font-weight: bold;
        background-color: #f8f9fa;
        text-align: center;
    }
    .model-cell .subtitle {
        font-size: 0.9em;
        font-weight: normal;
    }
    .model-cell .model-subtitle {
        font-size: 0.92em;
        font-weight: bold;
    }
    .formula-cell {
        font-family: 'Courier New', monospace;
        background-color: #f0f8ff;
        font-size: 14.5px;
    }
    .description-cell {
        background-color: #fafafa;
        font-size: 14.5px;
    }
    /* セクション内の行間調整 */
    .safety-stock-section {
        line-height: 1.4 !important;
        margin-top: 0.8rem !important;
        margin-bottom: 0 !important;
        font-size: 14.5px;
    }
    .safety-stock-section p {
        line-height: 1.5 !important;
        margin-bottom: 0.15rem !important;
    }
    .safety-stock-section p:first-child {
        margin-bottom: 0.5rem !important;
    }
    .safety-stock-section p:last-child {
        margin-bottom: 0 !important;
    }
    .safety-stock-section ul {
        line-height: 1.5 !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0 !important;
    }
    .safety-stock-section li {
        margin-bottom: 0.4rem !important;
        line-height: 1.5 !important;
    }
    /* レスポンシブ対応 */
    @media (max-width: 768px) {
        .safety-stock-table {
            font-size: 14px;
        }
        .safety-stock-table th,
        .safety-stock-table td {
            padding: 8px 4px;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # HTMLテーブルで表示（改行対応）
    st.markdown("""
    <table class="safety-stock-table">
        <thead>
            <tr>
                <th style="width: 19%;">モデル</th>
                <th style="width: 43%;">計算式</th>
                <th style="width: 38%;">説明</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td class="model-cell">【安全在庫①】<br><span class="model-subtitle">一般的な理論モデル</span></td>
                <td class="formula-cell"><strong>安全在庫 ＝ 安全係数 Z × 標準偏差 σ × √リードタイム</strong><br>※ LT期間の実績のバラつきを理論式で計算し、安全在庫を決定</td>
                <td class="description-cell">日々の実績データから標準偏差 σ を算出し、安全係数 Z とリードタイムの平方根を掛ける基本式。<strong>教科書的な安全在庫の理論モデル。計画誤差は考慮しない。</strong></td>
            </tr>
            <tr>
                <td class="model-cell">【安全在庫②】<br><span class="model-subtitle">実績バラつき実測モデル</span></td>
                <td class="formula-cell"><strong>リードタイム間差分（実績－平均）<br>＝ リードタイム期間の実績合計 － リードタイム期間実績合計の平均</strong><br>※ LT期間の実績のバラつきを実測し、安全在庫を決定</td>
                <td class="description-cell">LT期間の実績合計を 1 日ずつスライドし、平均を上回るプラス差分（＝実績のバラつきによる欠品リスク）を実測。欠品許容率 p を満たす安全在庫水準を設定。<strong>実績のバラつきを反映するが、計画誤差は考慮しない。</strong></td>
            </tr>
            <tr>
                <td class="model-cell">【安全在庫③】<br><span class="model-subtitle">計画誤差実測モデル (推奨)</span></td>
                <td class="formula-cell"><strong>リードタイム間差分（実績－計画）<br>＝ リードタイム期間の実績合計 － リードタイム期間の計画合計</strong><br>※ LT期間の計画誤差を実測し、安全在庫を決定</td>
                <td class="description-cell">LT期間の実績と計画を 1 日ずつスライドし、実績が計画を上回るプラス差分（＝計画誤差による欠品リスク）を実測。欠品許容率 p を満たす安全在庫水準を設定。<strong>実績のバラつきに加え、計画誤差も反映できる、最も実用的なモデル。</strong></td>
            </tr>
        </tbody>
    </table>
    """, unsafe_allow_html=True)
    
    # パラメータの説明
    st.markdown("""
    <div class="safety-stock-section">
        <p style="margin-bottom: 0.5rem !important; margin-top: 0 !important;"><strong>【パラメータの説明】</strong></p>
        <p style="margin-top: 0 !important; margin-bottom: 0.15rem !important; padding: 0 !important; line-height: 1.5 !important;"><strong>欠品許容率 p</strong>：欠品を 1%（デフォルト値）まで許容する場合、需要変動の 99% をカバーする安全在庫水準を決定します。</p>
        <p style="margin-top: 0 !important; margin-bottom: 0.15rem !important; padding: 0 !important; line-height: 1.5 !important;"><strong>リードタイム LT</strong>：生産（または発注）から在庫計上までの所要期間。稼働日数またはカレンダー日数を任意に指定できます。</p>
        <p style="margin-top: 0 !important; margin-bottom: 0.15rem !important; padding: 0 !important; line-height: 1.5 !important;"><strong>安全係数 Z</strong>：欠品許容率 p に対応する標準正規分布の片側基準値。p = 1% の場合、Z = 2.326（片側 1%）を使用します。</p>
        <p style="margin-top: 0 !important; margin-bottom: 0.15rem !important; padding: 0 !important; line-height: 1.5 !important;"><strong>標準偏差 σ</strong>：日次実績データに基づき、√［Σ（値 − 平均値）² ÷ データ数］で算出します。</p>
        <p style="margin-top: 0 !important; margin-bottom: 0 !important; padding: 0 !important; line-height: 1.5 !important;">※ 安全係数 Z と標準偏差 σ は、安全在庫①（理論モデル）のみに適用します。</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def display_step1():
    """STEP1のUIを表示"""
    # CSVファイルアップロードセクション
    display_file_upload_section()
    
    # ABC区分自動生成セクション（データ取り込み確定後に表示）
    if st.session_state.get('uploaded_data_loader') is not None:
        display_abc_classification_section()


def display_file_upload_section():
    """CSVファイルアップロードセクションを表示"""
    # 中項目
    st.markdown("""
    <div class="step1-middle-section">
        <p>CSVファイルアップロード</p>
    </div>
    """, unsafe_allow_html=True)

    # 必須データの案内
    st.markdown('<div class="step1-sub-section with-bullet">必須データ</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="step-description">データ①〜③は、安全在庫を算出し、現行設定と比較するために必須のデータです。</div>
    """, unsafe_allow_html=True)

    base_path = get_base_path()
    required_files = [
        ("① 月次計画データ", os.path.join(base_path, "data/月次計画データ.csv")),
        ("② 日次実績データ", os.path.join(base_path, "data/日次実績データ.csv")),
        ("③ 安全在庫データ", os.path.join(base_path, "data/安全在庫データ.csv")),
    ]
    
    # 判定ロジック：
    # - アップロードエリア：ファイル名を無視し、存在のみで判定
    # - dataフォルダ：ファイル名で厳格に判定
    has_monthly_plan = (
        st.session_state.get('uploaded_monthly_plan_file_obj') is not None or
        os.path.exists(required_files[0][1])
    )
    has_actual = (
        st.session_state.get('uploaded_actual_file_obj') is not None or
        os.path.exists(required_files[1][1])
    )
    has_safety_stock = (
        st.session_state.get('uploaded_safety_stock_file_obj') is not None or
        os.path.exists(required_files[2][1])
    )
    
    # ①・②は絶対必須、③は比較に必要
    has_required_12 = has_monthly_plan and has_actual
    all_required_files_exist = has_monthly_plan and has_actual and has_safety_stock

    # ケースA：①・②のどちらか、または両方が欠けている場合
    if not has_required_12:
        st.markdown("""
        <div class="annotation-info-box">
            CSVファイルをアップロードしてください。Browse filesでファイルを指定するか、CSVファイルをドラッグ＆ドロップできます。
        </div>
        """, unsafe_allow_html=True)
    # ケースB：①・②は揃っているが③が無い場合
    elif not has_safety_stock:
        st.markdown("""
        <div class="annotation-info-box">
            CSVファイルをアップロードしてください。Browse filesでファイルを指定するか、CSVファイルをドラッグ＆ドロップできます。
        </div>
        """, unsafe_allow_html=True)
    elif all_required_files_exist:
        # すべて揃っている場合
        st.markdown("""
        <div class="annotation-info-box">
            dataフォルダ内に、必須データ（①〜③）がすべて揃っています。<br>別のデータを使用したい場合は、Browse filesでファイルを指定、またはCSVファイルをドラッグ&ドロップしてください。
        </div>
        """, unsafe_allow_html=True)
    
    # ケースBでボタン押下後に表示し続けるエラー注釈
    if st.session_state.get('missing_safety_stock_error', False):
        st.markdown("""
        <div class="annotation-warning-box">
            <span class="icon">⚠</span>
            <div class="text">必須データエラー：③ 安全在庫データがアップロードされていないため、現行設定との比較ができません（安全在庫の算出は可能です）。</div>
        </div>
        """, unsafe_allow_html=True)
    
    # 3列レイアウトで各ファイルタイプのアップロードを配置
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown('<div class="step1-sub-section">① 月次計画データ</div>', unsafe_allow_html=True)
        monthly_plan_file = st.file_uploader(
            "",
            type=['csv'],
            help="形式: 行=商品コード、列=日付（YYYYMM）、セル=数量（数値）",
            key="monthly_plan_uploader",
            label_visibility="collapsed"
        )
        if monthly_plan_file is not None:
            st.session_state.uploaded_monthly_plan_file = monthly_plan_file.name
            st.session_state.uploaded_monthly_plan_file_obj = monthly_plan_file
        elif 'uploaded_monthly_plan_file_obj' in st.session_state:
            # ファイルが削除された場合
            del st.session_state.uploaded_monthly_plan_file_obj
    
    with col2:
        st.markdown('<div class="step1-sub-section">② 日次実績データ</div>', unsafe_allow_html=True)
        actual_file = st.file_uploader(
            "",
            type=['csv'],
            help="形式: 行=商品コード、列=日付（YYYYMMDD）、セル=数量（数値）",
            key="actual_uploader",
            label_visibility="collapsed"
        )
        if actual_file is not None:
            st.session_state.uploaded_actual_file = actual_file.name
            st.session_state.uploaded_actual_file_obj = actual_file
        elif 'uploaded_actual_file_obj' in st.session_state:
            del st.session_state.uploaded_actual_file_obj
    
    with col3:
        st.markdown('<div class="step1-sub-section">③ 安全在庫データ</div>', unsafe_allow_html=True)
        safety_stock_file = st.file_uploader(
            "",
            type=['csv'],
            help="形式: A列=商品コード、B列=安全在庫月数",
            key="safety_stock_uploader",
            label_visibility="collapsed"
        )
        if safety_stock_file is not None:
            st.session_state.uploaded_safety_stock_file = safety_stock_file.name
            st.session_state.uploaded_safety_stock_file_obj = safety_stock_file
            # ③がアップロードされた場合、エラーをクリア（ファイル名は判定条件に含めない）
            if 'missing_safety_stock_error' in st.session_state:
                del st.session_state.missing_safety_stock_error
        elif 'uploaded_safety_stock_file_obj' in st.session_state:
            del st.session_state.uploaded_safety_stock_file_obj

    # データ説明（①②③のDrag and Dropエリアの直下）
    st.markdown("""
    <div style="margin-top: 0.5rem; margin-bottom: 0.5rem; font-size: 14px; line-height: 1.6; color: #555555;">
        <p style="margin: 0 0 0.3rem 0; padding: 0;">※ 月次計画データ：月次計画を稼働日マスタで日割りし、日次計画を作成</p>
        <p style="margin: 0 0 0.3rem 0; padding: 0;">※ 日次実績データ：非稼働日の実績は翌稼働日に合算して集計</p>
        <p style="margin: 0; padding: 0;">※ 安全在庫データ：未登録でも安全在庫算出は可能（現行との比較は不可）</p>
    </div>
    """, unsafe_allow_html=True)

    # 任意データの案内
    st.markdown('<div class="step1-sub-section with-bullet">任意データ</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="step-description">データ④は、現行のABC区分を使用したい場合にのみアップロードしてください。アップロードしない場合は、ABC区分を自動生成できます。</div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="step1-sub-section">④ ABC区分データ（任意）</div>', unsafe_allow_html=True)
    current_abc_file = st.file_uploader(
        "",
        type=['csv'],
        help="形式: A列=商品コード、B列=ABC区分（A/B/C/Z）",
        key="current_abc_uploader",
        label_visibility="collapsed"
    )
    if current_abc_file is not None:
        st.session_state.uploaded_current_abc_file = current_abc_file.name
        st.session_state.uploaded_current_abc_file_obj = current_abc_file
    
    # アップロード完了メッセージ
    has_uploaded_files = (
        st.session_state.get('uploaded_monthly_plan_file_obj') is not None or
        st.session_state.get('uploaded_actual_file_obj') is not None or
        st.session_state.get('uploaded_safety_stock_file_obj') is not None or
        st.session_state.get('uploaded_current_abc_file_obj') is not None
    )
    
    if has_uploaded_files:
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>アップロード完了：</strong>アップロード完了しました。</div>
        </div>
        """, unsafe_allow_html=True)
    
    # データ処理ボタン（全幅表示、常に表示）
    if st.button("データを取り込む（確定）", type="primary", use_container_width=True):
        process_uploaded_files(
            st.session_state.get('uploaded_monthly_plan_file_obj'),
            st.session_state.get('uploaded_actual_file_obj'),
            st.session_state.get('uploaded_safety_stock_file_obj'),
            st.session_state.get('uploaded_current_abc_file_obj')
        )
    
    # アンマッチチェック結果の表示
    display_data_consistency_check_results()
    
    st.divider()


def display_abc_classification_section():
    """ABC区分自動生成セクションを表示"""
    # 中項目
    st.markdown("""
    <div class="step1-middle-section">
        <p>ABC区分自動生成</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 注釈
    st.markdown("""
    <div class="step-description">ABC区分を自動生成するか、現行のABC区分を使用するかを選択してください。</div>
    """, unsafe_allow_html=True)
    
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
    if 'abc_mode' not in st.session_state:
        st.session_state.abc_mode = 'auto'
    if 'abc_option_auto' not in st.session_state:
        st.session_state.abc_option_auto = st.session_state.abc_mode == 'auto'
    if 'abc_option_existing' not in st.session_state:
        st.session_state.abc_option_existing = st.session_state.abc_mode == 'existing'
    if 'abc_active_mode' not in st.session_state:
        st.session_state.abc_active_mode = st.session_state.abc_mode
    if 'abc_analysis_source' not in st.session_state:
        st.session_state.abc_analysis_source = None
    
    # 分類単位選択（現時点では固定で全商品）
    st.session_state.abc_classification_unit = "全て"

    # 利用方式の選択肢
    def handle_auto_toggle():
        if st.session_state.abc_option_auto:
            st.session_state.abc_option_existing = False
            # 自動生成モードに切り替えた場合、既存の現行ABC区分の結果をクリア
            if st.session_state.get('abc_analysis_source') == 'existing':
                st.session_state.abc_analysis_result = None
                st.session_state.abc_analysis_source = None
            # エラーメッセージもクリア
            if 'abc_existing_error' in st.session_state:
                del st.session_state.abc_existing_error

    def handle_existing_toggle():
        if st.session_state.abc_option_existing:
            st.session_state.abc_option_auto = False
            # フラグを設定して、後続のクリア処理をスキップする
            st.session_state.abc_existing_processing = True
            # 現行ABC区分モードに切り替えた瞬間に、即座に反映処理を実行
            # data_loaderをsession_stateから取得
            current_data_loader = st.session_state.get('uploaded_data_loader')
            if current_data_loader is None:
                try:
                    current_data_loader = DataLoader("data/日次計画データ.csv", "data/日次実績データ.csv")
                    current_data_loader.load_data()
                except Exception:
                    st.session_state.abc_existing_error = "データ読み込みエラーが発生しました。"
                    st.session_state.abc_analysis_result = None
                    st.session_state.abc_analysis_source = None
                    st.session_state.abc_existing_processing = False
                    return
            
            if has_existing_abc_data():
                try:
                    results, missing_codes = prepare_existing_abc_results(current_data_loader)
                    st.session_state.abc_analysis_result = results
                    st.session_state.abc_analysis_source = 'existing'
                    st.session_state.abc_existing_missing_codes = missing_codes
                    # エラー状態をクリア
                    if 'abc_existing_error' in st.session_state:
                        del st.session_state.abc_existing_error
                    st.session_state.abc_existing_processing = False
                except ValueError as e:
                    st.session_state.abc_existing_error = str(e)
                    st.session_state.abc_analysis_result = None
                    st.session_state.abc_analysis_source = None
                    st.session_state.abc_existing_processing = False
                except Exception as e:
                    st.session_state.abc_existing_error = f"エラー: {str(e)}"
                    st.session_state.abc_analysis_result = None
                    st.session_state.abc_analysis_source = None
                    st.session_state.abc_existing_processing = False
            else:
                # ABC区分データが読み込まれていない場合
                st.session_state.abc_existing_error = "ABC区分データが読み込まれていません。Browse filesでファイルを指定、またはCSVファイルをドラッグ&ドロップしてください。"
                st.session_state.abc_analysis_result = None
                st.session_state.abc_analysis_source = None
                st.session_state.abc_existing_processing = False

    col_auto, col_existing = st.columns(2)
    with col_auto:
        st.checkbox(
            "チェックすると ABC区分を自動生成します",
            key="abc_option_auto",
            on_change=handle_auto_toggle
        )
    with col_existing:
        st.checkbox(
            "チェックすると 現行のABC区分を使用します",
            key="abc_option_existing",
            on_change=handle_existing_toggle
        )

    previous_mode = st.session_state.get('abc_active_mode', st.session_state.abc_mode)
    auto_selected = st.session_state.abc_option_auto
    existing_selected = st.session_state.abc_option_existing

    if auto_selected:
        st.session_state.abc_mode = 'auto'
    elif existing_selected:
        st.session_state.abc_mode = 'existing'
    else:
        st.session_state.abc_mode = None

    # モードが変更された場合の処理
    # handle_existing_toggle内で処理中の場合は、結果をクリアしない
    if previous_mode != st.session_state.abc_mode:
        # handle_existing_toggle内で処理中でない場合のみクリア
        if not st.session_state.get('abc_existing_processing', False):
            # existingモードから他のモードに切り替えた場合のみクリア
            if previous_mode == 'existing' and st.session_state.abc_mode != 'existing':
                st.session_state.abc_analysis_result = None
                st.session_state.abc_analysis_source = None
                if 'abc_existing_error' in st.session_state:
                    del st.session_state.abc_existing_error
            # autoモードから他のモードに切り替えた場合もクリア
            elif previous_mode == 'auto' and st.session_state.abc_mode != 'auto':
                st.session_state.abc_analysis_result = None
                st.session_state.abc_analysis_source = None
    else:
        # モードが変更されていない場合、処理フラグをクリア（rerun後の再実行時）
        if 'abc_existing_processing' in st.session_state:
            del st.session_state.abc_existing_processing
    
    st.session_state.abc_active_mode = st.session_state.abc_mode

    if st.session_state.abc_mode == 'auto':
        # 設定方法セクション（小項目）
        st.markdown('<div class="step1-sub-section with-bullet">設定方法</div>', unsafe_allow_html=True)
        
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
            st.markdown("""
            <div class="annotation-info-box">
                <strong>構成比率で区分</strong>：商品コードを「実績値」の多い順にソートし、指定した累積構成比率に基づいてABC分析を行います。
                ※実績値＝全期間の実績値合計
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="annotation-info-box">
                <strong>数量範囲で区分</strong>：商品コードを「月平均実績値」の多い順にソートし、指定した数量範囲に基づいてABC分析を行います。
                ※月平均実績値＝全期間の実績値合計 ÷ 対象月数
            </div>
            """, unsafe_allow_html=True)
        
        # 構成比率で区分の場合
        if method == "ratio":
            display_abc_ratio_settings()
        else:
            display_abc_range_settings()
        
        # 実行ボタン
        if st.button("ABC区分を自動生成する", type="primary", use_container_width=True):
            execute_abc_analysis(data_loader)
        
        # 結果表示（自動生成モードの場合のみ）
        if st.session_state.abc_analysis_result is not None:
            display_abc_results(st.session_state.abc_analysis_result)
    elif st.session_state.abc_mode == 'existing':
        display_existing_abc_summary(data_loader)
    else:
        st.info("ABC区分の扱いを選択すると設定内容が表示されます。")


def display_abc_ratio_settings():
    """構成比率で区分の設定UI"""
    st.markdown('<div class="step1-sub-section with-bullet">構成比率設定</div>', unsafe_allow_html=True)
    
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
            st.markdown("""
            <div class="annotation-info-box">追加できる区分がありません（A〜Zまで全て使用中）</div>
            """, unsafe_allow_html=True)
    
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
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        
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
                # catがabc_ratio_settingsに存在しない場合は初期化
                if cat not in st.session_state.abc_ratio_settings:
                    st.session_state.abc_ratio_settings[cat] = {'start': prev_end, 'end': 100}
                else:
                    st.session_state.abc_ratio_settings[cat]['start'] = prev_end
        
        with col3:
            end_val = st.session_state.abc_ratio_settings.get(cat, {}).get('end', 100)
            if i == len(st.session_state.abc_categories) - 1:
                # 最終区分は100%固定
                st.number_input("終了％", min_value=0, max_value=100, value=100, 
                               key=f"abc_ratio_end_{cat}", disabled=True)
                # catがabc_ratio_settingsに存在しない場合は初期化
                if cat not in st.session_state.abc_ratio_settings:
                    st.session_state.abc_ratio_settings[cat] = {'start': start_val if i == 0 else st.session_state.abc_ratio_settings.get(st.session_state.abc_categories[i-1], {}).get('end', 0), 'end': 100}
                else:
                    st.session_state.abc_ratio_settings[cat]['end'] = 100
            else:
                new_end = st.number_input("終了％", min_value=0, max_value=100, value=int(end_val), 
                                         key=f"abc_ratio_end_{cat}")
                # catがabc_ratio_settingsに存在しない場合は初期化
                if cat not in st.session_state.abc_ratio_settings:
                    st.session_state.abc_ratio_settings[cat] = {'start': start_val if i == 0 else st.session_state.abc_ratio_settings.get(st.session_state.abc_categories[i-1], {}).get('end', 0), 'end': new_end}
                else:
                    st.session_state.abc_ratio_settings[cat]['end'] = new_end
        
        with col4:
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
    st.markdown('<div class="step1-sub-section with-bullet">数量範囲設定</div>', unsafe_allow_html=True)
    
    # 注釈を表示（数量範囲で区分を選択した時のみ）
    st.markdown("""
    <div class="annotation-info-box"><strong>デフォルト値</strong>：A区分・B区分の下限値は、累積構成比率50%・80%に相当する値で自動計算されています。必要に応じて手動で調整可能です。</div>
    """, unsafe_allow_html=True)
    
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
            st.markdown("""
            <div class="annotation-info-box">追加できる区分がありません（A〜Zまで全て使用中）</div>
            """, unsafe_allow_html=True)
    
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
        col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
        
        with col1:
            st.markdown(f"**{cat}区分**")
        
        with col2:
            st.markdown("下限値", unsafe_allow_html=True)
        
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
                col_sub1, col_sub2 = st.columns([3, 2])
                with col_sub1:
                    new_lower = st.number_input(
                        "下限値",
                        min_value=0.0,
                        value=float(lower_limit),
                        step=1.0,
                        key=f"abc_range_lower_{cat}",
                        label_visibility="collapsed"
                    )
                    st.session_state.abc_range_settings[cat] = new_lower
                with col_sub2:
                    st.markdown("<div style='padding-top: 0.5rem;'>以上（月平均）</div>", unsafe_allow_html=True)
        
        with col4:
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
        
        # ABC区分表示列を追加
        from utils.common import add_abc_category_display_column, check_has_unclassified_products
        analysis_result_with_display = add_abc_category_display_column(analysis_result)
        
        st.session_state.abc_analysis_result = {
            'analysis': analysis_result_with_display,
            'aggregation': aggregation
        }
        st.session_state.abc_analysis_source = 'auto'
        st.session_state.abc_existing_missing_codes = set()
        
        # ABC区分がNaNの商品が存在する場合のフラグを設定
        st.session_state.has_unclassified_products = check_has_unclassified_products(analysis_result)
        
        # 全体計画誤差率（加重平均）を計算してセッション状態に保存
        from utils.common import calculate_weighted_average_plan_error_rate
        weighted_avg_plan_error_rate = calculate_weighted_average_plan_error_rate(
            data_loader,
            analysis_result=analysis_result_with_display,
            exclude_plan_only=True,
            exclude_actual_only=True
        )
        st.session_state.weighted_average_plan_error_rate = weighted_avg_plan_error_rate
        
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>ABC区分の自動生成完了：</strong>集計結果を確認し、次のステップに進んでください。</div>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"エラー: {str(e)}")


def display_abc_results(results):
    """ABC分析結果を表示"""
    from utils.common import format_abc_category_for_display, check_has_unclassified_products
    
    st.markdown("---")
    st.markdown('<div class="step1-sub-section with-bullet">ABC区分の集計結果</div>', unsafe_allow_html=True)
    
    # ABC区分がNaNの商品が存在する場合の注意喚起注釈を表示
    analysis_df = results.get('analysis')
    if analysis_df is not None and check_has_unclassified_products(analysis_df):
        st.markdown("""
        <div class="annotation-warning-box">
            <span class="icon">⚠</span>
            <div class="text">ABC区分が存在しない商品があります。これらは「未分類」として扱っています。</div>
        </div>
        """, unsafe_allow_html=True)
    
    # 集計結果テーブル
    aggregation_df = results['aggregation'].copy()
    aggregation_df.columns = ['ABC区分', '商品コード数（件数）', '実績合計', '構成比率（％）']
    
    # ABC区分の表示変換（NaNの場合は「未分類」）
    aggregation_df['ABC区分'] = aggregation_df['ABC区分'].apply(format_abc_category_for_display)
    # 「区分」を追加（「合計」と「未分類」はそのまま）
    aggregation_df['ABC区分'] = aggregation_df['ABC区分'].apply(
        lambda x: f"{x}区分" if x not in ["合計", "未分類"] else x
    )
    
    # 数値のフォーマット（すべて文字列に変換して左寄せにする）
    aggregation_df['商品コード数（件数）'] = aggregation_df['商品コード数（件数）'].apply(lambda x: f"{x:,.0f}")
    aggregation_df['実績合計'] = aggregation_df['実績合計'].apply(lambda x: f"{x:,.0f}")
    aggregation_df['構成比率（％）'] = aggregation_df['構成比率（％）'].apply(lambda x: f"{x:.2f}")
    
    st.dataframe(aggregation_df, use_container_width=True, hide_index=True)


def apply_existing_abc_results(data_loader):
    """現行ABC区分データを反映し、セッションに保存"""
    if not has_existing_abc_data():
        st.markdown("""
        <div class="annotation-warning-box">
            <span class="icon">⚠</span>
            <div class="text">ABC区分データが読み込まれていません。Browse filesでファイルを指定、またはCSVファイルをドラッグ&ドロップしてください。</div>
        </div>
        """, unsafe_allow_html=True)
        return False
    
    existing_df = st.session_state.get('existing_abc_df')
    
    try:
        results, missing_codes = prepare_existing_abc_results(data_loader)
    except ValueError as e:
        st.warning(str(e))
        return False
    except Exception as e:
        st.error(f"エラー: {str(e)}")
        return False
    
    st.session_state.abc_analysis_result = results
    st.session_state.abc_analysis_source = 'existing'
    st.session_state.abc_existing_missing_codes = missing_codes
    
    # 全体計画誤差率（加重平均）を計算してセッション状態に保存
    from utils.common import calculate_weighted_average_plan_error_rate
    weighted_avg_plan_error_rate = calculate_weighted_average_plan_error_rate(
        data_loader,
        analysis_result=results['analysis'],
        exclude_plan_only=True,
        exclude_actual_only=True
    )
    st.session_state.weighted_average_plan_error_rate = weighted_avg_plan_error_rate
    
    return True


def prepare_existing_abc_results(data_loader):
    """現行ABC区分データを基に集計結果を作成"""
    if not has_existing_abc_data():
        raise ValueError("現行ABC区分データが読み込まれていません。")
    
    existing_df = st.session_state.get('existing_abc_df')
    
    normalized_df = existing_df.copy()
    normalized_df = normalized_df.dropna(subset=['product_code', 'abc_category'])
    normalized_df = normalized_df.drop_duplicates(subset='product_code', keep='last')
    
    if normalized_df.empty:
        raise ValueError("現行ABC区分データに有効な商品コードがありません。")
    
    abc_analyzer = ABCAnalysis(data_loader, st.session_state.abc_classification_unit)
    products_df = abc_analyzer.get_all_products_data()
    merged_df = products_df.merge(normalized_df, on='product_code', how='inner')
    
    if merged_df.empty:
        raise ValueError("現行ABC区分データの商品コードが実績データに一致しません。")
    
    aggregation = abc_analyzer.calculate_aggregation_results(
        merged_df[['product_code', 'abc_category', 'total_actual', 'monthly_avg_actual']]
    )
    
    missing_codes = set(normalized_df['product_code']) - set(merged_df['product_code'])
    
    # ABC区分表示列を追加
    from utils.common import add_abc_category_display_column, check_has_unclassified_products
    analysis_df = merged_df[['product_code', 'abc_category', 'total_actual', 'monthly_avg_actual']].copy()
    analysis_df_with_display = add_abc_category_display_column(analysis_df)
    
    results = {
        'analysis': analysis_df_with_display,
        'aggregation': aggregation
    }
    
    # ABC区分がNaNの商品が存在する場合のフラグを設定
    st.session_state.has_unclassified_products = check_has_unclassified_products(analysis_df)
    
    return results, missing_codes


def display_existing_abc_summary(data_loader):
    """現行ABC区分データの集計結果を表示"""
    existing_df_available = has_existing_abc_data()
    
    # ABC区分データが読み込まれた場合、エラーをクリアして結果を自動生成
    if existing_df_available:
        # エラー状態をクリア（ABC区分CSVが正常に読み込まれたため）
        if 'abc_existing_error' in st.session_state:
            del st.session_state.abc_existing_error
        
        # 結果がまだ設定されていない場合、自動的に結果を生成
        has_result = (
            st.session_state.get('abc_analysis_source') == 'existing' and
            st.session_state.get('abc_analysis_result') is not None
        )
        
        if not has_result:
            try:
                results, missing_codes = prepare_existing_abc_results(data_loader)
                st.session_state.abc_analysis_result = results
                st.session_state.abc_analysis_source = 'existing'
                st.session_state.abc_existing_missing_codes = missing_codes
                has_result = True
            except ValueError as e:
                st.session_state.abc_existing_error = str(e)
                st.warning(str(e))
                return
            except Exception as e:
                st.session_state.abc_existing_error = f"エラー: {str(e)}"
                st.error(f"エラー: {str(e)}")
                return
    else:
        # データが読み込まれていない場合
        has_result = (
            st.session_state.get('abc_analysis_source') == 'existing' and
            st.session_state.get('abc_analysis_result') is not None
        )
        
        # エラーメッセージの表示（結果が存在しない場合のみ）
        if not has_result:
            st.markdown("""
            <div class="annotation-warning-box">
                <span class="icon">⚠</span>
                <div class="text">ABC区分データが読み込まれていません。Browse filesでファイルを指定、またはCSVファイルをドラッグ&ドロップしてください。</div>
            </div>
            """, unsafe_allow_html=True)
            return
    
    # 集計結果の表示
    # abc_analysis_sourceが'existing'で、abc_analysis_resultが存在する場合に表示
    if has_result:
        # 成功メッセージと集計結果を表示
        st.markdown("---")
        st.markdown('<div class="step1-sub-section">ABC区分の集計結果</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>ABC区分の集計結果：</strong>現行ABC区分の集計結果を表示します。</div>
        </div>
        """, unsafe_allow_html=True)
        display_abc_results(st.session_state.abc_analysis_result)
        
        missing_codes = st.session_state.get('abc_existing_missing_codes') or set()
        if missing_codes:
            st.info(f"現行ABC区分データに含まれる {len(missing_codes)} 件の商品コードが実績データに存在しません。対象外として集計しました。")


def display_data_consistency_check_results():
    """データ整合性チェック結果（アンマッチリスト）を表示"""
    import pandas as pd
    from utils.data_io import dataframe_to_csv_bytes
    
    # アンマッチチェック結果が存在するか確認（サマリーデータと詳細データ）
    mismatch_summary_df = st.session_state.get('product_code_mismatch_summary_df')
    mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
    
    # データが読み込まれていない場合は表示しない
    if mismatch_summary_df is None:
        return
    
    # アンマッチがない場合
    if mismatch_summary_df.empty or len(mismatch_summary_df) == 0:
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>アンマッチ確認結果：</strong> 商品コードのアンマッチはありません。すべてのデータが整合しています。</div>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # アンマッチがある場合
    st.markdown("""
    <div class="annotation-success-box">
        <span class="icon">✅</span>
        <div class="text"><strong>アンマッチ確認結果：</strong> 一部の商品コードにアンマッチがあります。下のアンマッチリストを確認してください。</div>
    </div>
    """, unsafe_allow_html=True)
    
    # 中項目タイトル
    st.markdown("""
    <div class="step1-middle-section">
        <p>データ整合性チェック結果サマリー</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 小項目タイトルとCSVダウンロードボタンを横並びに配置
    col_title, col_download = st.columns([4, 1])
    
    with col_title:
        st.markdown('<div class="step1-sub-section with-bullet">商品コードアンマッチリスト</div>', unsafe_allow_html=True)
    
    with col_download:
        # CSVダウンロードボタン（右上に配置、詳細データをダウンロード）
        if mismatch_detail_df is not None and not mismatch_detail_df.empty:
            csv_bytes = dataframe_to_csv_bytes(mismatch_detail_df)
            st.download_button(
                label="Download as CSV",
                data=csv_bytes,
                file_name="data_consistency_mismatch_list.csv",
                mime="text/csv",
                key="download_mismatch_list",
                help="アンマッチリスト（全件）をCSV形式でダウンロードします"
            )
    
    # HTMLテーブルで表示（カラム幅を完全に制御）
    st.markdown("""
    <style>
    .mismatch-list-table {
        width: 100%;
        border-collapse: collapse;
        margin: 0.5rem 0;
        font-size: 14px;
        table-layout: fixed;
    }
    .mismatch-list-table th {
        background-color: #f0f2f6;
        color: #262730;
        font-weight: normal;
        text-align: left;
        padding: 10px 12px;
        border: 1px solid #e0e0e0;
        white-space: normal;
        word-wrap: break-word;
    }
    .mismatch-list-table td {
        padding: 10px 12px;
        border: 1px solid #e0e0e0;
        white-space: normal;
        word-wrap: break-word;
        overflow-wrap: break-word;
        word-break: break-word;
    }
    /* 区分列（1列目）- 18% */
    .mismatch-list-table th:nth-child(1),
    .mismatch-list-table td:nth-child(1) {
        width: 15%;
        text-align: left;
    }
    /* 商品コード件数列（2列目）- 15%（最小限の幅） */
    .mismatch-list-table th:nth-child(2),
    .mismatch-list-table td:nth-child(2) {
        width: 12%;
        text-align: left;
        white-space: nowrap;
        padding: 10px 6px;
    }
    /* 例列（3列目）- 15% */
    .mismatch-list-table th:nth-child(3),
    .mismatch-list-table td:nth-child(3) {
        width: 15%;
        text-align: left;
    }
    /* 説明列（4列目）- 52%（広く） */
    .mismatch-list-table th:nth-child(4),
    .mismatch-list-table td:nth-child(4) {
        width: 58%;
        text-align: left;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # DataFrameをHTMLテーブルに変換
    html_table = '<table class="mismatch-list-table"><thead><tr>'
    for col in mismatch_summary_df.columns:
        html_table += f'<th>{col}</th>'
    html_table += '</tr></thead><tbody>'
    
    for _, row in mismatch_summary_df.iterrows():
        html_table += '<tr>'
        for col in mismatch_summary_df.columns:
            value = str(row[col])
            # HTMLエスケープ処理
            value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html_table += f'<td>{value}</td>'
        html_table += '</tr>'
    
    html_table += '</tbody></table>'
    st.markdown(html_table, unsafe_allow_html=True)
    
    # 折り畳み式注釈「商品コードアンマッチリストの見方」を追加（テーブルの下に配置）
    with st.expander("商品コードアンマッチリストの見方", expanded=False):
        st.markdown("""
        <style>
        .mismatch-guide-table {
            width: 100%;
            border-collapse: collapse;
            margin: 0.5rem 0;
            font-size: 14px;
        }
        .mismatch-guide-table th {
            background-color: #f0f2f6;
            color: #262730;
            font-weight: normal;
            text-align: left;
            padding: 10px 12px;
            border: 1px solid #e0e0e0;
            white-space: normal;
            word-wrap: break-word;
        }
        .mismatch-guide-table td {
            padding: 10px 12px;
            border: 1px solid #e0e0e0;
            white-space: normal;
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: break-word;
            vertical-align: top;
        }
        .mismatch-guide-table th:nth-child(1),
        .mismatch-guide-table td:nth-child(1) {
            width: 12%;
        }
        .mismatch-guide-table th:nth-child(2),
        .mismatch-guide-table td:nth-child(2) {
            width: 88%;
        }
        .mismatch-guide-note {
            margin-top: 1rem;
            font-size: 0.9rem;
            color: #555555;
            line-height: 1.6;
        }
        .mismatch-guide-note p {
            margin: 0.3rem 0;
        }
        </style>
        <table class="mismatch-guide-table">
            <thead>
                <tr>
                    <th>区分</th>
                    <th>メッセージの詳細</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>計画のみ</td>
                    <td>実績データが存在しないため、安全在庫を算出できません。原因を確認し、必要であれば実績データを整備した上で再度アップロードしてください。</td>
                </tr>
                <tr>
                    <td>実績のみ</td>
                    <td>実績は存在するものの、計画データが登録されていません。計画データを確認し、必要な場合は計画を追加した上で再度アップロードしてください。</td>
                </tr>
                <tr>
                    <td>安全在庫なし</td>
                    <td>計画・実績の両方が存在しているにもかかわらず、安全在庫が未設定の状態です。安全在庫の新規設定候補となります。</td>
                </tr>
                <tr>
                    <td>安全在庫あり</td>
                    <td>安全在庫は設定されていますが、計画データ・実績データともに存在しません。安全在庫設定を解除してください。</td>
                </tr>
            </tbody>
        </table>
        <div class="mismatch-guide-note">
            <p>※ レコード存在の有無を示す判定（ゼロ判定ではない）</p>
        </div>
        """, unsafe_allow_html=True)

