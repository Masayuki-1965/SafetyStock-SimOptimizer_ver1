"""
STEP2 ビュー
安全在庫算出ロジック体感（選定機種）のUI
"""

import streamlit as st
import pandas as pd
import numpy as np
from modules.data_loader import DataLoader
from modules.safety_stock_models import SafetyStockCalculator
from modules.outlier_handler import OutlierHandler
from utils.common import (
    slider_with_number_input,
    get_representative_products_by_abc,
    get_abc_analysis_with_fallback,
    calculate_plan_error_rate,
    is_plan_anomaly
)
from views.step1_view import display_safety_stock_definitions
from charts.safety_stock_charts import (
    create_time_series_chart,
    create_time_series_delta_bar_chart,
    create_histogram_with_unified_range,
    create_outlier_processing_results_chart,
    create_outlier_lt_delta_comparison_chart,
    create_after_processing_comparison_chart
)

# 標準偏差の計算方法（固定）
STD_METHOD_FIXED = "population"  # 母分散（推奨）を固定使用


def display_step2():
    """STEP2のUIを表示"""
    # データローダーの取得
    try:
        if st.session_state.uploaded_data_loader is not None:
            data_loader = st.session_state.uploaded_data_loader
        else:
            data_loader = DataLoader("data/日次計画データ.csv", "data/日次実績データ.csv")
            data_loader.load_data()
        
        product_list = data_loader.get_product_list()
    except Exception as e:
        st.error(f"データ読み込みエラー: {str(e)}")
        return
    
    if not product_list:
        st.warning("⚠️ 分析対象の機種がありません。STEP 1でデータを取り込んでください。")
        return

    from utils.common import format_abc_category_for_display, check_has_unclassified_products
    
    raw_analysis = st.session_state.get('abc_analysis_result')
    analysis_result, abc_categories, abc_warning = get_abc_analysis_with_fallback(
        data_loader,
        product_list,
        analysis_result=raw_analysis.get('analysis') if raw_analysis else None
    )

    if abc_warning:
        st.markdown("""
        <div class="annotation-warning-box">
            <span class="icon">⚠</span>
            <div class="text">ABC区分がないため、ABC区分別の評価はできません。</div>
        </div>
        """, unsafe_allow_html=True)
    
    # ABC区分がNaNの商品が存在する場合の注意喚起注釈を表示
    if check_has_unclassified_products(analysis_result):
        st.markdown("""
        <div class="annotation-warning-box">
            <span class="icon">⚠</span>
            <div class="text">ABC区分が存在しない商品があります。これらは「未分類」として扱っています。</div>
        </div>
        """, unsafe_allow_html=True)
    
    abc_category_map = dict(zip(analysis_result['product_code'], analysis_result['abc_category']))
    
    def get_product_category(product_code):
        value = abc_category_map.get(product_code)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        return value
    
    # ABC区分ごとの機種を自動選定
    auto_representative_products = get_representative_products_by_abc(data_loader)
    
    if not auto_representative_products:
        st.warning("⚠️ 機種を選定できませんでした。ABC分析結果を確認してください。")
        return
    
    # 全ABC区分の商品を取得し、実績値（累計）の多い順にソート
    # ABC区分ラベル付きで商品コードを表示
    all_products_with_category = analysis_result[['product_code', 'abc_category', 'total_actual']].copy()
    all_products_with_category = all_products_with_category.sort_values('total_actual', ascending=False).reset_index(drop=True)
    
    # 表示用ラベルを作成（例：A | TT-XXXXX-AAAA、NaNの場合は「未分類」）
    all_products_with_category['display_label'] = all_products_with_category.apply(
        lambda row: f"{format_abc_category_for_display(row['abc_category'])} | {row['product_code']}", axis=1
    )
    
    # 商品コードとラベルのマッピングを作成
    product_code_to_label = dict(zip(all_products_with_category['product_code'], all_products_with_category['display_label']))
    label_to_product_code = {v: k for k, v in product_code_to_label.items()}
    
    # デフォルト値：最初のABC区分の機種、または実績値最大の機種
    default_category = abc_categories[0]
    default_product = auto_representative_products.get(default_category, None)
    
    # デフォルト商品が存在しない場合は、実績値最大の機種を使用
    if default_product is None or default_product not in product_code_to_label:
        default_product = all_products_with_category.iloc[0]['product_code']
    
    default_label = product_code_to_label.get(default_product, all_products_with_category.iloc[0]['display_label'])
    
    # ========== 安全在庫モデル定義セクション ==========
    display_safety_stock_definitions()
    st.divider()
    
    # ========== 手順①：対象商品コードを選択する ==========
    st.markdown("""
    <div class="step-middle-section">
        <p>手順①：対象商品コードを選択する</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="step-description">分析対象の商品コードを選択します。<br><strong>「任意の商品コード」</strong>から選択するか、計画誤差率（％）の閾値を設定し、<strong>「計画誤差率（プラス）大」</strong>または<strong>「計画誤差率（マイナス）大」</strong>を選択してください。</div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 計画誤差率の閾値設定
    st.markdown('<div class="step-sub-section">計画誤差率の閾値設定</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        plan_plus_threshold = st.number_input(
            "計画誤差率（プラス）の閾値（%）",
            min_value=0.0,
            max_value=500.0,
            value=st.session_state.get("step2_plan_plus_threshold", 50.0),
            step=5.0,
            help="計画誤差率がこの値以上の場合、計画誤差率（プラス）大として扱います。",
            key="step2_plan_plus_threshold"
        )
    with col2:
        plan_minus_threshold = st.number_input(
            "計画誤差率（マイナス）の閾値（%）",
            min_value=-500.0,
            max_value=0.0,
            value=st.session_state.get("step2_plan_minus_threshold", -50.0),
            step=5.0,
            help="計画誤差率がこの値以下の場合、計画誤差率（マイナス）大として扱います。",
            key="step2_plan_minus_threshold"
        )
    
    # 商品コード選択モード
    st.markdown('<div class="step-sub-section">商品コードの選択</div>', unsafe_allow_html=True)
    selection_mode = st.radio(
        "選択モード",
        options=["任意の商品コード", "計画誤差率（プラス）大", "計画誤差率（マイナス）大"],
        help="任意の商品コードから選択するか、計画誤差率が大きい商品コードから選択できます。",
        horizontal=True,
        key="step2_selection_mode"
    )
    
    # 計画誤差率を計算して商品リストをフィルタリング
    filtered_products = []
    if selection_mode == "任意の商品コード":
        filtered_products = all_products_with_category.copy()
        st.markdown("""
        <div class="annotation-info-box">💡 <strong>任意の商品コードから選択できます。</strong>まずはここから選んで問題ありません。</div>
        """, unsafe_allow_html=True)
    else:
        # 計画誤差率を計算
        plan_error_rates = {}
        for product_code in product_list:
            try:
                plan_data = data_loader.get_daily_plan(product_code)
                actual_data = data_loader.get_daily_actual(product_code)
                plan_error_rate, _, _ = calculate_plan_error_rate(actual_data, plan_data)
                plan_error_rates[product_code] = plan_error_rate
            except Exception:
                plan_error_rates[product_code] = None
        
        # フィルタリング
        if selection_mode == "計画誤差率（プラス）大":
            filtered_products = all_products_with_category[
                all_products_with_category['product_code'].apply(
                    lambda x: plan_error_rates.get(x) is not None and plan_error_rates.get(x) >= plan_plus_threshold
                )
            ].copy()
            st.markdown(f"""
            <div class="annotation-info-box">
                <strong>計画誤差率が大きい（+{plan_plus_threshold:.1f}%以上）商品コードを選択できます。</strong><br><strong>計画プラス誤差率</strong> ＝（実績合計 − 計画合計）÷ 計画合計 × 100%（<strong>※実績合計 ＞ 計画合計</strong>：実績がどれだけ計画を上回ったか）
            </div>
            """, unsafe_allow_html=True)
        elif selection_mode == "計画誤差率（マイナス）大":
            filtered_products = all_products_with_category[
                all_products_with_category['product_code'].apply(
                    lambda x: plan_error_rates.get(x) is not None and plan_error_rates.get(x) <= plan_minus_threshold
                )
            ].copy()
            st.markdown(f"""
            <div class="annotation-info-box">
                <strong>計画誤差率が大きい（{plan_minus_threshold:.1f}%以下）商品コードを選択できます。</strong><br><strong>計画マイナス誤差率</strong> ＝（実績合計 − 計画合計）÷ 計画合計 × 100%（<strong>※実績合計 ＜ 計画合計</strong>：実績がどれだけ計画を下回ったか）
            </div>
            """, unsafe_allow_html=True)
        
        if filtered_products.empty:
            st.warning(f"⚠️ {selection_mode}に該当する商品コードがありません。")
            filtered_products = all_products_with_category.copy()
    
    # 商品コード選択プルダウン
    if not filtered_products.empty:
        filtered_products = filtered_products.sort_values('total_actual', ascending=False).reset_index(drop=True)
        filtered_labels = filtered_products['display_label'].tolist()
        
        # デフォルト値の設定
        if selection_mode == "任意の商品コード":
            default_label = default_label
        else:
            default_label = filtered_labels[0] if filtered_labels else default_label
        
        default_index = filtered_labels.index(default_label) if default_label in filtered_labels else 0
        
        selected_label = st.selectbox(
            "商品コード",
            options=filtered_labels,
            index=default_index,
            key="step2_selected_product_label",
            help="分析対象の商品コードを選択してください。"
        )
        
        selected_product = label_to_product_code.get(selected_label, default_product)
    else:
        selected_product = default_product
        selected_label = default_label
    
    st.divider()
    
    # ========== 手順②：算出条件を設定する ==========
    st.markdown("""
    <div class="step-middle-section">
        <p>手順②：算出条件を設定する</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="step-description">安全在庫算出に必要な条件（リードタイム、欠品許容率、標準偏差の計算方法）を設定します。<br>これらの設定値は、後続の手順で使用される安全在庫モデルの算出に影響します。</div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # リードタイム設定
    st.markdown('<div class="step-sub-section">リードタイムの設定</div>', unsafe_allow_html=True)
    lead_time_type = st.radio(
        "リードタイムの種別",
        options=["working_days", "calendar"],
        format_func=lambda x: "稼働日数" if x == "working_days" else "カレンダー日数",
        help="稼働日数：土日祝除く、カレンダー日数：土日祝含む",
        horizontal=True,
        key="shared_lead_time_type",
        index=0
    )
    
    lead_time = slider_with_number_input(
        "リードタイム",
        min_value=1,
        max_value=60,
        default_value=st.session_state.get("shared_lead_time", 5),
        key_prefix="shared_lead_time",
        step=1,
        help="1日〜60日の範囲で設定できます。"
    )
    
    # 欠品許容率設定
    st.markdown('<div class="step-sub-section">欠品許容率の設定</div>', unsafe_allow_html=True)
    stockout_tolerance = slider_with_number_input(
        "欠品許容率（%）",
        min_value=0.0,
        max_value=10.0,
        default_value=st.session_state.get("shared_stockout_tolerance", 1.0),
        key_prefix="shared_stockout_tolerance",
        step=0.1,
        help="0％〜10％の範囲で欠品許容率を設定できます。",
        format="%.1f"
    )
    
    std_method = STD_METHOD_FIXED
    st.session_state.shared_std_method = STD_METHOD_FIXED
    
    st.divider()
    
    # ========== 手順③：需要変動と計画誤差率を把握する ==========
    st.markdown("""
    <div class="step-middle-section">
        <p>手順③：需要変動と計画誤差率を把握する</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="step-description">リードタイム期間の実績合計と計画合計を比較し、実績のバラつき（実績−平均）と計画誤差率（実績−計画）を可視化します。<br>これらの差分を時系列グラフと統計情報で確認することで、安全在庫を設定する際の根拠となるデータの特性を把握できます。</div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # セッション状態の初期化
    if 'step2_lt_delta_calculated' not in st.session_state:
        st.session_state.step2_lt_delta_calculated = False
    if 'step2_lt_delta_data' not in st.session_state:
        st.session_state.step2_lt_delta_data = None
    if 'step2_lt_delta_calculator' not in st.session_state:
        st.session_state.step2_lt_delta_calculator = None
    if 'step2_lt_delta_product_code' not in st.session_state:
        st.session_state.step2_lt_delta_product_code = None
    if 'step2_lt_delta_total_count' not in st.session_state:
        st.session_state.step2_lt_delta_total_count = None
    
    # ボタン: LT間差分を計算・表示する
    if st.button("LT間差分を計算・表示する", type="primary", use_container_width=True, key="step2_lt_delta_button"):
        try:
            # データ取得
            if st.session_state.uploaded_data_loader is not None:
                current_data_loader = st.session_state.uploaded_data_loader
            else:
                current_data_loader = data_loader
            
            plan_data = current_data_loader.get_daily_plan(selected_product)
            actual_data = current_data_loader.get_daily_actual(selected_product)
            working_dates = current_data_loader.get_working_dates()
            
            # ABC区分を取得
            abc_category = get_product_category(selected_product)
            
            # リードタイム日数を計算（LT間差分計算用）
            # 一時的なcalculatorを作成してリードタイム日数を取得
            temp_calculator = SafetyStockCalculator(
                plan_data=plan_data,
                actual_data=actual_data,
                working_dates=working_dates,
                lead_time=lead_time,
                lead_time_type=lead_time_type,
                stockout_tolerance_pct=stockout_tolerance,
                std_calculation_method=std_method,
                data_loader=current_data_loader,
                product_code=selected_product,
                abc_category=abc_category,
                category_cap_days={}
            )
            lead_time_working_days = temp_calculator._get_lead_time_in_working_days()
            lead_time_days = int(np.ceil(lead_time_working_days))
            
            # LT間差分を計算
            actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
            delta2 = actual_sums - actual_sums.mean()
            plan_sums = plan_data.rolling(window=lead_time_days).sum().dropna()
            common_idx = actual_sums.index.intersection(plan_sums.index)
            delta3 = actual_sums.loc[common_idx] - plan_sums.loc[common_idx]
            
            # リードタイム区間の総件数を計算（稼働日ベース）
            # 全期間の日数 = LT間差分計算に使用している日次データの有効期間（稼働日のみ）
            total_days = len(actual_data)  # actual_dataは既に稼働日ベースに再サンプリング済み
            total_count = total_days - lead_time_days + 1
            
            # セッション状態に保存
            st.session_state.step2_lt_delta_calculated = True
            st.session_state.step2_lt_delta_data = {
                'delta2': delta2,
                'delta3': delta3,
                'plan_data': plan_data,
                'actual_data': actual_data,
                'working_dates': working_dates,
                'lead_time_days': lead_time_days
            }
            st.session_state.step2_lt_delta_calculator = temp_calculator
            st.session_state.step2_lt_delta_product_code = selected_product
            st.session_state.step2_lt_delta_total_count = total_count
            st.session_state.step2_lt_delta_plan_data = plan_data
            st.session_state.step2_lt_delta_actual_data = actual_data
            st.session_state.step2_lt_delta_working_dates = working_dates
            
            st.success("✅ LT間差分の計算が完了しました。")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ LT間差分の計算でエラーが発生しました: {str(e)}")
    
    # LT間差分の表示
    if st.session_state.get('step2_lt_delta_calculated', False) and st.session_state.get('step2_lt_delta_data') is not None:
        product_code = st.session_state.get('step2_lt_delta_product_code')
        lt_delta_data = st.session_state.get('step2_lt_delta_data')
        calculator = st.session_state.get('step2_lt_delta_calculator')
        total_count = st.session_state.get('step2_lt_delta_total_count')
        lead_time_days = lt_delta_data['lead_time_days']
        
        # 計画と実績の時系列推移グラフ
        st.markdown('<div class="step-sub-section">日次計画と日次実績の時系列推移</div>', unsafe_allow_html=True)
        fig = create_time_series_chart(product_code, calculator)
        st.plotly_chart(fig, use_container_width=True, key=f"time_series_step2_{product_code}")
        # 日次計画と日次実績の統計情報（グラフとの間隔を最小化するため、空行を削除）
        st.markdown('<div class="step-sub-section">日次計画と日次実績の統計情報</div>', unsafe_allow_html=True)
        display_plan_actual_statistics(product_code, calculator)
        
        # リードタイム区間の総件数の表示
        st.markdown('<div class="step-sub-section">リードタイム区間の総件数</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="annotation-success-box">
                <span class="icon">✅</span>
                <div class="text">
                    <strong>リードタイム区間の総件数：{total_count}件</strong><br>
                    リードタイム日数分の実績合計を1日ずつスライドしながら計算した「リードタイム区間」の総数です。　※ 総件数 ＝ 全期間の日数 − リードタイム ＋ 1
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # LT間差分の時系列推移グラフ（安全在庫ラインなし）
        st.markdown('<div class="step-sub-section">リードタイム間差分の時系列推移</div>', unsafe_allow_html=True)
        fig = create_time_series_delta_bar_chart(product_code, None, calculator, show_safety_stock_lines=False)
        st.plotly_chart(fig, use_container_width=True, key=f"delta_bar_step2_{product_code}")
        
        # リードタイム間差分の統計情報
        st.markdown('<div class="step-sub-section">リードタイム間差分の統計情報</div>', unsafe_allow_html=True)
        display_delta_statistics_from_data(product_code, lt_delta_data['delta2'], lt_delta_data['delta3'])
        
        st.divider()
    
    # ========== 手順④：安全在庫を算出する ==========
    if st.session_state.get('step2_lt_delta_calculated', False):
        st.markdown("""
        <div class="step-middle-section">
            <p>手順④：安全在庫を算出する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">リードタイム間差分の分布を分析し、3種類の安全在庫モデル（理論値・実測値（実績−平均）・実測値（実績−計画））を算出します。<br>ヒストグラムで分布の形状を確認し、各モデルの安全在庫ラインがどのように設定されるかを理解できます。</div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # セッション状態の初期化
        if 'step2_calculated' not in st.session_state:
            st.session_state.step2_calculated = False
        if 'step2_results' not in st.session_state:
            st.session_state.step2_results = None
        if 'step2_calculator' not in st.session_state:
            st.session_state.step2_calculator = None
        if 'step2_product_code' not in st.session_state:
            st.session_state.step2_product_code = None
        
        # ボタン: 安全在庫を算出する
        if st.button("安全在庫を算出する", type="primary", use_container_width=True, key="step2_calculate_button"):
            try:
                # データ取得（手順②で計算済みのデータを再利用）
                if st.session_state.get('step2_lt_delta_plan_data') is not None:
                    plan_data = st.session_state.step2_lt_delta_plan_data
                    actual_data = st.session_state.step2_lt_delta_actual_data
                    working_dates = st.session_state.step2_lt_delta_working_dates
                else:
                    # フォールバック：手順②のデータがない場合は新規取得
                    if st.session_state.uploaded_data_loader is not None:
                        current_data_loader = st.session_state.uploaded_data_loader
                    else:
                        current_data_loader = data_loader
                    plan_data = current_data_loader.get_daily_plan(selected_product)
                    actual_data = current_data_loader.get_daily_actual(selected_product)
                    working_dates = current_data_loader.get_working_dates()
                
                # ABC区分を取得
                abc_category = get_product_category(selected_product)
                
                # 安全在庫計算（ステップ3では上限カットを適用しない）
                calculator = SafetyStockCalculator(
                    plan_data=plan_data,
                    actual_data=actual_data,
                    working_dates=working_dates,
                    lead_time=lead_time,
                    lead_time_type=lead_time_type,
                    stockout_tolerance_pct=stockout_tolerance,
                    std_calculation_method=std_method,
                    data_loader=st.session_state.uploaded_data_loader if st.session_state.uploaded_data_loader is not None else data_loader,
                    product_code=selected_product,
                    abc_category=abc_category,
                    category_cap_days={}  # ステップ3では上限カットを適用しない（空の辞書）
                )
                
                results = calculator.calculate_all_models()
                
                # セッション状態に保存
                st.session_state.step2_calculated = True
                st.session_state.step2_results = results
                st.session_state.step2_calculator = calculator
                st.session_state.step2_product_code = selected_product
                st.session_state.step2_plan_data = plan_data
                st.session_state.step2_actual_data = actual_data
                st.session_state.step2_working_dates = working_dates
                
                st.success("✅ 安全在庫の算出が完了しました。")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 安全在庫の算出でエラーが発生しました: {str(e)}")
        
        # 算出結果の表示
        if st.session_state.get('step2_calculated', False) and st.session_state.get('step2_results') is not None:
            product_code = st.session_state.get('step2_product_code')
            results = st.session_state.get('step2_results')
            calculator = st.session_state.get('step2_calculator')
            
            # LT間差分の時系列推移グラフ（安全在庫ライン付きで再描画）
            # 手順③では別のキーを使用して、安全在庫ラインを追加したグラフを表示
            st.markdown('<div class="step-sub-section">リードタイム間差分の時系列推移</div>', unsafe_allow_html=True)
            fig = create_time_series_delta_bar_chart(product_code, results, calculator, show_safety_stock_lines=True)
            st.plotly_chart(fig, use_container_width=True, key=f"delta_bar_step3_{product_code}")
            
            # ヒストグラム
            st.markdown('<div class="step-sub-section">リードタイム間差分の分布（ヒストグラム）</div>', unsafe_allow_html=True)
            fig = create_histogram_with_unified_range(product_code, results, calculator)
            st.plotly_chart(fig, use_container_width=True, key=f"histogram_{product_code}")
            # 安全在庫算出メッセージを表示
            hist_data = calculator.get_histogram_data()
            series_avg_diff = hist_data['model2_delta']
            series_plan_diff = hist_data['model3_delta']
            shortage_rate = results['common_params']['stockout_tolerance_pct']
            is_p_zero = shortage_rate <= 0
            total_count = st.session_state.get('step2_lt_delta_total_count', max(len(series_avg_diff), len(series_plan_diff)))
            if is_p_zero:
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>安全在庫の設定：</strong>欠品許容率 p＝0 のため、安全在庫①（理論値）は計算不可（p＝0 → Z＝∞）。安全在庫②・③は差分の最大値を安全在庫として設定しています。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                k = max(1, int(np.ceil(shortage_rate / 100.0 * total_count)))
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>安全在庫の設定：</strong>安全在庫②と③は、全 {total_count} 件のうち {k} 件（{shortage_rate:.1f}%）だけ欠品を許容し、その水準を安全在庫ラインとして設定しています。</div>
                </div>
                """, unsafe_allow_html=True)
            
            # 安全在庫比較テーブル
            st.markdown('<div class="step-sub-section">安全在庫比較結果</div>', unsafe_allow_html=True)
            display_safety_stock_comparison(product_code, results, calculator)
            
            st.divider()
    
    # ========== 手順⑤：実績異常値処理を実施する ==========
    if st.session_state.get('step2_calculated', False):
        st.markdown("""
        <div class="step-middle-section">
            <p>手順⑤：実績異常値処理を実施する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">需要データに含まれる統計的な上振れ異常値を検出し、設定した上限値へ補正します。<br>スパイク（突発的に跳ね上がる異常な値）を抑えることで、安全在庫が過大に算定されるのを防ぎ、結果を安定させます。</div>
        """, unsafe_allow_html=True)
        
        # 実績異常値処理パラメータ設定
        st.markdown('<div class="step-sub-section">実績異常値処理パラメータ</div>', unsafe_allow_html=True)
        
        # グローバル異常基準と上位カット割合を横並びレイアウト
        col1, col2 = st.columns(2)
        
        with col1:
            sigma_k = st.number_input(
                "異常基準：mean + σ × (係数)",
                min_value=2.0,
                max_value=10.0,
                value=6.0,
                step=0.5,
                help="※ 平均からどれだけ離れた値を異常とみなすか？",
                key="step2_sigma_k"
            )
        
        with col2:
            top_limit_p = st.number_input(
                "上位カット割合（％）",
                min_value=1.0,
                max_value=5.0,
                value=2.0,
                step=0.1,
                help="※ 上位何％を補正対象とするか？",
                key="step2_top_limit_p"
            )
        
        # 割合（％）のみで制御する仕様に統一
        top_limit_mode = 'percent'
        top_limit_n = None
        
        # セッション状態の初期化
        if 'step2_outlier_processed' not in st.session_state:
            st.session_state.step2_outlier_processed = False
        if 'step2_outlier_handler' not in st.session_state:
            st.session_state.step2_outlier_handler = None
        if 'step2_imputed_data' not in st.session_state:
            st.session_state.step2_imputed_data = None
        
        # ボタン2: 実績異常値処理を実施する
        if st.button("実績異常値処理を実施する", type="primary", use_container_width=True, key="step2_outlier_button"):
            try:
                actual_data = st.session_state.get('step2_actual_data')
                working_dates = st.session_state.get('step2_working_dates')
                
                # ABC区分を取得
                selected_product = st.session_state.get('step2_product_code')
                abc_category = get_product_category(selected_product) if selected_product else None
                
                # 異常値処理
                outlier_handler = OutlierHandler(
                    actual_data=actual_data,
                    working_dates=working_dates,
                    sigma_k=sigma_k,
                    top_limit_mode='percent',
                    top_limit_n=2,
                    top_limit_p=top_limit_p,
                    abc_category=abc_category
                )
                
                processing_result = outlier_handler.detect_and_impute()
                
                # セッション状態に保存
                st.session_state.step2_outlier_processed = True
                st.session_state.step2_outlier_handler = outlier_handler
                st.session_state.step2_imputed_data = processing_result['imputed_data']
                
                processing_info = processing_result.get('processing_info', {})
                candidate_count = processing_info.get('candidate_count', 0)
                final_count = processing_info.get('final_count', 0)
                
                # セッション状態に処理情報を保存（メッセージ表示用）
                st.session_state.step2_processing_info = processing_info
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 異常値処理でエラーが発生しました: {str(e)}")
        
        # 異常値処理結果の表示（Before/After）
        if st.session_state.get('step2_outlier_processed', False) and st.session_state.get('step2_outlier_handler') is not None:
            # 処理情報を取得（セッション状態から、またはoutlier_handlerから）
            outlier_handler = st.session_state.get('step2_outlier_handler')
            processing_info = st.session_state.get('step2_processing_info', {})
            if not processing_info and outlier_handler:
                processing_info = outlier_handler.processing_info if hasattr(outlier_handler, 'processing_info') else {}
            
            is_skipped = processing_info.get('skipped', False)
            candidate_count = processing_info.get('candidate_count', 0)
            
            # メッセージを表示
            if is_skipped or candidate_count == 0:
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>結果：</strong>異常値は検出されませんでした。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>結果：</strong>異常値を検出し、補正処理を実施しました。</div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown('<div class="step-sub-section">異常値処理結果：実績データ Before/After 比較</div>', unsafe_allow_html=True)
            
            # 詳細情報を表示（異常値が検出された場合のみ）
            # display_outlier_processing_results内でグラフも表示されるため、ここでは直接表示しない
            product_code = st.session_state.get('step2_product_code')
            before_data = st.session_state.get('step2_actual_data')
            after_data = st.session_state.get('step2_imputed_data')
            outlier_handler = st.session_state.get('step2_outlier_handler')
            
            if not is_skipped and candidate_count > 0:
                display_outlier_processing_results(
                    product_code,
                    before_data,
                    after_data,
                    outlier_handler,
                    st.session_state.get('step2_results'),
                    st.session_state.get('step2_calculator'),
                    st.session_state.get('step2_after_results'),
                    st.session_state.get('step2_after_calculator'),
                    show_details=True
                )
            else:
                # 異常値が検出されなかった場合でも、グラフだけは表示する
                display_outlier_processing_results(
                    product_code,
                    before_data,
                    after_data,
                    outlier_handler,
                    st.session_state.get('step2_results'),
                    st.session_state.get('step2_calculator'),
                    st.session_state.get('step2_after_results'),
                    st.session_state.get('step2_after_calculator'),
                    show_details=False
                )
            
            st.divider()
    
    # ========== 手順⑥：実績異常値処理後の安全在庫を再算出して比較する ==========
    if st.session_state.get('step2_outlier_processed', False):
        st.markdown("""
        <div class="step-middle-section">
            <p>手順⑥：実績異常値処理後の安全在庫を再算出して比較する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">実績異常値補正が安全在庫の算定結果にどの程度影響するかを確認します。</div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # セッション状態の初期化
        if 'step2_recalculated' not in st.session_state:
            st.session_state.step2_recalculated = False
        if 'step2_after_results' not in st.session_state:
            st.session_state.step2_after_results = None
        if 'step2_after_calculator' not in st.session_state:
            st.session_state.step2_after_calculator = None
        
        # ボタン4: 異常値処理前後の安全在庫を再算出・比較する
        if st.button("安全在庫を再算出・比較する", type="primary", use_container_width=True, key="step2_recalculate_button"):
            try:
                plan_data = st.session_state.get('step2_plan_data')
                imputed_data = st.session_state.get('step2_imputed_data')
                working_dates = st.session_state.get('step2_working_dates')
                
                # ABC区分を取得
                selected_product = st.session_state.get('step2_product_code') or st.session_state.get('step2_selected_product')
                abc_category = get_product_category(selected_product) if selected_product else None
                
                # 補正後データで安全在庫再計算（ステップ4では上限カットを適用しない）
                # 異常値処理前のデータを取得（安全在庫②の平均計算用）
                original_actual_data = st.session_state.get('step2_actual_data')
                after_calculator = SafetyStockCalculator(
                    plan_data=plan_data,
                    actual_data=imputed_data,
                    working_dates=working_dates,
                    lead_time=lead_time,
                    lead_time_type=lead_time_type,
                    stockout_tolerance_pct=stockout_tolerance,
                    std_calculation_method=std_method,
                    data_loader=st.session_state.uploaded_data_loader if st.session_state.uploaded_data_loader is not None else data_loader,
                    product_code=st.session_state.step2_product_code,
                    abc_category=abc_category,
                    category_cap_days={},  # ステップ4では上限カットを適用しない（空の辞書）
                    original_actual_data=original_actual_data  # 異常値処理前のデータ（安全在庫②の平均計算用）
                )
                
                after_results = after_calculator.calculate_all_models()
                
                # セッション状態に保存
                st.session_state.step2_recalculated = True
                st.session_state.step2_after_results = after_results
                st.session_state.step2_after_calculator = after_calculator
                
                st.success("✅ 異常値処理前後の安全在庫の比較・再算出が完了しました。")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 異常値処理前後の安全在庫の比較・再算出でエラーが発生しました: {str(e)}")
        
        # 再算出結果の表示（Before/After比較）
        if st.session_state.get('step2_recalculated', False) and st.session_state.get('step2_after_results') is not None:
            st.markdown('<div class="step-sub-section">異常値処理結果：安全在庫①②③ Before / After 比較</div>', unsafe_allow_html=True)
            
            product_code = st.session_state.get('step2_product_code')
            before_results = st.session_state.get('step2_results')
            after_results = st.session_state.get('step2_after_results')
            before_calculator = st.session_state.get('step2_calculator')
            after_calculator = st.session_state.get('step2_after_calculator')
            
            # 比較テーブル + 現行比表示（グラフも含む）
            display_after_processing_comparison(
                product_code,
                before_results,
                after_results,
                before_calculator,
                after_calculator
            )
            
            # LT間差分の分布（Before/After）
            st.markdown('<div class="step-sub-section">異常値処理結果：リードタイム間差分の分布（ヒストグラム）Before/After 比較</div>', unsafe_allow_html=True)
            lead_time_days = int(np.ceil(before_results['common_params']['lead_time_days']))
            stockout_tolerance_pct = before_results['common_params']['stockout_tolerance_pct']
            before_data = st.session_state.get('step2_actual_data')
            after_data = st.session_state.get('step2_imputed_data')
            before_sums = before_data.rolling(window=lead_time_days).sum().dropna()
            before_delta2 = before_sums - before_sums.mean()
            before_delta3 = before_sums - before_calculator.plan_data.rolling(window=lead_time_days).sum().dropna().loc[before_sums.index]
            after_sums = after_data.rolling(window=lead_time_days).sum().dropna()
            after_delta2 = after_sums - after_sums.mean()
            after_delta3 = after_sums - before_calculator.plan_data.rolling(window=lead_time_days).sum().dropna().loc[after_sums.index]
            before_ss1 = before_results['model1_theoretical']['safety_stock']
            before_ss2 = before_results['model2_empirical_actual']['safety_stock']
            before_ss3 = before_results['model3_empirical_plan']['safety_stock']
            if after_results is not None:
                after_ss1 = after_results['model1_theoretical']['safety_stock']
                after_ss2 = after_results['model2_empirical_actual']['safety_stock']
                after_ss3 = after_results['model3_empirical_plan']['safety_stock']
            else:
                after_ss1 = before_ss1
                after_delta2_positive = after_delta2[after_delta2 > 0]
                after_delta3_positive = after_delta3[after_delta3 > 0]
                N_pos2 = len(after_delta2_positive)
                N_pos3 = len(after_delta3_positive)
                if N_pos2 == 0:
                    after_ss2 = 0.0
                elif stockout_tolerance_pct <= 0:
                    if len(after_delta2_positive) > 0:
                        after_ss2 = after_delta2_positive.max()
                    else:
                        after_ss2 = 0.0
                else:
                    q = 1 - stockout_tolerance_pct / 100.0
                    k = max(1, int(np.ceil(q * N_pos2)))
                    after_delta2_positive_sorted = np.sort(after_delta2_positive.values)
                    after_ss2 = after_delta2_positive_sorted[k - 1]
                if N_pos3 == 0:
                    after_ss3 = 0.0
                elif stockout_tolerance_pct <= 0:
                    if len(after_delta3_positive) > 0:
                        after_ss3 = after_delta3_positive.max()
                    else:
                        after_ss3 = 0.0
                else:
                    q = 1 - stockout_tolerance_pct / 100.0
                    k = max(1, int(np.ceil(q * N_pos3)))
                    after_delta3_positive_sorted = np.sort(after_delta3_positive.values)
                    after_ss3 = after_delta3_positive_sorted[k - 1]
            is_before_ss1_undefined = before_results['model1_theoretical'].get('is_undefined', False) or before_ss1 is None
            is_p_zero = stockout_tolerance_pct <= 0
            if after_results is not None:
                is_after_ss1_undefined = after_results['model1_theoretical'].get('is_undefined', False) or after_ss1 is None
            else:
                is_after_ss1_undefined = is_before_ss1_undefined
            fig = create_outlier_lt_delta_comparison_chart(
                product_code,
                before_delta2,
                before_delta3,
                after_delta2,
                after_delta3,
                before_ss1,
                before_ss2,
                before_ss3,
                after_ss1,
                after_ss2,
                after_ss3,
                is_p_zero,
                is_before_ss1_undefined,
                is_after_ss1_undefined
            )
            st.plotly_chart(fig, use_container_width=True, key=f"delta_distribution_{product_code}")
            
            # 異常値処理後の安全在庫設定の説明注釈
            total_count_after = len(after_delta2)  # または len(after_delta3)、どちらでも同じ
            if is_p_zero:
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>安全在庫の設定：</strong>欠品許容率 p＝0 のため、安全在庫①（理論値）は計算不可（p＝0 → Z＝∞）。安全在庫②・③は差分の最大値を安全在庫として設定しています。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                k_after = max(1, int(np.ceil(stockout_tolerance_pct / 100.0 * total_count_after)))
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>安全在庫の設定：</strong>安全在庫②と③は、全 {total_count_after} 件のうち {k_after} 件（{stockout_tolerance_pct:.1f}%）だけ欠品を許容し、その水準を安全在庫ラインとして設定しています。</div>
                </div>
                """, unsafe_allow_html=True)
            
            st.divider()
        else:
            # ボタン押下前は軽いメッセージのみ表示
            st.info("💡 「安全在庫を再算出・比較する」ボタンを押すと、LT間差分の分布グラフが表示されます。")
    
    # ========== 手順⑦：上限カットを適用する ==========
    if st.session_state.get('step2_recalculated', False) and st.session_state.get('step2_after_results') is not None:
        st.markdown("""
        <div class="step-middle-section">
            <p>手順⑦：上限カットを適用する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">異常値処理後の安全在庫が過大にならないよう、区分別の上限日数で安全在庫を調整します。<br>上限日数は区分ごとに設定でき、0を入力すると上限なしとなります。</div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # セッション状態の初期化
        # analysis_resultから実際に存在する全ての区分を取得（「未分類」も含む）
        from utils.common import format_abc_category_for_display
        all_categories_in_data = analysis_result['abc_category'].apply(format_abc_category_for_display).unique().tolist()
        abc_categories_for_cap = sorted([cat for cat in all_categories_in_data if str(cat).strip() != ""])
        
        if not abc_categories_for_cap:
            abc_categories_for_cap = ['A', 'B', 'C']
        
        if 'category_cap_days' not in st.session_state:
            st.session_state.category_cap_days = {cat: 40 for cat in abc_categories_for_cap}
        
        # 新しい区分が追加された場合、デフォルト値を設定
        for cat in abc_categories_for_cap:
            if cat not in st.session_state.category_cap_days:
                st.session_state.category_cap_days[cat] = 40
        
        col1, col2, col3 = st.columns(3)
        cols = [col1, col2, col3]
        
        for i, cat in enumerate(abc_categories_for_cap):
            with cols[i % 3]:
                current_value = st.session_state.category_cap_days.get(cat, 40)
                # Noneの場合は40をデフォルト値として使用
                default_value = int(current_value) if current_value is not None else 40
                cap_days_input = st.number_input(
                    f"{cat}区分の上限日数（日）",
                    min_value=0,
                    max_value=365,
                    value=default_value,
                    step=1,
                    help="異常値処理後でも必要以上に安全在庫が膨らまないよう、区分別の上限日数でカットします。デフォルトは全区分40日（2か月）です。0を入力すると上限なし（カットしない）になります。",
                    key=f"step2_category_cap_days_{cat}"
                )
                # 0の場合はNone（上限なし）として扱う
                if cap_days_input == 0:
                    st.session_state.category_cap_days[cat] = None
                else:
                    st.session_state.category_cap_days[cat] = cap_days_input
        
        # セッション状態の初期化
        if 'step2_final_results' not in st.session_state:
            st.session_state.step2_final_results = None
        if 'step2_final_calculator' not in st.session_state:
            st.session_state.step2_final_calculator = None
        
        # ボタン5: 上限カットを適用する
        if st.button("上限カットを適用する", type="primary", use_container_width=True, key="step2_apply_cap_button"):
            try:
                plan_data = st.session_state.get('step2_plan_data')
                imputed_data = st.session_state.get('step2_imputed_data')
                working_dates = st.session_state.get('step2_working_dates')
                
                # ABC区分を取得
                selected_product = st.session_state.get('step2_product_code')
                abc_category = get_product_category(selected_product) if selected_product else None
                
                # 上限カットを適用して安全在庫を再計算
                category_cap_days = st.session_state.get('category_cap_days', {})
                # 異常値処理前のデータを取得（安全在庫②の平均計算用）
                original_actual_data = st.session_state.get('step2_actual_data')
                final_calculator = SafetyStockCalculator(
                    plan_data=plan_data,
                    actual_data=imputed_data,
                    working_dates=working_dates,
                    lead_time=lead_time,
                    lead_time_type=lead_time_type,
                    stockout_tolerance_pct=stockout_tolerance,
                    std_calculation_method=std_method,
                    data_loader=st.session_state.uploaded_data_loader if st.session_state.uploaded_data_loader is not None else data_loader,
                    product_code=st.session_state.step2_product_code,
                    abc_category=abc_category,
                    category_cap_days=category_cap_days,  # ステップ5で上限カットを適用
                    original_actual_data=original_actual_data  # 異常値処理前のデータ（安全在庫②の平均計算用）
                )
                
                final_results = final_calculator.calculate_all_models()
                
                # セッション状態に保存
                st.session_state.step2_final_results = final_results
                st.session_state.step2_final_calculator = final_calculator
                
                st.success("✅ 上限カット適用後の最終的な安全在庫の算出が完了しました。")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 上限カット適用後の安全在庫の算出でエラーが発生しました: {str(e)}")
        
        # 最終結果の表示（上限カット適用後）
        if st.session_state.get('step2_final_results') is not None and st.session_state.get('step2_final_calculator') is not None:
            final_results = st.session_state.get('step2_final_results')
            final_calculator = st.session_state.get('step2_final_calculator')
            
            # 上限カットが実際に適用されたかどうかを確認
            category_limit_applied = False
            if final_calculator and final_calculator.abc_category:
                model1_applied = final_results['model1_theoretical'].get('category_limit_applied', False)
                model2_applied = final_results['model2_empirical_actual'].get('category_limit_applied', False)
                model3_applied = final_results['model3_empirical_plan'].get('category_limit_applied', False)
                category_limit_applied = model1_applied or model2_applied or model3_applied
            
            if category_limit_applied:
                # 上限カットが適用された場合
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>上限カットの適用：</strong>上限カットは適用されました。</div>
                </div>
                """, unsafe_allow_html=True)
                product_code = st.session_state.get('step2_product_code')
                
                # 上限カット適用前後の安全在庫比較テーブル
                display_after_cap_comparison(
                    product_code,
                    st.session_state.get('step2_after_results'),
                    final_results,
                    st.session_state.get('step2_after_calculator'),
                    final_calculator,
                    cap_applied=True  # 上限カットが適用されたことを示すフラグ
                )
            else:
                # 上限カットが適用されていない場合でも比較結果を表示
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>上限カットの適用：</strong>上限カットは適用されませんでした。</div>
                </div>
                """, unsafe_allow_html=True)
                product_code = st.session_state.get('step2_product_code')
                
                # 上限カット適用前後の安全在庫比較テーブル（上限カットが適用されなかった場合でも表示）
                display_after_cap_comparison(
                    product_code,
                    st.session_state.get('step2_after_results'),
                    final_results,
                    st.session_state.get('step2_after_calculator'),
                    final_calculator,
                    cap_applied=False  # 上限カットが適用されなかったことを示すフラグ
                )
            
            st.divider()
    
    # ========== 手順⑧：計画異常値処理を実施し、安全在庫を確定する ==========
    if st.session_state.get('step2_final_results') is not None and st.session_state.get('step2_final_calculator') is not None:
        st.markdown("""
        <div class="step-middle-section">
            <p>手順⑧：計画異常値処理を実施し、安全在庫を確定する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">計画誤差率を計算し、計画異常値処理の判定結果に基づいて、安全在庫として採用するモデル（②または③）を最終決定します。<br>計画誤差率が大きい場合は安全在庫②を、許容範囲内の場合は安全在庫③を採用します。</div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 計画誤差率の閾値設定（手順1の値を継承、必要に応じて変更可能）
        st.markdown('<div class="step-sub-section">計画異常値処理の閾値設定</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            plan_plus_threshold_final = st.number_input(
                "計画誤差率（プラス）の閾値（%）",
                min_value=0.0,
                max_value=500.0,
                value=st.session_state.get("step2_plan_plus_threshold", 50.0),
                step=5.0,
                help="計画誤差率がこの値以上の場合、安全在庫②を採用します。",
                key="step2_plan_plus_threshold_final"
            )
        with col2:
            plan_minus_threshold_final = st.number_input(
                "計画誤差率（マイナス）の閾値（%）",
                min_value=-500.0,
                max_value=0.0,
                value=st.session_state.get("step2_plan_minus_threshold", -50.0),
                step=5.0,
                help="計画誤差率がこの値以下の場合、安全在庫②を採用します。",
                key="step2_plan_minus_threshold_final"
            )
        
        # 計画誤差率を計算
        product_code = st.session_state.get('step2_product_code')
        plan_data = st.session_state.get('step2_plan_data')
        actual_data = st.session_state.get('step2_actual_data')
        
        if plan_data is not None and actual_data is not None:
            plan_error_rate, plan_error, plan_total = calculate_plan_error_rate(actual_data, plan_data)
            is_anomaly, anomaly_reason = is_plan_anomaly(
                plan_error_rate,
                plan_plus_threshold_final,
                plan_minus_threshold_final
            )
            
            # 判定結果の表示
            st.markdown('<div class="step-sub-section">計画異常値処理の判定結果</div>', unsafe_allow_html=True)
            
            final_results = st.session_state.get('step2_final_results')
            final_calculator = st.session_state.get('step2_final_calculator')
            
            if plan_error_rate is None:
                # 計画誤差率計算不可の場合
                st.markdown("""
                <div class="annotation-warning-box">
                    <span class="icon">⚠</span>
                    <div class="text"><strong>計画誤差率計算不可：</strong>計画合計が0のため、計画誤差率を計算できません。安全在庫②または③を手動で選択してください。</div>
                </div>
                """, unsafe_allow_html=True)
                
                # 手動選択UI
                selected_model = st.radio(
                    "採用する安全在庫モデル",
                    options=["安全在庫②", "安全在庫③"],
                    help="計画誤差率が計算できないため、手動で選択してください。",
                    key="step2_manual_model_selection"
                )
                
                if selected_model == "安全在庫②":
                    final_safety_stock = final_results['model2_empirical_actual']['safety_stock']
                    final_model_name = "安全在庫②"
                else:
                    final_safety_stock = final_results['model3_empirical_plan']['safety_stock']
                    final_model_name = "安全在庫③"
            else:
                # 計画誤差率が計算可能な場合
                if is_anomaly:
                    # 異常の場合
                    st.markdown(f"""
                    <div class="annotation-warning-box">
                        <span class="icon">⚠</span>
                        <div class="text"><strong>計画異常値処理：</strong>{anomaly_reason}。安全在庫②を採用して確定します。</div>
                    </div>
                    """, unsafe_allow_html=True)
                    final_safety_stock = final_results['model2_empirical_actual']['safety_stock']
                    final_model_name = "安全在庫②"
                else:
                    # 正常の場合
                    st.markdown(f"""
                    <div class="annotation-success-box">
                        <span class="icon">✅</span>
                        <div class="text"><strong>計画異常値処理：</strong>{anomaly_reason}。安全在庫③を採用して確定しますか？</div>
                    </div>
                    """, unsafe_allow_html=True)
                    final_safety_stock = final_results['model3_empirical_plan']['safety_stock']
                    final_model_name = "安全在庫③"
            
            # 計画誤差率情報の表示
            st.markdown('<div class="step-sub-section">計画誤差率情報</div>', unsafe_allow_html=True)
            plan_info_data = {
                '項目': ['計画誤差率', '計画誤差率（実績合計 - 計画合計）', '実績合計', '計画合計'],
                '値': [
                    f"{plan_error_rate:.2f}%" if plan_error_rate is not None else "計算不可",
                    f"{plan_error:,.2f}",
                    f"{actual_data.sum():,.2f}",
                    f"{plan_total:,.2f}" if plan_total > 0 else "0.00"
                ]
            }
            plan_info_df = pd.DataFrame(plan_info_data)
            st.dataframe(plan_info_df, use_container_width=True, hide_index=True)
            
            # 最終安全在庫の表示
            daily_actual_mean = final_calculator.actual_data.mean()
            final_safety_stock_days = final_safety_stock / daily_actual_mean if daily_actual_mean > 0 else 0
            
            st.markdown('<div class="step-sub-section">確定する安全在庫</div>', unsafe_allow_html=True)
            final_safety_stock_data = {
                '項目': ['採用モデル', '安全在庫数量', '安全在庫日数'],
                '値': [
                    final_model_name,
                    f"{final_safety_stock:.2f}",
                    f"{final_safety_stock_days:.1f}日"
                ]
            }
            final_safety_stock_df = pd.DataFrame(final_safety_stock_data)
            st.dataframe(final_safety_stock_df, use_container_width=True, hide_index=True)
            
            # 確定ボタン
            if st.button("安全在庫を確定する", type="primary", use_container_width=True, key="step2_finalize_safety_stock"):
                st.session_state.step2_finalized_safety_stock = {
                    'product_code': product_code,
                    'model': final_model_name,
                    'safety_stock': final_safety_stock,
                    'safety_stock_days': final_safety_stock_days,
                    'plan_error_rate': plan_error_rate,
                    'plan_error': plan_error,
                    'actual_total': actual_data.sum(),
                    'plan_total': plan_total,
                    'is_plan_anomaly': is_anomaly if plan_error_rate is not None else None
                }
                st.success(f"✅ 安全在庫を確定しました。採用モデル：{final_model_name}（{final_safety_stock:.2f}、{final_safety_stock_days:.1f}日）")
                st.rerun()
            
            # 確定済みの場合の表示
            if 'step2_finalized_safety_stock' in st.session_state:
                finalized = st.session_state.step2_finalized_safety_stock
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>確定済み：</strong>安全在庫は確定済みです。採用モデル：{model}（{qty:.2f}、{days:.1f}日）</div>
                </div>
                """.format(
                    model=finalized['model'],
                    qty=finalized['safety_stock'],
                    days=finalized['safety_stock_days']
                ), unsafe_allow_html=True)


# ========================================
# STEP2専用のUIヘルパー関数
# ========================================

def display_plan_actual_statistics(product_code: str, calculator: SafetyStockCalculator):
    """計画と実績の統計情報テーブルを表示"""
    
    # データ取得
    plan_data = calculator.plan_data
    actual_data = calculator.actual_data
    
    # 計画（単体）の統計情報（6項目に統一）
    plan_stats = {
        '項目': '日次計画',
        '件数': len(plan_data),
        '平均': np.mean(plan_data),
        '標準偏差': np.std(plan_data),
        '最小値': np.min(plan_data),
        '中央値': np.median(plan_data),
        '最大値': np.max(plan_data)
    }
    
    # 実績（単体）の統計情報（6項目に統一）
    actual_stats = {
        '項目': '日次実績',
        '件数': len(actual_data),
        '平均': np.mean(actual_data),
        '標準偏差': np.std(actual_data),
        '最小値': np.min(actual_data),
        '中央値': np.median(actual_data),
        '最大値': np.max(actual_data)
    }
    
    # データフレーム作成（計画→実績の順）
    stats_df = pd.DataFrame([plan_stats, actual_stats])
    
    # 数値を丸める
    numeric_columns = ['平均', '標準偏差', '最小値', '中央値', '最大値']
    for col in numeric_columns:
        stats_df[col] = stats_df[col].round(2)
    
    # グラフ直下に配置するためのスタイル適用
    st.markdown('<div class="statistics-table-container">', unsafe_allow_html=True)
    st.dataframe(stats_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def display_delta_statistics_from_data(product_code: str, delta2: pd.Series, delta3: pd.Series):
    """LT間差分の統計情報テーブルを表示（データから直接）"""
    
    # LT間差分（実績−平均）の統計情報（6項目に統一）
    model2_stats = {
        '項目': 'リードタイム間差分（実績 − 平均）※実績バラつき',
        '件数': len(delta2),
        '平均': np.mean(delta2),
        '標準偏差': np.std(delta2),
        '最小値': np.min(delta2),
        '中央値': np.median(delta2),
        '最大値': np.max(delta2)
    }
    
    # LT間差分（実績−計画）の統計情報（6項目に統一）
    model3_stats = {
        '項目': 'リードタイム間差分（実績 − 計画）※計画誤差率',
        '件数': len(delta3),
        '平均': np.mean(delta3),
        '標準偏差': np.std(delta3),
        '最小値': np.min(delta3),
        '中央値': np.median(delta3),
        '最大値': np.max(delta3)
    }
    
    # データフレーム作成
    stats_df = pd.DataFrame([model2_stats, model3_stats])
    
    # 数値を丸める
    numeric_columns = ['平均', '標準偏差', '最小値', '中央値', '最大値']
    for col in numeric_columns:
        stats_df[col] = stats_df[col].round(2)
    
    # グラフ直下に配置するためのスタイル適用
    st.markdown('<div class="statistics-table-container">', unsafe_allow_html=True)
    st.dataframe(stats_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def display_delta_statistics(product_code: str, calculator: SafetyStockCalculator):
    """LT間差分の統計情報テーブルを表示"""
    
    # データ取得
    hist_data = calculator.get_histogram_data()
    
    # LT間差分（実績−平均）の統計情報（6項目に統一）
    model2_stats = {
        '項目': 'リードタイム間差分（実績 − 平均）※実績バラつき',
        '件数': len(hist_data['model2_delta']),
        '平均': np.mean(hist_data['model2_delta']),
        '標準偏差': np.std(hist_data['model2_delta']),
        '最小値': np.min(hist_data['model2_delta']),
        '中央値': np.median(hist_data['model2_delta']),
        '最大値': np.max(hist_data['model2_delta'])
    }
    
    # LT間差分（実績−計画）の統計情報（6項目に統一）
    model3_stats = {
        '項目': 'リードタイム間差分（実績 − 計画）※計画誤差率',
        '件数': len(hist_data['model3_delta']),
        '平均': np.mean(hist_data['model3_delta']),
        '標準偏差': np.std(hist_data['model3_delta']),
        '最小値': np.min(hist_data['model3_delta']),
        '中央値': np.median(hist_data['model3_delta']),
        '最大値': np.max(hist_data['model3_delta'])
    }
    
    # データフレーム作成
    stats_df = pd.DataFrame([model2_stats, model3_stats])
    
    # 数値を丸める
    numeric_columns = ['平均', '標準偏差', '最小値', '中央値', '最大値']
    for col in numeric_columns:
        stats_df[col] = stats_df[col].round(2)
    
    # グラフ直下に配置するためのスタイル適用
    st.markdown('<div class="statistics-table-container">', unsafe_allow_html=True)
    st.dataframe(stats_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def display_safety_stock_comparison(product_code: str, results: dict, calculator: SafetyStockCalculator):
    """安全在庫比較結果を表示"""
    
    # 安全在庫値を取得
    theoretical_value = results['model1_theoretical']['safety_stock']
    is_model1_undefined = results['model1_theoretical'].get('is_undefined', False) or theoretical_value is None
    empirical_actual_value = results['model2_empirical_actual']['safety_stock']
    empirical_plan_value = results['model3_empirical_plan']['safety_stock']
    current_value = results['current_safety_stock']['safety_stock']
    current_days = results['current_safety_stock']['safety_stock_days']
    
    # 日当たり実績平均を計算
    daily_actual_mean = calculator.actual_data.mean()
    
    # 在庫日数を計算（①が計算不可の場合は0）
    theoretical_days = theoretical_value / daily_actual_mean if (daily_actual_mean > 0 and not is_model1_undefined and theoretical_value is not None) else 0
    empirical_actual_days = empirical_actual_value / daily_actual_mean if daily_actual_mean > 0 else 0
    empirical_plan_days = empirical_plan_value / daily_actual_mean if daily_actual_mean > 0 else 0
    
    # 比較データを作成（列名変更と欠品許容率とZの対応表示）
    stockout_tolerance_pct = results['common_params']['stockout_tolerance_pct']
    safety_factor = results['common_params']['safety_factor']
    is_p_zero = stockout_tolerance_pct <= 0
    
    # ①の値を判定
    if is_model1_undefined or is_p_zero:
        theoretical_display = "計算不可（p=0→Z=∞）"
        theoretical_ratio = "—"
        z_display = "計算不可（p=0→Z=∞）"
    else:
        theoretical_display = f"{theoretical_value:.2f}（{theoretical_days:.1f}日）"
        theoretical_ratio = f"{theoretical_value / current_value:.2f}" if current_value > 0 else "—"
        z_display = f"{stockout_tolerance_pct:.1f}% → Z={safety_factor:.3f}"
    
    comparison_data = {
        'モデル': [
            '安全在庫①：理論値',
            '安全在庫②：実測値（実績−平均）',
            '安全在庫③：実測値（実績−計画）',
            '現行設定'
        ],
        '安全在庫数量（日数）': [
            theoretical_display,
            f"{empirical_actual_value:.2f}（{empirical_actual_days:.1f}日）",
            f"{empirical_plan_value:.2f}（{empirical_plan_days:.1f}日）",
            f"{current_value:.2f}（{current_days:.1f}日）"
        ],
        '現行比': [
            theoretical_ratio,
            f"{empirical_actual_value / current_value:.2f}" if current_value > 0 else "—",
            f"{empirical_plan_value / current_value:.2f}" if current_value > 0 else "—",
            "1.00"
        ]
    }
    
    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)
    
    # 算出条件テーブルを追加（折りたたみ式、初期状態は閉じる）
    # このブロックと上部のテーブルを一体的に見せたいので、間に余計なスペースは入れない
    with st.expander("安全在庫算出条件", expanded=False):
        # 必要な値を取得
        lead_time_working_days = results['common_params']['lead_time_working_days']
        current_safety_stock_info = results['current_safety_stock']
        monthly_stock = current_safety_stock_info.get('monthly_stock', 0.0)
        avg_working_days_per_month = current_safety_stock_info.get('avg_working_days_per_month', 0.0)
        
        # 算出条件データを作成
        calculation_conditions_data = {
            '項目名': [
                '日当たり実績',
                'リードタイム（稼働日）',
                '欠品許容率 p',
                'z（片側）＝Φ⁻¹(1−p)【安全在庫①のみ適用】',
                '月平均稼働日数（稼働日マスタに基づく）',
                '現行の安全在庫登録値（月数）'
            ],
            '値': [
                f"{daily_actual_mean:.2f}",
                f"{lead_time_working_days:.1f}日",
                f"{stockout_tolerance_pct:.1f}%",
                f"{safety_factor:.3f}" if safety_factor is not None else "計算不可（p=0→Z=∞）",
                f"{avg_working_days_per_month:.1f}日",
                f"{monthly_stock:.2f}ヶ月"
            ],
            '備考': [
                '実データから算出（動的）',
                'ユーザー設定値',
                'ユーザー設定値',
                'p に基づき自動算出',
                '分析対象期間の平均稼働日',
                'STEP1で取り込んだ現行安全在庫データ'
            ]
        }
        
        calculation_conditions_df = pd.DataFrame(calculation_conditions_data)
        st.dataframe(calculation_conditions_df, use_container_width=True, hide_index=True)
    
    # 区分別上限適用情報を表示（実際に上限カットが適用された場合のみ表示）
    if calculator.abc_category:
        # 実際に上限カットが適用されたかどうかを確認
        # モデル結果にcategory_limit_appliedフラグがあるか、または実際に上限が適用されているかをチェック
        model1_applied = results['model1_theoretical'].get('category_limit_applied', False)
        model2_applied = results['model2_empirical_actual'].get('category_limit_applied', False)
        model3_applied = results['model3_empirical_plan'].get('category_limit_applied', False)
        
        if model1_applied or model2_applied or model3_applied:
            # 実際に上限カットが適用された場合のみ表示
            cap_days = calculator.category_cap_days.get(calculator.abc_category.upper())
            if cap_days is not None:
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>区分別上限適用：</strong>{product_code}は、上限{cap_days}日を適用しました。</div>
                </div>
                """, unsafe_allow_html=True)
        # 上限カットが適用されていない場合は何も表示しない
    
    # 在庫削減効果メッセージを追加
    recommended_ratio = empirical_plan_value / current_value if current_value > 0 else 0
    reduction_rate = (1 - recommended_ratio) * 100
    st.markdown(f"""
    <div class="annotation-success-box">
        <span class="icon">✅</span>
        <div class="text"><strong>在庫削減効果：</strong>推奨モデルは現行比 {recommended_ratio:.2f} で、約 {reduction_rate:.1f}% の在庫削減が期待できます。</div>
    </div>
    """, unsafe_allow_html=True)


def display_outlier_processing_results(product_code: str,
                                        before_data: pd.Series,
                                        after_data: pd.Series,
                                        outlier_handler: 'OutlierHandler',
                                        before_results: dict,
                                        before_calculator: SafetyStockCalculator,
                                        after_results: dict = None,
                                        after_calculator: SafetyStockCalculator = None,
                                        show_details: bool = True):
    """異常値処理結果を表示（Before/After比較）"""
    
    # Before/After実績線グラフ（重ね描き）を先に表示（小項目は呼び出し側で設定済み）
    # 異常値のインデックスを取得
    outlier_indices = outlier_handler.outlier_final_indices if hasattr(outlier_handler, 'outlier_final_indices') else []
    
    # chartsモジュールからグラフを生成
    fig = create_outlier_processing_results_chart(product_code, before_data, after_data, outlier_indices)
    st.plotly_chart(fig, use_container_width=True, key=f"outlier_detail_{product_code}")
    
    # 異常値処理の詳細情報を表示（グラフの後に表示）
    # show_detailsがFalseの場合は表示しない
    if not show_details:
        return
    
    processing_info = outlier_handler.processing_info
    if processing_info and not processing_info.get('skipped', False):
        # 異常値処理の詳細情報を折りたたみ式で表示（初期状態は閉じる）
        # このブロックと上部のグラフを一体的に見せたいので、間に余計なスペースは入れない
        with st.expander("異常値処理結果の見方（詳細情報）", expanded=False):
            # ユーザー指定パラメータを取得（セッション状態から）
            sigma_coef = st.session_state.get('step2_sigma_k', processing_info.get('sigma_k', 6.0))
            top_cut_ratio = st.session_state.get('step2_top_limit_p', processing_info.get('top_limit_p', 2.0))
            top_limit_value = top_cut_ratio
            
            info_data = []
            candidate_count = processing_info.get('candidate_count', 0)
            if candidate_count > 0:
                final_count = processing_info.get('final_count', 0)
                threshold_global = processing_info.get('threshold_global')
                threshold_final = processing_info.get('threshold_final')
                
                # 異常値の見つけ方
                info_data.append([
                    '異常値の見つけ方',
                    f'mean + σ × {sigma_coef:.2f}',
                    f'ユーザー指定のσ係数（例：{sigma_coef:.2f}）に基づき、平均から許容範囲を外れる上振れ値を異常候補として抽出'
                ])
                
                # 怪しい値（候補）
                info_data.append([
                    '怪しい値（候補）',
                    f'{candidate_count}件',
                    f'基準値(mean + {sigma_coef:.0f}σ)を超過した件数'
                ])
                
                # 最終的に直した件数
                info_data.append([
                    '最終的に直した件数',
                    f'{final_count}件',
                    f'上位カット割合（例：{top_cut_ratio:.2f}%）の範囲へ収まるように補正対象を確定した件数'
                ])
                
                # 異常とみなす基準（初期）
                info_data.append([
                    '異常とみなす基準（初期）',
                    f'{threshold_global:.2f}' if threshold_global else '—',
                    f'σ係数({sigma_coef:.2f})を反映した初期しきい値 (threshold_global)'
                ])
                
                # 異常とみなす基準（最終）
                info_data.append([
                    '異常とみなす基準（最終）',
                    f'{threshold_final:.2f}' if threshold_final else '—',
                    f'上位カット割合({top_cut_ratio:.2f}%)を適用し、最終的に採用された補正しきい値(threshold_final)'
                ])
                
                # 補正する上限割合
                info_data.append([
                    '補正する上限割合',
                    f'{top_cut_ratio:.2f}%',
                    f'上位{top_cut_ratio:.2f}%のみを補正対象とし、極端値による安全在庫の過大化を防止'
                ])
            
            if info_data:
                info_df = pd.DataFrame(info_data, columns=['項目', '値', '備考'])
                
                # CSSで列幅を調整（st.dataframe用）
                st.markdown("""
                <style>
                /* 異常値処理詳細情報テーブルの列幅調整 */
                div[data-testid="stDataFrame"] table,
                div[data-testid="stDataFrame"] .dataframe {
                    table-layout: fixed !important;
                    width: 100% !important;
                    border-collapse: collapse !important;
                }
                /* 項目列 */
                div[data-testid="stDataFrame"] th:nth-child(1),
                div[data-testid="stDataFrame"] td:nth-child(1) {
                    width: 20% !important;
                    min-width: 120px !important;
                    padding: 8px 12px !important;
                }
                /* 値列 */
                div[data-testid="stDataFrame"] th:nth-child(2),
                div[data-testid="stDataFrame"] td:nth-child(2) {
                    width: 15% !important;
                    min-width: 100px !important;
                    padding: 8px 12px !important;
                }
                /* 備考列 */
                div[data-testid="stDataFrame"] th:nth-child(3),
                div[data-testid="stDataFrame"] td:nth-child(3) {
                    width: 65% !important;
                    white-space: normal !important;
                    word-wrap: break-word !important;
                    overflow-wrap: break-word !important;
                    padding: 8px 12px !important;
                }
                /* テーブル全体のスタイル */
                div[data-testid="stDataFrame"] {
                    overflow-x: auto !important;
                }
                </style>
                """, unsafe_allow_html=True)
                
                st.dataframe(info_df, use_container_width=True, hide_index=True)


def display_outlier_lt_delta_comparison(product_code: str,
                                        before_data: pd.Series,
                                        after_data: pd.Series,
                                        outlier_handler: 'OutlierHandler',
                                        before_results: dict,
                                        before_calculator: SafetyStockCalculator,
                                        after_results: dict = None,
                                        after_calculator: SafetyStockCalculator = None):
    """LT間差分の分布（Before/After）と異常値処理統計情報を表示"""
    
    # LT差分 Before/After 比較
    st.markdown('<div class="step-sub-section">リードタイム間差分の分布（ヒストグラム）Before/After 比較</div>', unsafe_allow_html=True)
    
    lead_time_days = int(np.ceil(before_results['common_params']['lead_time_days']))
    stockout_tolerance_pct = before_results['common_params']['stockout_tolerance_pct']
    
    # BeforeのLT差分
    before_sums = before_data.rolling(window=lead_time_days).sum().dropna()
    before_delta2 = before_sums - before_sums.mean()
    before_delta3 = before_sums - before_calculator.plan_data.rolling(window=lead_time_days).sum().dropna().loc[before_sums.index]
    
    # AfterのLT差分
    after_sums = after_data.rolling(window=lead_time_days).sum().dropna()
    after_delta2 = after_sums - after_sums.mean()
    after_delta3 = after_sums - before_calculator.plan_data.rolling(window=lead_time_days).sum().dropna().loc[after_sums.index]
    
    # Before/Afterの安全在庫値を計算
    # Before安全在庫
    before_ss1 = before_results['model1_theoretical']['safety_stock']
    before_ss2 = before_results['model2_empirical_actual']['safety_stock']
    before_ss3 = before_results['model3_empirical_plan']['safety_stock']
    
    # After安全在庫（after_resultsが提供されている場合）
    if after_results is not None:
        after_ss1 = after_results['model1_theoretical']['safety_stock']
        after_ss2 = after_results['model2_empirical_actual']['safety_stock']
        after_ss3 = after_results['model3_empirical_plan']['safety_stock']
    else:
        # after_resultsが提供されていない場合は、Afterデータから計算
        after_ss1 = before_ss1  # 理論値は同じ
        
        # 右側（正の差分、欠品リスク側）のみを抽出
        after_delta2_positive = after_delta2[after_delta2 > 0]
        after_delta3_positive = after_delta3[after_delta3 > 0]
        N_pos2 = len(after_delta2_positive)
        N_pos3 = len(after_delta3_positive)
        
        # 安全在庫②の計算
        if N_pos2 == 0:
            after_ss2 = 0.0
        elif stockout_tolerance_pct <= 0:
            # 右側サンプルが存在することを確認してからmax()を実行
            if len(after_delta2_positive) > 0:
                after_ss2 = after_delta2_positive.max()
            else:
                after_ss2 = 0.0
        else:
            q = 1 - stockout_tolerance_pct / 100.0
            k = max(1, int(np.ceil(q * N_pos2)))
            after_delta2_positive_sorted = np.sort(after_delta2_positive.values)
            after_ss2 = after_delta2_positive_sorted[k - 1]
        
        # 安全在庫③の計算
        if N_pos3 == 0:
            after_ss3 = 0.0
        elif stockout_tolerance_pct <= 0:
            # 右側サンプルが存在することを確認してからmax()を実行
            if len(after_delta3_positive) > 0:
                after_ss3 = after_delta3_positive.max()
            else:
                after_ss3 = 0.0
        else:
            q = 1 - stockout_tolerance_pct / 100.0
            k = max(1, int(np.ceil(q * N_pos3)))
            after_delta3_positive_sorted = np.sort(after_delta3_positive.values)
            after_ss3 = after_delta3_positive_sorted[k - 1]
    
    # グラフ生成に必要なパラメータを準備
    is_before_ss1_undefined = before_results['model1_theoretical'].get('is_undefined', False) or before_ss1 is None
    is_p_zero = before_results['common_params']['stockout_tolerance_pct'] <= 0
    if after_results is not None:
        is_after_ss1_undefined = after_results['model1_theoretical'].get('is_undefined', False) or after_ss1 is None
    else:
        is_after_ss1_undefined = is_before_ss1_undefined
    
    # chartsモジュールからグラフを生成
    fig = create_outlier_lt_delta_comparison_chart(
        product_code,
        before_delta2,
        before_delta3,
        after_delta2,
        after_delta3,
        before_ss1,
        before_ss2,
        before_ss3,
        after_ss1,
        after_ss2,
        after_ss3,
        is_p_zero,
        is_before_ss1_undefined,
        is_after_ss1_undefined
    )
    
    st.plotly_chart(fig, use_container_width=True, key=f"after_cap_comparison_{product_code}")


def display_after_processing_comparison(product_code: str,
                                        before_results: dict,
                                        after_results: dict,
                                        before_calculator: SafetyStockCalculator,
                                        after_calculator: SafetyStockCalculator):
    """処理後の安全在庫再算出結果を表示（Before/After比較）"""
    
    # Before/After安全在庫①②③の比較グラフ（タイトルは呼び出し側で設定済み）
    
    # 平均需要を取得（安全在庫日数に変換するため）
    before_mean_demand = before_calculator.actual_data.mean() if before_calculator and hasattr(before_calculator, 'actual_data') else 1.0
    after_mean_demand = after_calculator.actual_data.mean() if after_calculator and hasattr(after_calculator, 'actual_data') else 1.0
    
    # ゼロ除算を防ぐ
    if before_mean_demand <= 0:
        before_mean_demand = 1.0
    if after_mean_demand <= 0:
        after_mean_demand = 1.0
    
    # 安全在庫数量を安全在庫日数に変換
    before_values = [
        before_results['model1_theoretical']['safety_stock'] / before_mean_demand if before_results['model1_theoretical']['safety_stock'] is not None else 0.0,
        before_results['model2_empirical_actual']['safety_stock'] / before_mean_demand,
        before_results['model3_empirical_plan']['safety_stock'] / before_mean_demand
    ]
    after_values = [
        after_results['model1_theoretical']['safety_stock'] / after_mean_demand if after_results['model1_theoretical']['safety_stock'] is not None else 0.0,
        after_results['model2_empirical_actual']['safety_stock'] / after_mean_demand,
        after_results['model3_empirical_plan']['safety_stock'] / after_mean_demand
    ]
    
    # chartsモジュールからグラフを生成
    fig = create_after_processing_comparison_chart(product_code, before_values, after_values)
    st.plotly_chart(fig, use_container_width=True, key=f"after_processing_comparison_detail_{product_code}")
    
    # 比較テーブル + 現行比表示（タイトルは呼び出し側で設定済み）
    
    # 現行安全在庫（日数）を取得
    current_days = before_results['current_safety_stock']['safety_stock_days']
    current_value = before_results['current_safety_stock']['safety_stock']
    
    # 安全在庫①がNoneの場合（p=0%など）の処理
    is_before_ss1_undefined = before_results['model1_theoretical'].get('is_undefined', False) or before_results['model1_theoretical']['safety_stock'] is None
    is_after_ss1_undefined = after_results['model1_theoretical'].get('is_undefined', False) or after_results['model1_theoretical']['safety_stock'] is None
    
    # 処理前の安全在庫数量を取得
    before_quantities = [
        before_results['model1_theoretical']['safety_stock'],
        before_results['model2_empirical_actual']['safety_stock'],
        before_results['model3_empirical_plan']['safety_stock']
    ]
    
    # 処理後の安全在庫数量を取得
    after_quantities = [
        after_results['model1_theoretical']['safety_stock'],
        after_results['model2_empirical_actual']['safety_stock'],
        after_results['model3_empirical_plan']['safety_stock']
    ]
    
    # 処理前の安全在庫数量（日数）を表示形式で作成
    before_display = []
    for i, (qty, days) in enumerate(zip(before_quantities, before_values)):
        if i == 0 and (is_before_ss1_undefined or qty is None or days is None or days == 0.0):
            before_display.append("—")
        else:
            before_display.append(f"{qty:.2f}（{days:.1f}日）")
    
    # 処理後の安全在庫数量（日数）を表示形式で作成
    after_display = []
    for i, (qty, days) in enumerate(zip(after_quantities, after_values)):
        if i == 0 and (is_after_ss1_undefined or qty is None or days is None or days == 0.0):
            after_display.append("—")
        else:
            after_display.append(f"{qty:.2f}（{days:.1f}日）")
    
    # 現行比を計算（処理後_安全在庫（日数） ÷ 現行安全在庫（日数））
    current_ratios = []
    for i, v in enumerate(after_values):
        if i == 0 and (is_after_ss1_undefined or v is None or v == 0.0):
            current_ratios.append("—")
        elif current_days > 0 and v is not None:
            ratio = v / current_days
            current_ratios.append(f"{ratio:.2f}")
        else:
            current_ratios.append("—")
    
    # 現行安全在庫の表示形式を作成
    current_display_before = f"{current_value:.2f}（{current_days:.1f}日）"
    current_display_after = "同左"
    current_ratio_display = "1.00"
    
    # 欠品許容率とZの対応表示を取得
    stockout_tolerance_pct = before_results['common_params']['stockout_tolerance_pct']
    safety_factor = before_results['common_params']['safety_factor']
    is_p_zero = stockout_tolerance_pct <= 0
    
    # 安全在庫①の欠品許容率→Z（片側）表示
    if is_before_ss1_undefined or is_p_zero:
        z_display = "計算不可（p=0→Z=∞）"
    else:
        z_display = f"{stockout_tolerance_pct:.1f}% → Z={safety_factor:.3f}"
    
    comparison_data = {
        'モデル': [
            '安全在庫①：理論値',
            '安全在庫②：実測値（実績−平均）',
            '安全在庫③：実測値（実績−計画）',
            '現行設定'
        ],
        '処理前_安全在庫数量（日数）': before_display + [current_display_before],
        '処理後_安全在庫数量（日数）': after_display + [current_display_after],
        '現行比（処理後 ÷ 現行）': current_ratios + [current_ratio_display]
    }
    
    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)
    
    # 在庫削減効果メッセージを表示（推奨モデル = 安全在庫③）
    if after_values[2] is not None and current_days > 0:
        recommended_ratio = after_values[2] / current_days
        reduction_rate = (1 - recommended_ratio) * 100
        st.markdown(f"""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>推奨モデルは現行比 {recommended_ratio:.2f} で、約 {reduction_rate:.1f}% の在庫削減が期待できます。</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>安全在庫③の値が取得できないため、削減効果を計算できません。</div>
        </div>
        """, unsafe_allow_html=True)


def display_after_cap_comparison(product_code: str,
                                 before_results: dict,
                                 after_results: dict,
                                 before_calculator: SafetyStockCalculator,
                                 after_calculator: SafetyStockCalculator,
                                 cap_applied: bool = True):
    """上限カット適用前後の安全在庫比較結果を表示
    
    Args:
        product_code: 商品コード
        before_results: 上限カット適用前の結果
        after_results: 上限カット適用後の結果
        before_calculator: 上限カット適用前の計算機
        after_calculator: 上限カット適用後の計算機
        cap_applied: 上限カットが適用されたかどうか（Falseの場合は「同左」を表示）
    """
    
    # タイトルを表示
    st.markdown('<div class="step-sub-section">安全在庫比較結果</div>', unsafe_allow_html=True)
    
    # 現行安全在庫（日数）を取得
    current_days = before_results['current_safety_stock']['safety_stock_days']
    current_value = before_results['current_safety_stock']['safety_stock']
    
    # 平均需要を取得（安全在庫日数に変換するため）
    before_mean_demand = before_calculator.actual_data.mean() if before_calculator and hasattr(before_calculator, 'actual_data') else 1.0
    after_mean_demand = after_calculator.actual_data.mean() if after_calculator and hasattr(after_calculator, 'actual_data') else 1.0
    
    # ゼロ除算を防ぐ
    if before_mean_demand <= 0:
        before_mean_demand = 1.0
    if after_mean_demand <= 0:
        after_mean_demand = 1.0
    
    # 安全在庫①がNoneの場合（p=0%など）の処理
    is_before_ss1_undefined = before_results['model1_theoretical'].get('is_undefined', False) or before_results['model1_theoretical']['safety_stock'] is None
    is_after_ss1_undefined = after_results['model1_theoretical'].get('is_undefined', False) or after_results['model1_theoretical']['safety_stock'] is None
    
    # 処理前の安全在庫数量を取得
    before_quantities = [
        before_results['model1_theoretical']['safety_stock'],
        before_results['model2_empirical_actual']['safety_stock'],
        before_results['model3_empirical_plan']['safety_stock']
    ]
    
    # 処理後の安全在庫数量を取得
    after_quantities = [
        after_results['model1_theoretical']['safety_stock'],
        after_results['model2_empirical_actual']['safety_stock'],
        after_results['model3_empirical_plan']['safety_stock']
    ]
    
    # 処理前の安全在庫数量（日数）を計算
    before_days = [
        before_quantities[0] / before_mean_demand if (before_quantities[0] is not None and before_mean_demand > 0) else 0.0,
        before_quantities[1] / before_mean_demand if before_mean_demand > 0 else 0.0,
        before_quantities[2] / before_mean_demand if before_mean_demand > 0 else 0.0
    ]
    
    # 処理後の安全在庫数量（日数）を計算
    after_days = [
        after_quantities[0] / after_mean_demand if (after_quantities[0] is not None and after_mean_demand > 0) else 0.0,
        after_quantities[1] / after_mean_demand if after_mean_demand > 0 else 0.0,
        after_quantities[2] / after_mean_demand if after_mean_demand > 0 else 0.0
    ]
    
    # 処理前の安全在庫数量（日数）を表示形式で作成
    before_display = []
    for i, (qty, days) in enumerate(zip(before_quantities, before_days)):
        if i == 0 and (is_before_ss1_undefined or qty is None or days is None or days == 0.0):
            before_display.append("—")
        else:
            before_display.append(f"{qty:.2f}（{days:.1f}日）")
    
    # 処理後の安全在庫数量（日数）を表示形式で作成
    after_display = []
    if not cap_applied:
        # 上限カットが適用されなかった場合、「同左」を表示
        for i in range(len(after_quantities)):
            after_display.append("同左")
    else:
        # 上限カットが適用された場合、通常通り表示
        for i, (qty, days) in enumerate(zip(after_quantities, after_days)):
            if i == 0 and (is_after_ss1_undefined or qty is None or days is None or days == 0.0):
                after_display.append("—")
            else:
                after_display.append(f"{qty:.2f}（{days:.1f}日）")
    
    # 現行比を計算（処理後_安全在庫（日数） ÷ 現行安全在庫（日数））
    current_ratios = []
    if not cap_applied:
        # 上限カットが適用されなかった場合、上限カット前の値と同じ現行比を計算
        for i, v in enumerate(before_days):
            if i == 0 and (is_before_ss1_undefined or v is None or v == 0.0):
                current_ratios.append("—")
            elif current_days > 0 and v is not None:
                ratio = v / current_days
                current_ratios.append(f"{ratio:.2f}")
            else:
                current_ratios.append("—")
    else:
        # 上限カットが適用された場合、通常通り計算
        for i, v in enumerate(after_days):
            if i == 0 and (is_after_ss1_undefined or v is None or v == 0.0):
                current_ratios.append("—")
            elif current_days > 0 and v is not None:
                ratio = v / current_days
                current_ratios.append(f"{ratio:.2f}")
            else:
                current_ratios.append("—")
    
    # 現行安全在庫の表示形式を作成
    current_display_before = f"{current_value:.2f}（{current_days:.1f}日）"
    current_display_after = "同左"
    current_ratio_display = "1.00"
    
    # 欠品許容率とZの対応表示を取得
    stockout_tolerance_pct = before_results['common_params']['stockout_tolerance_pct']
    safety_factor = before_results['common_params']['safety_factor']
    is_p_zero = stockout_tolerance_pct <= 0
    
    # 安全在庫①の欠品許容率→Z（片側）表示
    if is_before_ss1_undefined or is_p_zero:
        z_display = "計算不可（p=0→Z=∞）"
    else:
        z_display = f"{stockout_tolerance_pct:.1f}% → Z={safety_factor:.3f}"
    
    comparison_data = {
        'モデル': [
            '安全在庫①：理論値',
            '安全在庫②：実測値（実績−平均）',
            '安全在庫③：実測値（実績−計画）',
            '現行設定'
        ],
        '上限カット前_安全在庫数量（日数）': before_display + [current_display_before],
        '上限カット後_安全在庫数量（日数）': after_display + [current_display_after],
        '現行比（上限カット後 ÷ 現行）': current_ratios + [current_ratio_display]
    }
    
    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)
    
    # 在庫削減効果メッセージを表示（推奨モデル = 安全在庫③）
    # 上限カットが適用されなかった場合でも、上限カット前の値を使用して計算
    target_days = after_days[2] if cap_applied else before_days[2]
    if target_days is not None and current_days > 0:
        recommended_ratio = target_days / current_days
        reduction_rate = (1 - recommended_ratio) * 100
        st.markdown(f"""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>推奨モデルは現行比 {recommended_ratio:.2f} で、約 {reduction_rate:.1f}% の在庫削減が期待できます。</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>安全在庫③の値が取得できないため、削減効果を計算できません。</div>
        </div>
        """, unsafe_allow_html=True)

