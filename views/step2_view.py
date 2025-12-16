"""
STEP2 ビュー
安全在庫算出ロジック体感（選定機種）のUI
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional
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
    create_after_processing_comparison_chart,
    create_safety_stock_comparison_bar_chart,
    create_before_after_comparison_bar_chart,
    create_adopted_model_comparison_charts,
    create_cap_comparison_bar_chart,
    create_cap_adopted_model_comparison_charts
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
    
    # 商品コード選択モード
    st.markdown('<div class="step-sub-section">商品コードの選択</div>', unsafe_allow_html=True)
    selection_mode = st.radio(
        "選択モード",
        options=["任意の商品コード", "計画誤差率（プラス）大", "計画誤差率（マイナス）大"],
        help="任意の商品コードから選択するか、計画誤差率が大きい商品コードから選択できます。",
        horizontal=True,
        key="step2_selection_mode"
    )
    
    # 計画誤差率の閾値設定（詳細設定として折り畳み）
    with st.expander("詳細設定（任意）", expanded=False):
        st.markdown("計画誤差率の閾値（プラス／マイナス）は、商品コードの絞り込みに使用します。<br>初期値（±50%）のままで問題ない場合は、この設定を変更する必要はありません。慣れてきたユーザーが、より厳しい条件で分析したい場合にご活用ください。", unsafe_allow_html=True)
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
                <strong>計画誤差率が大きい（+{plan_plus_threshold:.1f}%以上）商品コードを選択できます。</strong><br><strong>計画誤差率（プラス）</strong> ＝（実績合計 − 計画合計）÷ 実績合計 × 100%（<strong>※実績合計 ＞ 計画合計</strong>：実績がどれだけ計画を上回ったか）
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
                <strong>計画誤差率が大きい（{plan_minus_threshold:.1f}%以下）商品コードを選択できます。</strong><br><strong>計画誤差率（マイナス）</strong> ＝（実績合計 − 計画合計）÷ 実績合計 × 100%（<strong>※実績合計 ＜ 計画合計</strong>：実績がどれだけ計画を下回ったか）
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
    <div class="step-description">安全在庫の算出に必要な条件（<strong>リードタイム</strong>、<strong>欠品許容率</strong>）を設定します。<br>
    これらの設定値は、後続の手順で適用される安全在庫モデルの結果に直接影響します。</div>
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
    <div class="step-description">リードタイム期間の実績合計と計画合計を比較し、<strong>実績のバラつき（実績−平均）</strong>と <strong>計画誤差（実績−計画）</strong> を可視化します。<br>
    時系列グラフと統計情報により、需要変動の大きさや計画精度を把握し、<strong>次の手順④で安全在庫を算出するための前提となるデータ特性</strong> を確認します。</div>
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
        
        # 1. 日次計画と日次実績の時系列推移
        st.markdown('<div class="step-sub-section">日次計画と日次実績の時系列推移</div>', unsafe_allow_html=True)
        fig = create_time_series_chart(product_code, calculator)
        st.plotly_chart(fig, use_container_width=True, key=f"time_series_step2_{product_code}")
        
        # 2. 日次計画と日次実績の統計情報（計画誤差率を追加）
        st.markdown('<div class="step-sub-section">日次計画と日次実績の統計情報</div>', unsafe_allow_html=True)
        display_plan_actual_statistics(product_code, calculator)
        
        # 3. リードタイム区間の総件数（スライド集計）
        st.markdown('<div class="step-sub-section">リードタイム区間の総件数（スライド集計）</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="annotation-success-box">
                <span class="icon">✅</span>
                <div class="text">
                    <strong>リードタイム区間の総件数：{total_count}件</strong><br>
                    リードタイム日数分の計画および実績データを1日ずつスライドしながら合計します。<br>
                    この件数が、後続の「リードタイム期間合計（計画・実績）」や「リードタイム間差分」の分析単位になります。
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # 4. リードタイム期間合計（計画・実績）の統計情報（NEW）
        st.markdown('<div class="step-sub-section">リードタイム期間合計（計画・実績）の統計情報</div>', unsafe_allow_html=True)
        display_lead_time_total_statistics(product_code, calculator)
        
        # 5. リードタイム間差分の時系列推移
        st.markdown('<div class="step-sub-section">リードタイム間差分の時系列推移</div>', unsafe_allow_html=True)
        fig = create_time_series_delta_bar_chart(product_code, None, calculator, show_safety_stock_lines=False)
        st.plotly_chart(fig, use_container_width=True, key=f"delta_bar_step2_{product_code}")
        
        # 6. リードタイム間差分の統計情報
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
        <div class="step-description">リードタイム間差分に基づく <strong>2つの実測モデル（安全在庫②・③）</strong>を中心に、比較指標として <strong>理論モデル（安全在庫①）</strong>も算出し、3種類の安全在庫を比較・評価します。<br>
        ヒストグラムで「実績のばらつき」や「計画誤差」の分布の形状を確認し、各モデルの安全在庫ラインがどのように導かれるかを理解できます。</div>
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
            
            # 安全在庫比較結果（棒グラフ＋表の一体化）
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
        <div class="step-description">実績データに含まれる <strong>統計的スパイク（異常な上振れ値）</strong>を検出し、設定した <strong>上限値（異常基準）</strong>へ補正します。<br>
        突発的に大きく跳ね上がる値を抑えることで、安全在庫が過大に算定されることを防ぎ、算出結果の妥当性を高めます。</div>
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
                    <div class="text"><strong>実績異常値処理結果：</strong>異常値は検出されませんでした。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>実績異常値処理結果：</strong>異常値を検出し、補正処理を実施しました。</div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown('<div class="step-sub-section">実績異常値処理後：実績データ比較結果（Before/After）</div>', unsafe_allow_html=True)
            
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
        <div class="step-description">実績異常値補正を反映した安全在庫を再算出し、<strong>補正前（Before）との違い </strong>がどの程度生じるかを比較・把握します。<br>
補正が安全在庫の設定に与える影響を確認し、より妥当なモデルを選択します。</div>
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
            st.markdown('<div class="step-sub-section">実績異常値処理後：安全在庫比較結果（Before/After）</div>', unsafe_allow_html=True)
            
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
            st.markdown('<div class="step-sub-section">実績異常値処理後：リードタイム間差分の分布比較結果（Before/After）</div>', unsafe_allow_html=True)
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
    
    # ========== 手順⑦：計画異常値処理を実施し、安全在庫を確定する ==========
    if st.session_state.get('step2_recalculated', False) and st.session_state.get('step2_after_results') is not None:
        st.markdown("""
        <div class="step-middle-section">
            <p>手順⑦：計画異常値処理を実施し、安全在庫を確定する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">計画誤差率を計算し、その判定結果に基づいて、安全在庫として採用するモデル（②または③）を決定します。<br>
        計画誤差率が大きい場合は <strong>安全在庫②（実績のバラつきを反映したモデル）</strong>、許容範囲内の場合は <strong>安全在庫③（計画誤差を考慮した推奨モデル）</strong>を採用します。</div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 1. 計画異常値処理の閾値設定
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
            
            # セッション状態に保存（ウィジェットの値は自動的にセッション状態に保存されるため、明示的な設定は不要）
            # ただし、他の場所で参照する場合は、step2_plan_plus_threshold_finalとstep2_plan_minus_threshold_finalを使用
            
            final_results = st.session_state.get('step2_after_results')
            final_calculator = st.session_state.get('step2_after_calculator')
            
            # 2. 計画誤差率情報
            st.markdown('<div class="step-sub-section">計画誤差率情報</div>', unsafe_allow_html=True)
            plan_info_data = {
                '対象商品コード': [product_code],
                '実績合計': [f"{actual_data.sum():,.2f}"],
                '計画合計': [f"{plan_total:,.2f}" if plan_total > 0 else "0.00"],
                '計画誤差（実績合計−計画合計）': [f"{plan_error:,.2f}"],
                '計画誤差率': [f"{plan_error_rate:.1f}%" if plan_error_rate is not None else "計算不可"]
            }
            plan_info_df = pd.DataFrame(plan_info_data)
            st.dataframe(plan_info_df, use_container_width=True, hide_index=True)
            
            # 3. 計画異常値処理の判定結果
            st.markdown('<div class="step-sub-section">計画異常値処理の判定結果</div>', unsafe_allow_html=True)
            
            if plan_error_rate is None:
                # 計画誤差率計算不可の場合
                st.markdown("""
                <div class="annotation-warning-box">
                    <span class="icon">⚠</span>
                    <div class="text"><strong>計画異常値処理結果：</strong>計画誤差率が計算できません。安全在庫②を代替採用します。</div>
                </div>
                """, unsafe_allow_html=True)
                adopted_model = "ss2"
                adopted_model_name = "安全在庫②（実測値：実績−平均）"
            elif is_anomaly:
                # 異常値の場合
                st.markdown(f"""
                <div class="annotation-warning-box">
                    <span class="icon">⚠</span>
                    <div class="text"><strong>計画異常値処理結果：</strong>計画誤差率が {plan_error_rate:.1f}％で、閾値（{plan_plus_threshold_final:.1f}％ / {plan_minus_threshold_final:.1f}％）を外れているため、安全在庫③は採用できません。安全在庫②を代替採用します。</div>
                </div>
                """, unsafe_allow_html=True)
                adopted_model = "ss2"
                adopted_model_name = "安全在庫②（実測値：実績−平均）"
            else:
                # 正常値の場合
                st.markdown(f"""
                <div class="annotation-info-box">ℹ️ <strong>計画異常値処理結果：</strong>計画誤差率は {plan_error_rate:.1f}％で許容範囲内です。安全在庫③をそのまま採用します。</div>
                """, unsafe_allow_html=True)
                adopted_model = "ss3"
                adopted_model_name = "安全在庫③（実測値：実績−計画）"
            
            # セッション状態に保存
            st.session_state.step2_adopted_model = adopted_model
            st.session_state.step2_adopted_model_name = adopted_model_name
            
            # 採用モデルの安全在庫を取得
            if adopted_model == "ss2":
                adopted_safety_stock = final_results['model2_empirical_actual']['safety_stock']
            else:
                adopted_safety_stock = final_results['model3_empirical_plan']['safety_stock']
            
            st.session_state.step2_adopted_safety_stock = adopted_safety_stock
            
            # ボタン: 安全在庫③を適正化する（安全在庫②を代替採用）
            if st.button("安全在庫③を適正化する（安全在庫②を代替採用）", type="primary", use_container_width=True, key="step2_finalize_safety_stock_button"):
                st.session_state.step2_adopted_model = adopted_model
                st.session_state.step2_adopted_model_name = adopted_model_name
                st.session_state.step2_adopted_safety_stock = adopted_safety_stock
                # メッセージは結果表示時に統合メッセージとして表示するため、ここでは表示しない
                st.rerun()
            
            if st.session_state.get('step2_adopted_model') is not None:
                adopted_model = st.session_state.get('step2_adopted_model')
                adopted_model_name = st.session_state.get('step2_adopted_model_name')
                adopted_safety_stock = st.session_state.get('step2_adopted_safety_stock')
                
                st.markdown('<div class="step-sub-section">計画異常値処理後：安全在庫比較結果（採用モデル含む）</div>', unsafe_allow_html=True)
                
                # a) 採用モデル確定メッセージ（バナー）は削除し、統合メッセージに統合
                daily_actual_mean = final_calculator.actual_data.mean()
                adopted_safety_stock_days = adopted_safety_stock / daily_actual_mean if daily_actual_mean > 0 else 0
                
                # b) 棒グラフ（左右２グラフ＋中央に「➡」表示）
                # グラフとテーブルの位置を同期させるため、st.columnsでレイアウトを調整
                # 上の5本の棒グラフ（「現行設定」「安全在庫①」「安全在庫②」「安全在庫③」「採用モデル」）と
                # 下の表の5列を視覚的に揃えるため、左グラフ（4本）と右グラフ（1本）の幅の比率を4:1に近づける
                col_left_space, col_graphs = st.columns([0.12, 0.88])
                with col_left_space:
                    st.empty()  # 左側に空のスペースを確保（テーブルのインデックス列に対応）
                with col_graphs:
                    # グラフ間の距離を縮める（中央の矢印用カラムを細くして左右のグラフを中央へ寄せる）
                    # 左グラフ4本と右グラフ1本の比率を考慮して、左:矢印:右 = 4:0.2:1 の比率で配置
                    # 左側のグラフを7mm広げ、右側のグラフを7mm狭くする
                    col_left, col_arrow, col_right = st.columns([3.8, 0.2, 1.0])
                    
                    with col_left:
                        # 左側グラフ：候補モデル比較
                        # daily_actual_mean > 0 のガードを追加してゼロ除算を防止
                        if daily_actual_mean > 0:
                            ss1_days = final_results['model1_theoretical']['safety_stock'] / daily_actual_mean if final_results['model1_theoretical']['safety_stock'] is not None else None
                            ss2_days = final_results['model2_empirical_actual']['safety_stock'] / daily_actual_mean
                            ss3_days = final_results['model3_empirical_plan']['safety_stock'] / daily_actual_mean
                        else:
                            ss1_days = None
                            ss2_days = 0
                            ss3_days = 0
                        
                        fig_left, fig_right = create_adopted_model_comparison_charts(
                            product_code=product_code,
                            current_days=final_results['current_safety_stock']['safety_stock_days'],
                            ss1_days=ss1_days,
                            ss2_days=ss2_days,
                            ss3_days=ss3_days,
                            adopted_model=adopted_model,
                            is_ss1_undefined=final_results['model1_theoretical'].get('is_undefined', False)
                        )
                        st.plotly_chart(fig_left, use_container_width=True, key=f"adopted_model_left_{product_code}")
                    
                    with col_arrow:
                        # 中央の矢印を縦に3つ並べて強調表示
                        st.markdown("""
                        <div style='text-align: center; margin-top: 180px;'>
                            <div style='font-size: 48px; font-weight: bold; color: #333333; line-height: 1.2;'>➡</div>
                            <div style='font-size: 48px; font-weight: bold; color: #333333; line-height: 1.2;'>➡</div>
                            <div style='font-size: 48px; font-weight: bold; color: #333333; line-height: 1.2;'>➡</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col_right:
                        # 右側グラフ：採用モデル専用
                        st.plotly_chart(fig_right, use_container_width=True, key=f"adopted_model_right_{product_code}")
                
                # c) テーブル
                theoretical_value = final_results['model1_theoretical']['safety_stock']
                is_model1_undefined = final_results['model1_theoretical'].get('is_undefined', False) or theoretical_value is None
                empirical_actual_value = final_results['model2_empirical_actual']['safety_stock']
                empirical_plan_value = final_results['model3_empirical_plan']['safety_stock']
                current_value = final_results['current_safety_stock']['safety_stock']
                current_days = final_results['current_safety_stock']['safety_stock_days']
                
                theoretical_days = theoretical_value / daily_actual_mean if (daily_actual_mean > 0 and not is_model1_undefined and theoretical_value is not None) else 0
                empirical_actual_days = empirical_actual_value / daily_actual_mean if daily_actual_mean > 0 else 0
                empirical_plan_days = empirical_plan_value / daily_actual_mean if daily_actual_mean > 0 else 0
                
                if is_model1_undefined:
                    theoretical_display = "計算不可（p=0→Z=∞）"
                else:
                    theoretical_display = f"{theoretical_value:.2f}（{theoretical_days:.1f}日）"
                
                comparison_data = {
                    '現行設定': [
                        f"{current_value:.2f}（{current_days:.1f}日）",
                        f"{current_days / current_days:.2f}" if current_days > 0 else "1.00"
                    ],
                    '安全在庫①': [
                        theoretical_display,
                        f"{theoretical_days / current_days:.2f}" if (current_days > 0 and not is_model1_undefined and theoretical_days > 0) else "—"
                    ],
                    '安全在庫②': [
                        f"{empirical_actual_value:.2f}（{empirical_actual_days:.1f}日）",
                        f"{empirical_actual_days / current_days:.2f}" if current_days > 0 else "—"
                    ],
                    '安全在庫③': [
                        f"{empirical_plan_value:.2f}（{empirical_plan_days:.1f}日）",
                        f"{empirical_plan_days / current_days:.2f}" if current_days > 0 else "—"
                    ],
                    '採用モデル': [
                        f"{adopted_safety_stock:.2f}（{adopted_safety_stock_days:.1f}日）",
                        f"{adopted_safety_stock_days / current_days:.2f}" if current_days > 0 else "—"
                    ]
                }
                
                comparison_df = pd.DataFrame(comparison_data, index=['処理後_安全在庫数量（日数）', '現行比（処理後 ÷ 現行）'])
                
                # 採用モデル列をハイライト（安全在庫③と同じ薄い緑に統一）
                # 安全在庫③の色: rgba(100, 200, 150, 0.8) をテーブルの背景色として使用
                # 白色背景にrgba(100, 200, 150, 0.8)を重ねた場合の色を計算
                # R: 100*0.8 + 255*0.2 = 80 + 51 = 131
                # G: 200*0.8 + 255*0.2 = 160 + 51 = 211
                # B: 150*0.8 + 255*0.2 = 120 + 51 = 171
                # → rgb(131, 211, 171) → #83D3AB
                # テーブルの背景色として使用する場合は、より薄い色を使用
                adopted_model_bg_color = '#B4E6D1'  # 安全在庫③の色系統（rgba(100, 200, 150, 0.8)）に基づいた薄い緑
                
                # 列名で採用モデル列を特定
                styled_df = comparison_df.style.applymap(
                    lambda x: f'background-color: {adopted_model_bg_color}; font-weight: bold;' if isinstance(x, str) and x != '' else '',
                    subset=['採用モデル']
                )
                # 行ラベルが切れないように、CSSで調整
                st.markdown("""
                <style>
                .stDataFrame {
                    width: 100%;
                }
                .stDataFrame table {
                    table-layout: auto;
                }
                .stDataFrame th:first-child,
                .stDataFrame td:first-child {
                    min-width: 250px !important;
                    white-space: nowrap !important;
                    max-width: none !important;
                }
                </style>
                """, unsafe_allow_html=True)
                st.dataframe(styled_df, use_container_width=True)
                
                # d) 統合された結論メッセージ（注釈）
                if adopted_safety_stock_days is not None and current_days > 0:
                    # 現行比を計算
                    recommended_ratio = adopted_safety_stock_days / current_days
                    
                    # Aパターン：安全在庫③（推奨モデル）を採用した場合
                    if adopted_model == "ss3":
                        model_display_name = "安全在庫③（推奨モデル）"
                        
                        # ① 現行設定 ＞ 安全在庫③ の場合
                        if recommended_ratio < 1:
                            reduction_rate = (1 - recommended_ratio) * 100
                            effect_text = f"約 {round(reduction_rate):.0f}% の在庫削減が期待できます。"
                        # ② 現行設定 ＜ 安全在庫③ の場合
                        else:
                            increase_rate = (recommended_ratio - 1) * 100
                            effect_text = f"約 {round(increase_rate):.0f}% の在庫増加となります。"
                        
                        # 統合メッセージを1つのブロックとして表示
                        st.markdown(f"""
                        <div class="annotation-success-box">
                            <span class="icon">✅</span>
                            <div class="text"><strong>採用モデル：</strong>{model_display_name}を採用しました。現行比 {recommended_ratio:.2f} に変更はありません。{effect_text}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Bパターン：安全在庫②を代替採用した場合
                    else:  # adopted_model == "ss2"
                        model_display_name = "安全在庫②（実績のバラつきを反映したモデル）"
                        
                        # ③ 現行設定 ＞ 安全在庫② の場合
                        if recommended_ratio < 1:
                            reduction_rate = (1 - recommended_ratio) * 100
                            effect_text = f"約 {round(reduction_rate):.0f}% の在庫削減が期待できます。"
                        # ④ 現行設定 ＜ 安全在庫② の場合
                        else:
                            increase_rate = (recommended_ratio - 1) * 100
                            effect_text = f"約 {round(increase_rate):.0f}% の在庫増加となります。"
                        
                        # 統合メッセージを1つのブロックとして表示
                        st.markdown(f"""
                        <div class="annotation-success-box">
                            <span class="icon">✅</span>
                            <div class="text"><strong>採用モデル：</strong>{model_display_name}を代替採用しました。現行比 {recommended_ratio:.2f} で、{effect_text}</div>
                        </div>
                        """, unsafe_allow_html=True)
                elif current_days <= 0:
                    # 採用モデル名を統合メッセージ用の形式に変換
                    if adopted_model == "ss2":
                        model_display_name = "安全在庫②（実測値－実績平均）"
                    else:
                        model_display_name = "安全在庫③（実測値：実績−計画）"
                    
                    st.markdown(f"""
                    <div class="annotation-success-box">
                        <span class="icon">✅</span>
                        <div class="text"><strong>採用モデル：</strong>{model_display_name}を採用しました。<strong>在庫削減効果：</strong>現行設定がないため、削減効果を計算できません。</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.divider()
    
    # ========== 手順⑧：上限カットを適用する ==========
    if st.session_state.get('step2_adopted_model') is not None:
        st.markdown("""
        <div class="step-middle-section">
            <p>手順⑧：上限カットを適用する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">異常値処理後の安全在庫が過大にならないよう、<strong>区分別の上限日数を適用</strong>して安全在庫を調整します。<br>
        上限日数は区分ごとに設定でき、<strong>0 を入力した場合は上限なし（制限なし）</strong>として扱います。</div>
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
            
            product_code = st.session_state.get('step2_product_code')
            
            # 上限カット適用前後の安全在庫比較結果
            st.markdown('<div class="step-sub-section">上限カット後：安全在庫比較結果（採用モデル含む）</div>', unsafe_allow_html=True)
            
            # 採用モデルを取得（手順⑦で決定されたモデル）
            adopted_model = st.session_state.get('step2_adopted_model', 'ss3')  # デフォルトはss3
            if adopted_model == "ss2":
                adopted_model_days = final_results['model2_empirical_actual']['safety_stock'] / final_calculator.actual_data.mean() if final_calculator.actual_data.mean() > 0 else 0
            else:
                adopted_model_days = final_results['model3_empirical_plan']['safety_stock'] / final_calculator.actual_data.mean() if final_calculator.actual_data.mean() > 0 else 0
            
            # 上限カット適用前後の安全在庫比較テーブル
            display_after_cap_comparison(
                product_code,
                st.session_state.get('step2_after_results'),
                final_results,
                st.session_state.get('step2_after_calculator'),
                final_calculator,
                cap_applied=category_limit_applied,
                adopted_model_days=adopted_model_days
            )
            
            st.divider()


# ========================================
# STEP2専用のUIヘルパー関数
# ========================================

def display_plan_actual_statistics(product_code: str, calculator: SafetyStockCalculator):
    """計画と実績の統計情報テーブルを表示"""
    
    # データ取得
    plan_data = calculator.plan_data
    actual_data = calculator.actual_data
    
    # 計画誤差率を計算
    plan_error_rate, plan_error, plan_total = calculate_plan_error_rate(actual_data, plan_data)
    
    # 計画（単体）の統計情報（6項目に統一）
    plan_stats = {
        '項目': '日次計画',
        '件数': len(plan_data),
        '平均': np.mean(plan_data),
        '標準偏差': np.std(plan_data),
        '最小値': np.min(plan_data),
        '中央値': np.median(plan_data),
        '最大値': np.max(plan_data),
        '計画誤差率': None  # 計画には計画誤差率は表示しない
    }
    
    # 実績（単体）の統計情報（6項目に統一 + 計画誤差率）
    actual_stats = {
        '項目': '日次実績',
        '件数': len(actual_data),
        '平均': np.mean(actual_data),
        '標準偏差': np.std(actual_data),
        '最小値': np.min(actual_data),
        '中央値': np.median(actual_data),
        '最大値': np.max(actual_data),
        '計画誤差率': plan_error_rate  # 計画誤差率を追加
    }
    
    # データフレーム作成（計画→実績の順）
    # 計算ロジックは変更せず、元データを保持
    stats_df = pd.DataFrame([plan_stats, actual_stats])
    
    # 表示用コピーを作成（元のDataFrameは変更しない）
    display_df = stats_df.copy()
    
    # 数値表示形式を統一（表示用コピーに対してのみ適用）
    numeric_columns = ['平均', '標準偏差', '最小値', '中央値', '最大値']
    
    # 件数は整数表示
    display_df['件数'] = display_df['件数'].apply(lambda x: f'{int(x):.0f}' if not pd.isna(x) else '')
    
    # 小数値は小数第2位まで表示（-0.000000も0.00として表示される）
    for col in numeric_columns:
        display_df[col] = display_df[col].apply(lambda x: f'{x:.2f}' if not pd.isna(x) else '')
    
    # 計画誤差率はパーセント表示（例：-20.58%）
    display_df['計画誤差率'] = display_df['計画誤差率'].apply(
        lambda x: f'{x:.2f}%' if x is not None and not pd.isna(x) else ''
    )
    
    # グラフ直下に配置するためのスタイル適用
    st.markdown('<div class="statistics-table-container">', unsafe_allow_html=True)
    
    # 計画誤差率列にスタイルを適用（背景：薄い緑、文字色：緑）
    def style_plan_error_rate(val):
        """計画誤差率列のスタイル設定"""
        if val is not None and str(val) != '' and '%' in str(val):
            return 'background-color: #E8F5E9; color: #2E7D32;'  # 薄い緑背景、緑文字
        return ''
    
    # スタイルを適用したDataFrameを表示
    styled_df = display_df.style.applymap(
        style_plan_error_rate,
        subset=['計画誤差率']
    )
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def display_lead_time_total_statistics(product_code: str, calculator: SafetyStockCalculator):
    """リードタイム期間合計（計画・実績）の統計情報テーブルを表示"""
    
    # リードタイム日数を取得
    lead_time_days = calculator._get_lead_time_in_working_days()
    lead_time_days = int(np.ceil(lead_time_days))
    
    # データ取得
    plan_data = calculator.plan_data
    actual_data = calculator.actual_data
    
    # リードタイム期間の計画合計と実績合計を計算（1日ずつスライド）
    plan_sums = plan_data.rolling(window=lead_time_days).sum().dropna()
    actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
    
    # 共通インデックスを取得
    common_idx = plan_sums.index.intersection(actual_sums.index)
    plan_sums_common = plan_sums.loc[common_idx]
    actual_sums_common = actual_sums.loc[common_idx]
    
    # 計画合計の統計情報
    plan_total_stats = {
        '項目': 'リードタイム期間の計画合計',
        '件数': len(plan_sums_common),
        '平均': np.mean(plan_sums_common),
        '標準偏差': np.std(plan_sums_common),
        '最小値': np.min(plan_sums_common),
        '中央値': np.median(plan_sums_common),
        '最大値': np.max(plan_sums_common)
    }
    
    # 実績合計の統計情報
    actual_total_stats = {
        '項目': 'リードタイム期間の実績合計',
        '件数': len(actual_sums_common),
        '平均': np.mean(actual_sums_common),
        '標準偏差': np.std(actual_sums_common),
        '最小値': np.min(actual_sums_common),
        '中央値': np.median(actual_sums_common),
        '最大値': np.max(actual_sums_common)
    }
    
    # データフレーム作成
    # 計算ロジックは変更せず、元データを保持
    stats_df = pd.DataFrame([plan_total_stats, actual_total_stats])
    
    # 表示用コピーを作成（元のDataFrameは変更しない）
    display_df = stats_df.copy()
    
    # 数値表示形式を統一（表示用コピーに対してのみ適用）
    numeric_columns = ['平均', '標準偏差', '最小値', '中央値', '最大値']
    
    # 件数は整数表示
    display_df['件数'] = display_df['件数'].apply(lambda x: f'{int(x):.0f}' if not pd.isna(x) else '')
    
    # 小数値は小数第2位まで表示（-0.000000も0.00として表示される）
    for col in numeric_columns:
        display_df[col] = display_df[col].apply(lambda x: f'{x:.2f}' if not pd.isna(x) else '')
    
    # グラフ直下に配置するためのスタイル適用
    st.markdown('<div class="statistics-table-container">', unsafe_allow_html=True)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
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
        '項目': 'リードタイム間差分（実績 − 計画）※計画誤差',
        '件数': len(delta3),
        '平均': np.mean(delta3),
        '標準偏差': np.std(delta3),
        '最小値': np.min(delta3),
        '中央値': np.median(delta3),
        '最大値': np.max(delta3)
    }
    
    # データフレーム作成
    # 計算ロジックは変更せず、元データを保持
    stats_df = pd.DataFrame([model2_stats, model3_stats])
    
    # 表示用コピーを作成（元のDataFrameは変更しない）
    display_df = stats_df.copy()
    
    # 数値表示形式を統一（表示用コピーに対してのみ適用）
    numeric_columns = ['平均', '標準偏差', '最小値', '中央値', '最大値']
    
    # 件数は整数表示
    display_df['件数'] = display_df['件数'].apply(lambda x: f'{int(x):.0f}' if not pd.isna(x) else '')
    
    # 小数値は小数第2位まで表示（-0.000000も0.00として表示される）
    for col in numeric_columns:
        display_df[col] = display_df[col].apply(lambda x: f'{x:.2f}' if not pd.isna(x) else '')
    
    # グラフ直下に配置するためのスタイル適用
    st.markdown('<div class="statistics-table-container">', unsafe_allow_html=True)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
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
        '項目': 'リードタイム間差分（実績 − 計画）※計画誤差',
        '件数': len(hist_data['model3_delta']),
        '平均': np.mean(hist_data['model3_delta']),
        '標準偏差': np.std(hist_data['model3_delta']),
        '最小値': np.min(hist_data['model3_delta']),
        '中央値': np.median(hist_data['model3_delta']),
        '最大値': np.max(hist_data['model3_delta'])
    }
    
    # データフレーム作成
    # 計算ロジックは変更せず、元データを保持
    stats_df = pd.DataFrame([model2_stats, model3_stats])
    
    # 表示用コピーを作成（元のDataFrameは変更しない）
    display_df = stats_df.copy()
    
    # 数値表示形式を統一（表示用コピーに対してのみ適用）
    numeric_columns = ['平均', '標準偏差', '最小値', '中央値', '最大値']
    
    # 件数は整数表示
    display_df['件数'] = display_df['件数'].apply(lambda x: f'{int(x):.0f}' if not pd.isna(x) else '')
    
    # 小数値は小数第2位まで表示（-0.000000も0.00として表示される）
    for col in numeric_columns:
        display_df[col] = display_df[col].apply(lambda x: f'{x:.2f}' if not pd.isna(x) else '')
    
    # グラフ直下に配置するためのスタイル適用
    st.markdown('<div class="statistics-table-container">', unsafe_allow_html=True)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def display_safety_stock_comparison(product_code: str, results: dict, calculator: SafetyStockCalculator):
    """安全在庫比較結果を表示（棒グラフ＋表の一体化）"""
    
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
    
    # 1. 棒グラフを表示
    # グラフとテーブルの位置を同期させるため、st.columnsでレイアウトを調整
    col_left, col_graph = st.columns([0.12, 0.88])
    with col_left:
        st.empty()  # 左側に空のスペースを確保（テーブルのインデックス列に対応）
    with col_graph:
        fig = create_safety_stock_comparison_bar_chart(
            product_code=product_code,
            current_days=current_days,
            ss1_days=theoretical_days if not is_model1_undefined and theoretical_days > 0 else None,
            ss2_days=empirical_actual_days,
            ss3_days=empirical_plan_days,
            is_ss1_undefined=is_model1_undefined,
            use_after_colors=False  # Before色を使用
        )
        st.plotly_chart(fig, use_container_width=True, key=f"safety_stock_comparison_{product_code}")
    
    # 2. 比較テーブルを表示
    stockout_tolerance_pct = results['common_params']['stockout_tolerance_pct']
    safety_factor = results['common_params']['safety_factor']
    is_p_zero = stockout_tolerance_pct <= 0
    
    # ①の値を判定
    if is_model1_undefined or is_p_zero:
        theoretical_display = "計算不可（p=0→Z=∞）"
        theoretical_ratio = "—"
    else:
        theoretical_display = f"{theoretical_value:.2f}（{theoretical_days:.1f}日）"
        # 現行比を1.00ベースの数値表示に変更
        theoretical_ratio = f"{theoretical_value / current_value:.2f}" if current_value > 0 else "—"
    
    # 現行比を1.00ベースの数値表示に変更
    empirical_actual_ratio = f"{empirical_actual_value / current_value:.2f}" if current_value > 0 else "—"
    empirical_plan_ratio = f"{empirical_plan_value / current_value:.2f}" if current_value > 0 else "—"
    
    # テーブルの列構成を手順⑥と同じ構造に変更
    # 「項目」列を削除し、代わりにDataFrameのindexを使用
    # 順序：「現行設定」「安全在庫①」「安全在庫②」「安全在庫③」
    comparison_data = {
        '現行設定': [
            f"{current_value:.2f}（{current_days:.1f}日）",
            "1.00"
        ],
        '安全在庫①': [
            theoretical_display,
            theoretical_ratio
        ],
        '安全在庫②': [
            f"{empirical_actual_value:.2f}（{empirical_actual_days:.1f}日）",
            empirical_actual_ratio
        ],
        '安全在庫③': [
            f"{empirical_plan_value:.2f}（{empirical_plan_days:.1f}日）",
            empirical_plan_ratio
        ]
    }
    
    # DataFrameのindexを使用して「項目」列を表現（手順⑥と同じ構造）
    comparison_df = pd.DataFrame(comparison_data, index=['ベース_安全在庫数量（日数）', '現行比（÷現行）'])
    
    # 列幅を統一するためのスタイル設定
    # インデックス列を18%に固定（「ベース_安全在庫数量（日数）」を表示するため）、データ列を残りの82%を4等分（各20.5%）
    st.markdown("""
    <style>
    /* テーブル全体のレイアウトを固定 */
    div[data-testid="stDataFrame"] table {
        table-layout: fixed !important;
        width: 100% !important;
    }
    /* インデックス列を18%に固定（長いテキストを表示するため） */
    div[data-testid="stDataFrame"] th:first-child,
    div[data-testid="stDataFrame"] td:first-child {
        width: 18% !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        line-height: 1.3 !important;
        padding: 8px 4px !important;
    }
    /* データ列（現行設定、安全在庫①、安全在庫②、安全在庫③）を完全に等幅に（各20.5%） */
    div[data-testid="stDataFrame"] th:not(:first-child),
    div[data-testid="stDataFrame"] td:not(:first-child) {
        width: 20.5% !important;
    }
    /* 長いヘッダーは改行で対応（列幅は固定のまま） */
    div[data-testid="stDataFrame"] th {
        white-space: normal !important;
        word-wrap: break-word !important;
        line-height: 1.2 !important;
        padding: 8px 4px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # インデックスを表示してテーブルを表示（手順⑥と同じ）
    st.dataframe(comparison_df, use_container_width=True)
    
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
    if current_value > 0:
        recommended_ratio = empirical_plan_value / current_value
        reduction_rate = (1 - recommended_ratio) * 100
        
        # 正負で表現を変更
        if recommended_ratio < 1:
            # 現行設定より小さい場合：削減
            effect_text = f"約 {round(abs(reduction_rate)):.0f}% の在庫削減が期待できます"
        else:
            # 現行設定より大きい場合：増加
            increase_rate = (recommended_ratio - 1) * 100
            effect_text = f"約 {round(increase_rate):.0f}% の在庫増加となります"
        
        st.markdown(f"""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>安全在庫③（推奨モデル）は現行比 {recommended_ratio:.2f} で、{effect_text}。</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>現行設定がないため、削減効果を計算できません。</div>
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
                
                # 異常値の判定式（上限値）
                info_data.append([
                    '異常値の判定式（上限値）',
                    f'mean + σ × {sigma_coef:.2f}',
                    f'平均と標準偏差から算出した上限値（mean + σ × {sigma_coef:.2f}）を超える上振れを検出します。'
                ])
                
                # 上限値を超えた件数（補正候補）
                info_data.append([
                    '上限値を超えた件数（補正候補）',
                    f'{candidate_count}件',
                    f'上限値（mean + σ × {sigma_coef:.2f}）を超えた実績の件数です。'
                ])
                
                # 補正した件数
                info_data.append([
                    '補正した件数',
                    f'{final_count}件',
                    f'上位 {top_cut_ratio:.2f}% の範囲に収まるよう、実際に補正した件数です。'
                ])
                
                # 上限値（初期）
                info_data.append([
                    '上限値（初期）',
                    f'{threshold_global:.2f}' if threshold_global else '—',
                    f'係数 {sigma_coef:.2f} を反映して算出した初期の上限値です。'
                ])
                
                # 上限値（最終）
                info_data.append([
                    '上限値（最終）',
                    f'{threshold_final:.2f}' if threshold_final else '—',
                    f'上位 {top_cut_ratio:.2f}% を適用して確定した最終の上限値です。'
                ])
                
                # 補正対象の上位割合（%）
                info_data.append([
                    '補正対象の上位割合（%）',
                    f'{top_cut_ratio:.2f}%',
                    f'上振れ補正の対象とする上位 {top_cut_ratio:.2f}% です。'
                ])
                
                # 全観測日数（分母：ゼロ日含む）
                top_limit_denominator = processing_info.get('top_limit_denominator')
                top_limit_calculated_count = processing_info.get('top_limit_calculated_count')
                if top_limit_denominator is not None:
                    info_data.append([
                        '全観測日数（分母：ゼロ日含む）',
                        f'{top_limit_denominator}日',
                        f'上位 {top_cut_ratio:.2f}% の計算に使用する全観測日数です。'
                    ])
                    if top_limit_calculated_count is not None:
                        info_data.append([
                            '補正対象の上限件数',
                            f'{top_limit_calculated_count}件',
                            f'全観測日数 × {top_cut_ratio:.2f}% で算出した補正件数の上限です。'
                        ])
            
            if info_data:
                # HTMLテーブルで表示（列幅を確実に制御するため）
                st.markdown("""
                <style>
                .outlier-info-table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 0.5rem 0;
                    font-size: 14px;
                    table-layout: fixed;
                }
                .outlier-info-table th {
                    background-color: #f0f2f6;
                    color: #262730;
                    font-weight: normal;
                    text-align: left;
                    padding: 10px 12px;
                    border: 1px solid #e0e0e0;
                    white-space: normal;
                    word-wrap: break-word;
                }
                .outlier-info-table td {
                    padding: 10px 12px;
                    border: 1px solid #e0e0e0;
                    white-space: normal;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    word-break: break-word;
                }
                /* 項目列：20% */
                .outlier-info-table th:nth-child(1),
                .outlier-info-table td:nth-child(1) {
                    width: 20%;
                    min-width: 120px;
                }
                /* 値列：20%（最小限） */
                .outlier-info-table th:nth-child(2),
                .outlier-info-table td:nth-child(2) {
                    width: 20%;
                    min-width: 120px;
                    text-align: left;
                }
                /* 処理内容の説明列：70%（最大限） */
                .outlier-info-table th:nth-child(3),
                .outlier-info-table td:nth-child(3) {
                    width: 60%;
                    white-space: normal;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # HTMLテーブルを構築
                html_table = '<table class="outlier-info-table"><thead><tr>'
                html_table += '<th>確認ポイント</th><th>結果</th><th>説明</th>'
                html_table += '</tr></thead><tbody>'
                
                for row in info_data:
                    html_table += '<tr>'
                    for col in row:
                        # HTMLエスケープ処理
                        value = str(col)
                        value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        html_table += f'<td>{value}</td>'
                    html_table += '</tr>'
                
                html_table += '</tbody></table>'
                st.markdown(html_table, unsafe_allow_html=True)


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
    
    # 平均需要を取得（安全在庫日数に変換するため）
    # 比較の一貫性を保つため、処理前のデータの平均を基準として使用する
    before_mean_demand = before_calculator.actual_data.mean() if before_calculator and hasattr(before_calculator, 'actual_data') else 1.0
    after_mean_demand = after_calculator.actual_data.mean() if after_calculator and hasattr(after_calculator, 'actual_data') else 1.0
    
    # ゼロ除算を防ぐ
    if before_mean_demand <= 0:
        before_mean_demand = 1.0
    if after_mean_demand <= 0:
        after_mean_demand = 1.0
    
    # 現行安全在庫（日数）を取得
    current_days = before_results['current_safety_stock']['safety_stock_days']
    current_value = before_results['current_safety_stock']['safety_stock']
    
    # 安全在庫数量を安全在庫日数に変換
    # 比較の一貫性を保つため、処理前のデータの平均を基準として使用する
    before_ss1_days = before_results['model1_theoretical']['safety_stock'] / before_mean_demand if before_results['model1_theoretical']['safety_stock'] is not None else None
    before_ss2_days = before_results['model2_empirical_actual']['safety_stock'] / before_mean_demand
    before_ss3_days = before_results['model3_empirical_plan']['safety_stock'] / before_mean_demand
    
    # 処理後の安全在庫も、処理前のデータの平均で日数換算する（比較の一貫性のため）
    after_ss1_days = after_results['model1_theoretical']['safety_stock'] / before_mean_demand if after_results['model1_theoretical']['safety_stock'] is not None else None
    after_ss2_days = after_results['model2_empirical_actual']['safety_stock'] / before_mean_demand
    after_ss3_days = after_results['model3_empirical_plan']['safety_stock'] / before_mean_demand
    
    # 安全在庫①が未定義かどうか
    is_before_ss1_undefined = before_results['model1_theoretical'].get('is_undefined', False) or before_results['model1_theoretical']['safety_stock'] is None
    is_after_ss1_undefined = after_results['model1_theoretical'].get('is_undefined', False) or after_results['model1_theoretical']['safety_stock'] is None
    
    # 1. Before/After比較棒グラフを表示
    # グラフとテーブルの位置を同期させるため、st.columnsでレイアウトを調整
    # テーブルの「項目」列の幅（12%）分だけ右にずらす
    col_left, col_graph = st.columns([0.12, 0.88])
    with col_left:
        st.empty()  # 左側に空のスペースを確保（テーブルの「項目」列に対応）
    with col_graph:
        # 数量データを取得
        before_ss1_value = before_results['model1_theoretical']['safety_stock'] if not is_before_ss1_undefined else None
        before_ss2_value = before_results['model2_empirical_actual']['safety_stock']
        before_ss3_value = before_results['model3_empirical_plan']['safety_stock']
        after_ss1_value = after_results['model1_theoretical']['safety_stock'] if not is_after_ss1_undefined else None
        after_ss2_value = after_results['model2_empirical_actual']['safety_stock']
        after_ss3_value = after_results['model3_empirical_plan']['safety_stock']
        
        fig = create_before_after_comparison_bar_chart(
            product_code=product_code,
            current_days=current_days,
            before_ss1_days=before_ss1_days,
            before_ss2_days=before_ss2_days,
            before_ss3_days=before_ss3_days,
            after_ss1_days=after_ss1_days,
            after_ss2_days=after_ss2_days,
            after_ss3_days=after_ss3_days,
            is_before_ss1_undefined=is_before_ss1_undefined,
            is_after_ss1_undefined=is_after_ss1_undefined,
            mean_demand=before_mean_demand,  # 比較の一貫性のため、処理前のデータの平均を使用
            current_value=current_value,
            before_ss1_value=before_ss1_value,
            before_ss2_value=before_ss2_value,
            before_ss3_value=before_ss3_value,
            after_ss1_value=after_ss1_value,
            after_ss2_value=after_ss2_value,
            after_ss3_value=after_ss3_value
        )
        st.plotly_chart(fig, use_container_width=True, key=f"after_processing_comparison_detail_{product_code}")
    
    # 2. 比較テーブル + 現行比表示
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
    for i, (qty, days) in enumerate(zip(before_quantities, [before_ss1_days, before_ss2_days, before_ss3_days])):
        if i == 0 and (is_before_ss1_undefined or qty is None or days is None or days == 0.0):
            before_display.append("—")
        else:
            before_display.append(f"{qty:.2f}（{days:.1f}日）" if days is not None else "—")
    
    # 処理後の安全在庫数量（日数）を表示形式で作成
    # 処理前と同じ値の場合は「同上」と表示
    after_display = []
    for i, (qty, days) in enumerate(zip(after_quantities, [after_ss1_days, after_ss2_days, after_ss3_days])):
        if i == 0 and (is_after_ss1_undefined or qty is None or days is None or days == 0.0):
            after_display.append("—")
        else:
            # 処理前の値と比較
            before_qty = before_quantities[i]
            before_days_val = [before_ss1_days, before_ss2_days, before_ss3_days][i]
            
            # 処理前が「—」の場合は比較しない
            if i == 0 and (is_before_ss1_undefined or before_qty is None or before_days_val is None or before_days_val == 0.0):
                after_display.append(f"{qty:.2f}（{days:.1f}日）" if days is not None else "—")
            # 処理前と処理後の値が同じ場合は「同上」と表示
            elif before_qty is not None and qty is not None and before_days_val is not None and days is not None:
                if abs(before_qty - qty) < 0.01 and abs(before_days_val - days) < 0.01:
                    after_display.append("同上")
                else:
                    after_display.append(f"{qty:.2f}（{days:.1f}日）")
            else:
                after_display.append(f"{qty:.2f}（{days:.1f}日）" if days is not None else "—")
    
    # 現行比を計算（処理後_安全在庫（日数） ÷ 現行安全在庫（日数））
    # 1.00ベースの数値表示にする
    current_ratios = []
    for i, v in enumerate([after_ss1_days, after_ss2_days, after_ss3_days]):
        if i == 0 and (is_after_ss1_undefined or v is None or v == 0.0):
            current_ratios.append("—")
        elif current_days > 0 and v is not None:
            ratio = v / current_days
            current_ratios.append(f"{ratio:.2f}")
        else:
            current_ratios.append("—")
    
    # 現行安全在庫の表示形式を作成
    # 処理前と処理後は常に同じ値なので「同上」と表示
    current_display_before = f"{current_value:.2f}（{current_days:.1f}日）"
    current_display_after = "同上"
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
        '現行設定': [
            current_display_before,
            current_display_after,
            current_ratio_display
        ],
        '安全在庫①': [
            before_display[0],
            after_display[0],
            current_ratios[0]
        ],
        '安全在庫②': [
            before_display[1],
            after_display[1],
            current_ratios[1]
        ],
        '安全在庫③': [
            before_display[2],
            after_display[2],
            current_ratios[2]
        ]
    }
    
    comparison_df = pd.DataFrame(comparison_data, index=['処理前_安全在庫数量（日数）', '処理後_安全在庫数量（日数）', '現行比（処理後 ÷ 現行）'])
    st.dataframe(comparison_df, use_container_width=True)
    
    # 3. テキストボックス型注釈を表示
    if current_days <= 0:
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>現行設定がないため、削減効果を計算できません。</div>
        </div>
        """, unsafe_allow_html=True)
    elif after_ss3_days is not None:
        recommended_ratio = after_ss3_days / current_days
        
        # 異常値が検出されたかどうかを判定
        processing_info = st.session_state.get('step2_processing_info', {})
        is_skipped = processing_info.get('skipped', False)
        candidate_count = processing_info.get('candidate_count', 0)
        outlier_detected = not is_skipped and candidate_count > 0
        
        # 安全在庫③への影響の有無を判定（処理前後の値を比較）
        before_ss3_value = before_results['model3_empirical_plan']['safety_stock']
        after_ss3_value = after_results['model3_empirical_plan']['safety_stock']
        ss3_changed = before_ss3_value is not None and after_ss3_value is not None and abs(before_ss3_value - after_ss3_value) >= 0.01
        
        # 異常値が検出されなかった場合、かつ安全在庫③に変更がない場合
        if not outlier_detected and not ss3_changed:
            # Aパターン：現行設定 ＞ 安全在庫③（推奨モデル）、Bパターン：現行設定 ＜ 安全在庫③（推奨モデル）
            if recommended_ratio < 1:
                # Aパターン：削減効果を追加
                reduction_rate = (1 - recommended_ratio) * 100
                effect_text = f"約 {round(reduction_rate):.0f}% の在庫削減効果が期待できます。"
            else:
                # Bパターン：増加率を追加
                increase_rate = (recommended_ratio - 1) * 100
                effect_text = f"約 {round(increase_rate):.0f}% の在庫増加となります。"
            
            st.markdown(f"""
            <div class="annotation-success-box">
                <span class="icon">✅</span>
                <div class="text"><strong>在庫削減効果：</strong>異常値は検出されなかったため、安全在庫③（推奨モデル）の現行比 {recommended_ratio:.2f} に変更はありません。{effect_text}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # 異常値が検出された場合、または安全在庫③に変更があった場合
            reduction_rate = (1 - recommended_ratio) * 100
            
            # 正負で表現を変更
            if recommended_ratio < 1:
                # 現行設定より小さい場合：削減
                effect_text = f"約 {round(abs(reduction_rate)):.0f}% の在庫削減が期待できます"
            else:
                # 現行設定より大きい場合：増加
                increase_rate = (recommended_ratio - 1) * 100
                effect_text = f"約 {round(increase_rate):.0f}% の在庫増加となります"
            
            st.markdown(f"""
            <div class="annotation-success-box">
                <span class="icon">✅</span>
                <div class="text"><strong>在庫削減効果：</strong>安全在庫③（推奨モデル）は現行比 {recommended_ratio:.2f} で、{effect_text}。</div>
            </div>
            """, unsafe_allow_html=True)


def display_after_cap_comparison(product_code: str,
                                 before_results: dict,
                                 after_results: dict,
                                 before_calculator: SafetyStockCalculator,
                                 after_calculator: SafetyStockCalculator,
                                 cap_applied: bool = True,
                                 adopted_model_days: Optional[float] = None):
    """上限カット適用前後の安全在庫比較結果を表示
    
    Args:
        product_code: 商品コード
        before_results: 上限カット適用前の結果
        after_results: 上限カット適用後の結果
        before_calculator: 上限カット適用前の計算機
        after_calculator: 上限カット適用後の計算機
        cap_applied: 上限カットが適用されたかどうか（Falseの場合は「同左」を表示）
        adopted_model_days: 採用モデルの安全在庫日数
    """
    
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
    before_ss1_days = before_results['model1_theoretical']['safety_stock'] / before_mean_demand if (before_results['model1_theoretical']['safety_stock'] is not None and before_mean_demand > 0) else None
    before_ss2_days = before_results['model2_empirical_actual']['safety_stock'] / before_mean_demand if before_mean_demand > 0 else 0
    before_ss3_days = before_results['model3_empirical_plan']['safety_stock'] / before_mean_demand if before_mean_demand > 0 else 0
    
    # 処理後の安全在庫数量を取得
    # 比較の一貫性を保つため、処理前のデータの平均を基準として使用する
    after_ss1_days = after_results['model1_theoretical']['safety_stock'] / before_mean_demand if (after_results['model1_theoretical']['safety_stock'] is not None and before_mean_demand > 0) else None
    after_ss2_days = after_results['model2_empirical_actual']['safety_stock'] / before_mean_demand if before_mean_demand > 0 else 0
    after_ss3_days = after_results['model3_empirical_plan']['safety_stock'] / before_mean_demand if before_mean_demand > 0 else 0
    
    # 採用モデルを取得（手順⑦で決定されたモデル）
    adopted_model = st.session_state.get('step2_adopted_model', 'ss3')  # デフォルトはss3
    
    # カット前の採用モデルの日数を計算
    if adopted_model == "ss2":
        before_adopted_model_days = before_ss2_days
    else:  # ss3
        before_adopted_model_days = before_ss3_days
    
    # カット後の採用モデルの日数を計算
    if adopted_model == "ss2":
        after_adopted_model_days = after_ss2_days
    else:  # ss3
        after_adopted_model_days = after_ss3_days
    
    # 採用モデルの日数（デフォルトはカット後の値）
    if adopted_model_days is None:
        adopted_model_days = after_adopted_model_days
    
    # 上限カット日数を取得
    cap_days = None
    if before_calculator and before_calculator.abc_category:
        abc_category = before_calculator.abc_category.upper()
        category_cap_days = st.session_state.get('category_cap_days', {})
        cap_days = category_cap_days.get(abc_category)
    
    # 1. 棒グラフを表示（手順⑦と同じレイアウト）
    # グラフとテーブルの位置を同期させるため、st.columnsでレイアウトを調整
    # 上の5本の棒グラフ（「現行設定」「安全在庫①」「安全在庫②」「安全在庫③」「採用モデル」）と
    # 下の表の5列を視覚的に揃えるため、左グラフ（4本）と右グラフ（1本）の幅の比率を4:1に近づける
    col_left_space, col_graphs = st.columns([0.12, 0.88])
    with col_left_space:
        st.empty()  # 左側に空のスペースを確保（テーブルのインデックス列に対応）
    with col_graphs:
        # グラフ間の距離を縮める（中央の矢印用カラムを細くして左右のグラフを中央へ寄せる）
        # 左グラフ4本と右グラフ1本の比率を考慮して、左:矢印:右 = 4:0.2:1 の比率で配置
        # 左側のグラフを7mm広げ、右側のグラフを7mm狭くする
        col_left, col_arrow, col_right = st.columns([3.8, 0.2, 1.0])
        
        with col_left:
            # 左側グラフ：候補モデル比較
            # カット前の採用モデルの日数を計算
            if adopted_model == "ss2":
                before_adopted_model_days = before_ss2_days
            else:  # ss3
                before_adopted_model_days = before_ss3_days
            
            # カット後の採用モデルの日数を計算
            if adopted_model == "ss2":
                after_adopted_model_days = after_ss2_days
            else:  # ss3
                after_adopted_model_days = after_ss3_days
            
            fig_left, fig_right = create_cap_adopted_model_comparison_charts(
                product_code=product_code,
                current_days=current_days,
                before_ss1_days=before_ss1_days,
                before_ss2_days=before_ss2_days,
                before_ss3_days=before_ss3_days,
                after_ss1_days=after_ss1_days,
                after_ss2_days=after_ss2_days,
                after_ss3_days=after_ss3_days,
                adopted_model=adopted_model,
                adopted_model_days=after_adopted_model_days,  # カット後の値を渡す
                cap_days=cap_days,
                is_before_ss1_undefined=is_before_ss1_undefined,
                is_after_ss1_undefined=is_after_ss1_undefined
            )
            st.plotly_chart(fig_left, use_container_width=True, key=f"cap_adopted_model_left_{product_code}")
        
        with col_arrow:
            # 中央の矢印を縦に3つ並べて強調表示
            st.markdown("""
            <div style='text-align: center; margin-top: 180px;'>
                <div style='font-size: 48px; font-weight: bold; color: #333333; line-height: 1.2;'>➡</div>
                <div style='font-size: 48px; font-weight: bold; color: #333333; line-height: 1.2;'>➡</div>
                <div style='font-size: 48px; font-weight: bold; color: #333333; line-height: 1.2;'>➡</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_right:
            # 右側グラフ：採用モデル専用
            st.plotly_chart(fig_right, use_container_width=True, key=f"cap_adopted_model_right_{product_code}")
    
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
    for i, (qty, days) in enumerate(zip(before_quantities, [before_ss1_days, before_ss2_days, before_ss3_days])):
        if i == 0 and (is_before_ss1_undefined or qty is None or days is None or days == 0.0):
            before_display.append("—")
        else:
            before_display.append(f"{qty:.2f}（{days:.1f}日）" if days is not None else "—")
    
    # 処理後の安全在庫数量（日数）を表示形式で作成
    after_display = []
    if not cap_applied:
        # 上限カットが適用されなかった場合、「同上」を表示
        for i in range(len(after_quantities)):
            after_display.append("同上")
    else:
        # 上限カットが適用された場合、カット前と同じ場合は「同上」、異なる場合は通常通り表示
        for i, (qty, days, before_qty, before_day) in enumerate(zip(
            after_quantities, 
            [after_ss1_days, after_ss2_days, after_ss3_days],
            before_quantities,
            [before_ss1_days, before_ss2_days, before_ss3_days]
        )):
            if i == 0 and (is_after_ss1_undefined or qty is None or days is None or days == 0.0):
                after_display.append("—")
            else:
                # カット前とカット後が同じ場合は「同上」を表示
                if days is not None and before_day is not None and abs(days - before_day) < 0.01:
                    after_display.append("同上")
                else:
                    after_display.append(f"{qty:.2f}（{days:.1f}日）" if days is not None else "—")
    
    # 現行比を計算（カット後_安全在庫（日数） ÷ 現行安全在庫（日数））
    current_ratios = []
    target_days_list = [after_ss1_days, after_ss2_days, after_ss3_days] if cap_applied else [before_ss1_days, before_ss2_days, before_ss3_days]
    for i, v in enumerate(target_days_list):
        # 演算子優先順位を修正：i == 0 のときのみ undefined/None/0.0 をチェック
        if i == 0 and ((is_after_ss1_undefined if cap_applied else is_before_ss1_undefined) or v is None or v == 0.0):
            current_ratios.append("—")
        elif current_days > 0 and v is not None:
            ratio = v / current_days
            current_ratios.append(f"{ratio:.2f}")
        else:
            current_ratios.append("—")
    
    # 現行安全在庫の表示形式を作成
    current_display_before = f"{current_value:.2f}（{current_days:.1f}日）"
    current_display_after = "同上"  # カット前と同じなので「同上」
    current_ratio_display = "1.00"
    
    # 2. テーブルを表示
    comparison_data = {
        '現行設定': [
            current_display_before,
            current_display_after,
            current_ratio_display
        ],
        '安全在庫①': [
            before_display[0],
            after_display[0],
            current_ratios[0]
        ],
        '安全在庫②': [
            before_display[1],
            after_display[1],
            current_ratios[1]
        ],
        '安全在庫③': [
            before_display[2],
            after_display[2],
            current_ratios[2]
        ],
        '採用モデル': [
            f"{adopted_model_days * before_mean_demand:.2f}（{adopted_model_days:.1f}日）" if adopted_model_days is not None else "—",
            "同上",  # 採用モデルはカット前後で同じなので「同上」
            f"{adopted_model_days / current_days:.2f}" if (adopted_model_days is not None and current_days > 0) else "—"
        ]
    }
    
    comparison_df = pd.DataFrame(comparison_data, index=['カット前_安全在庫数量（日数）', 'カット後_安全在庫数量（日数）', '現行比（カット後 ÷ 現行）'])
    
    # 採用モデル列をハイライト（手順⑦と同じ色を使用）
    # 安全在庫③の色系統（rgba(100, 200, 150, 0.8)）に基づいた薄い緑
    adopted_model_bg_color = '#B4E6D1'  # 手順⑦と同じ色
    
    # 列名で採用モデル列を特定
    styled_df = comparison_df.style.applymap(
        lambda x: f'background-color: {adopted_model_bg_color}; font-weight: bold;' if isinstance(x, str) and x != '' else '',
        subset=['採用モデル']
    )
    # 行ラベルが切れないように、CSSで調整
    st.markdown("""
    <style>
    .stDataFrame {
        width: 100%;
    }
    .stDataFrame table {
        table-layout: auto;
    }
    .stDataFrame th:first-child,
    .stDataFrame td:first-child {
        min-width: 250px !important;
        white-space: nowrap !important;
        max-width: none !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.dataframe(styled_df, use_container_width=True)
    
    # 3. テキストボックス型注釈を表示（4パターン動的表示）
    # 採用モデルのみを基準として判定
    if current_days <= 0:
        st.markdown("""
        <div class="annotation-success-box">
            <span class="icon">✅</span>
            <div class="text"><strong>在庫削減効果：</strong>現行設定がないため、削減効果を計算できません。</div>
        </div>
        """, unsafe_allow_html=True)
    elif adopted_model_days is not None and before_adopted_model_days is not None and after_adopted_model_days is not None:
        # 採用モデルに上限カットが適用されたかどうかを判定（BeforeとAfterを比較）
        # 値が異なれば上限カットが適用されたと判定（0.01日以上の差があれば適用とみなす）
        cap_applied_to_adopted_model = abs(before_adopted_model_days - after_adopted_model_days) >= 0.01
        
        # 現行比を計算（カット後の採用モデル日数 ÷ 現行設定日数）
        current_ratio = after_adopted_model_days / current_days if current_days > 0 else 0
        
        # 増減率を計算（現行設定日数とカット後の採用モデル日数の差）
        change_days = after_adopted_model_days - current_days
        change_rate = abs(change_days / current_days * 100) if current_days > 0 else 0
        change_rate_rounded = round(change_rate)  # 四捨五入して整数表示
        
        # 4パターンに分岐
        if cap_applied_to_adopted_model:
            # 上限カット適用
            if change_days < 0:
                # (1) 上限カット適用 ＆ 削減
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>在庫削減効果：</strong>採用モデルに上限カットを適用しました。現行比 {current_ratio:.2f} となり、約 {change_rate_rounded}% の在庫削減が期待できます。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # (2) 上限カット適用 ＆ 増加
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>在庫削減効果：</strong>採用モデルに上限カットを適用しました。現行比 {current_ratio:.2f} となり、約 {change_rate_rounded}% の在庫増加となります。</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            # 上限カット未適用
            if change_days < 0:
                # (3) 上限カット未適用 ＆ 削減
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>在庫削減効果：</strong>採用モデルに上限カットが適用されなかったため、現行比 {current_ratio:.2f} に変更はありません。約 {change_rate_rounded}% の在庫削減効果が期待できます。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # (4) 上限カット未適用 ＆ 増加
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>在庫削減効果：</strong>採用モデルに上限カットが適用されなかったため、現行比 {current_ratio:.2f} に変更はありません。約 {change_rate_rounded}% の在庫増加となります。</div>
                </div>
                """, unsafe_allow_html=True)

