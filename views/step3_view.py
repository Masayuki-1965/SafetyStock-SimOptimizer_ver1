"""
STEP3 ビュー
安全在庫算出と登録データ作成（全機種）のUI
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from modules.data_loader import DataLoader
from modules.safety_stock_models import SafetyStockCalculator
from modules.outlier_handler import OutlierHandler
from utils.common import (
    slider_with_number_input,
    classify_inventory_days_bin,
    get_abc_analysis_with_fallback
)
from charts.safety_stock_charts import (
    create_order_volume_comparison_chart_before,
    create_order_volume_comparison_chart_after
)

# 標準偏差の計算方法（固定）
STD_METHOD_FIXED = "population"  # 母分散（推奨）を固定使用


def display_step3():
    """STEP3のUIを表示"""
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
    analysis_result, abc_categories_from_analysis, abc_warning = get_abc_analysis_with_fallback(
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
    
    # ========== 手順①：算出条件を設定する ==========
    st.markdown("""
    <div class="step-middle-section">
        <p>手順①：算出条件を設定する</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="step-description">全機種の安全在庫算出に必要な条件（リードタイム、欠品許容率、標準偏差の計算方法）を設定します。<br>これらの設定値は、後続の手順で使用される安全在庫モデルの算出に影響します。</div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown('<div class="step-sub-section">リードタイムの設定</div>', unsafe_allow_html=True)
    lead_time_type = st.radio(
        "リードタイムの種別",
        options=["working_days", "calendar"],
        format_func=lambda x: "稼働日数" if x == "working_days" else "カレンダー日数",
        help="稼働日数：土日祝除く、カレンダー日数：土日祝含む",
        horizontal=True,
        key="shared_lead_time_type"
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
    
    # 標準偏差の計算式
    st.markdown('<div class="step-sub-section">標準偏差の計算式</div>', unsafe_allow_html=True)
    st.caption("💡 標準偏差は、日次実績データをもとに　√Σ（値 − 平均値）² ÷ データ数 で算出します。安全在庫①（理論値）のみに適用されます。")
    std_method = STD_METHOD_FIXED
    st.session_state.shared_std_method = STD_METHOD_FIXED
    
    st.divider()
    
    # ========== 手順②：安全在庫を算出する ==========
    st.markdown("""
    <div class="step-middle-section">
        <p>手順②：安全在庫を算出する</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="step-description">全機種を対象に、設定した算出条件に基づいて3種類の安全在庫モデルを算出します。<br>算出結果はサマリーテーブルとグラフで確認でき、現行設定との比較により全体傾向を把握できます。</div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 実行ボタン
    if st.button("安全在庫を算出する", type="primary", use_container_width=True):
        # 全機種の安全在庫を算出
        all_results = []
        progress_bar = st.progress(0)
        total_products = len(product_list)
        
        for idx, product_code in enumerate(product_list):
            try:
                # データ取得
                plan_data = data_loader.get_daily_plan(product_code)
                actual_data = data_loader.get_daily_actual(product_code)
                working_dates = data_loader.get_working_dates()
                
                # ABC区分を取得
                abc_category = get_product_category(product_code)
                
                # 安全在庫計算（異常値処理前なので上限カットは適用しない）
                calculator = SafetyStockCalculator(
                    plan_data=plan_data,
                    actual_data=actual_data,
                    working_dates=working_dates,
                    lead_time=lead_time,
                    lead_time_type=lead_time_type,
                    stockout_tolerance_pct=stockout_tolerance,
                    std_calculation_method=std_method,
                    data_loader=data_loader,
                    product_code=product_code,
                    abc_category=abc_category,
                    category_cap_days={}  # 異常値処理前では上限カットを適用しない
                )
                
                results = calculator.calculate_all_models()
                
                # 結果を保存
                daily_actual_mean = calculator.actual_data.mean()
                # 安全在庫①がNoneの場合（p=0%など）の処理
                ss1_value = results['model1_theoretical']['safety_stock']
                is_ss1_undefined = results['model1_theoretical'].get('is_undefined', False) or ss1_value is None
                
                # 月当たり実績を取得（analysis_resultから）
                monthly_avg_actual = 0.0
                if 'monthly_avg_actual' in analysis_result.columns:
                    product_monthly = analysis_result[analysis_result['product_code'] == product_code]
                    if len(product_monthly) > 0:
                        monthly_avg_actual = product_monthly.iloc[0]['monthly_avg_actual']
                        if pd.isna(monthly_avg_actual):
                            monthly_avg_actual = 0.0
                
                result_row = {
                    '商品コード': product_code,
                    'ABC区分': format_abc_category_for_display(abc_category),
                    '月当たり実績': monthly_avg_actual,
                    '現行設定_数量': results['current_safety_stock']['safety_stock'],
                    '現行設定_日数': results['current_safety_stock']['safety_stock_days'],
                    '安全在庫①_数量': ss1_value,
                    '安全在庫②_数量': results['model2_empirical_actual']['safety_stock'],
                    '安全在庫③_数量': results['model3_empirical_plan']['safety_stock'],
                    '安全在庫①_日数': (ss1_value / daily_actual_mean if (daily_actual_mean > 0 and not is_ss1_undefined and ss1_value is not None) else 0),
                    '安全在庫②_日数': results['model2_empirical_actual']['safety_stock'] / daily_actual_mean if daily_actual_mean > 0 else 0,
                    '安全在庫③_日数': results['model3_empirical_plan']['safety_stock'] / daily_actual_mean if daily_actual_mean > 0 else 0,
                    '日当たり実績': daily_actual_mean,
                    '欠品許容率': stockout_tolerance  # 欠品許容率を保存
                }
                all_results.append(result_row)
                
            except Exception as e:
                st.warning(f"{product_code} の計算でエラーが発生しました: {str(e)}")
                continue
            
            progress_bar.progress((idx + 1) / total_products)
        
        progress_bar.empty()
        
        # 結果をDataFrameに変換
        if all_results:
            results_df = pd.DataFrame(all_results)
            st.session_state.all_products_results = results_df
            st.markdown(f"""
            <div class="annotation-success-box">
                <span class="icon">✅</span>
                <div class="text"><strong>安全在庫算出完了：</strong>{len(all_results)}機種の安全在庫算出が完了しました。</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error("❌ 算出結果がありません。")
            return
    
    # サマリー表の表示
    if 'all_products_results' in st.session_state and st.session_state.all_products_results is not None:
        results_df = st.session_state.all_products_results.copy()
        
        st.markdown("""
        <div class="step-middle-section">
            <p>安全在庫算出結果（異常値処理前）サマリー</p>
        </div>
        """, unsafe_allow_html=True)
        
        # ABC区分ごとの安全在庫比較結果サマリー表
        if 'ABC区分' in results_df.columns:
            # ABC区分別_安全在庫比較マトリクスを表示
            st.markdown('<div class="step-sub-section">ABC区分別_安全在庫比較マトリクス</div>', unsafe_allow_html=True)
            display_abc_matrix_comparison(results_df, key_prefix="abc_matrix_before")
            
            # 受注量別 安全在庫比較グラフ（異常値処理前）を追加
            st.markdown("""
            <div class="step-middle-section">
                <p>受注量別 安全在庫 比較グラフ（異常値処理前）</p>
            </div>
            """, unsafe_allow_html=True)
            st.caption("安全在庫モデルを『現行設定』『安全在庫①』『安全在庫②』『安全在庫③』から選択してください。")
            
            # 安全在庫タイプ選択UI
            col1, col2 = st.columns([1, 3])
            with col1:
                safety_stock_type_before = st.selectbox(
                    "安全在庫モデル",
                    options=["current", "ss1", "ss2", "ss3"],
                    format_func=lambda x: {
                        "current": "現行設定",
                        "ss1": "安全在庫①",
                        "ss2": "安全在庫②",
                        "ss3": "安全在庫③"
                    }[x],
                    index=3,  # デフォルトは安全在庫③
                    key="safety_stock_type_before"
                )
            
            with col2:
                type_descriptions = {
                    "current": "<strong>現行設定</strong>：現行設定している安全在庫",
                    "ss1": "<strong>安全在庫①</strong>：理論値【理論モデル】",
                    "ss2": "<strong>安全在庫②</strong>：実測値（実績 − 平均）【実績の変動に基づくモデル】",
                    "ss3": "<strong>安全在庫③</strong>：実測値（実績 − 計画）【計画誤差を考慮した推奨モデル】"
                }
                st.markdown(f'<div style="color: #555555; margin-top: 28px; line-height: 38px; display: flex; align-items: center;">{type_descriptions[safety_stock_type_before]}</div>', unsafe_allow_html=True)
            
            # 全データから最大値を計算（軸スケール統一用）
            all_quantity_cols = ['現行設定_数量', '安全在庫①_数量', '安全在庫②_数量', '安全在庫③_数量']
            all_days_cols = ['現行設定_日数', '安全在庫①_日数', '安全在庫②_日数', '安全在庫③_日数']
            max_quantity = 0
            max_days = 0
            for col in all_quantity_cols:
                if col in results_df.columns:
                    valid_values = results_df[col].dropna()
                    if len(valid_values) > 0:
                        max_quantity = max(max_quantity, valid_values.max())
            for col in all_days_cols:
                if col in results_df.columns:
                    valid_values = results_df[col].dropna()
                    if len(valid_values) > 0:
                        max_days = max(max_days, valid_values.max())
            
            # デフォルト値を計算（1.1倍のマージン）
            default_y1_max = max_quantity * 1.1 if max_quantity > 0 else 100
            default_y2_max = max_days * 1.1 if max_days > 0 else 50
            
            # セッション状態の初期化
            if 'step3_before_y1_max' not in st.session_state:
                st.session_state.step3_before_y1_max = default_y1_max
            if 'step3_before_y2_max' not in st.session_state:
                st.session_state.step3_before_y2_max = default_y2_max
            
            fig = create_order_volume_comparison_chart_before(
                results_df, 
                safety_stock_type=safety_stock_type_before,
                y1_max=st.session_state.step3_before_y1_max,
                y2_max=st.session_state.step3_before_y2_max
            )
            if len(fig.data) > 0:
                st.plotly_chart(fig, use_container_width=True, key="order_volume_comparison_chart_before")
                
                # 縦軸最大値の入力欄を追加
                col_y1, col_y2 = st.columns(2)
                with col_y1:
                    y1_max_input = st.number_input(
                        "左縦軸「数量」最大値",
                        min_value=0.0,
                        value=float(st.session_state.step3_before_y1_max),
                        step=100.0,
                        key="step3_before_y1_max_input"
                    )
                    st.session_state.step3_before_y1_max = y1_max_input
                
                with col_y2:
                    y2_max_input = st.number_input(
                        "右縦軸「日数」最大値",
                        min_value=0.0,
                        value=float(st.session_state.step3_before_y2_max),
                        step=5.0,
                        key="step3_before_y2_max_input"
                    )
                    st.session_state.step3_before_y2_max = y2_max_input
            else:
                st.warning("グラフ表示に必要なデータがありません。")
        
        # 詳細テーブル（表示オプション）
        st.markdown('<div class="step-sub-section">詳細データ</div>', unsafe_allow_html=True)
        # 月当たり実績で降順ソート
        if '月当たり実績' in results_df.columns:
            results_df = results_df.sort_values('月当たり実績', ascending=False).reset_index(drop=True)
        # 列順を指定して並び替え（ABC区分の右隣に月当たり実績を配置）
        column_order = [
            '商品コード', 'ABC区分', '月当たり実績', '現行設定_数量', '現行設定_日数', '安全在庫①_数量', '安全在庫②_数量', '安全在庫③_数量',
            '安全在庫①_日数', '安全在庫②_日数', '安全在庫③_日数', '日当たり実績', '欠品許容率'
        ]
        # 存在する列のみを選択
        available_columns = [col for col in column_order if col in results_df.columns]
        results_df_display = results_df[available_columns]
        # 横スクロールを有効化（use_container_width=Trueで自動的に横スクロール可能）
        st.dataframe(results_df_display, use_container_width=True, hide_index=True)
        
        # CSVエクスポート（列順を指定）
        # Plotly標準の"Download as CSV"があるため、独自のダウンロードボタンは廃止
        
        # ========== 手順③：異常値処理と上限カットを実施する ==========
        st.divider()
        st.markdown("""
        <div class="step-middle-section">
            <p>手順③：異常値処理と上限カットを実施する</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">全機種に異常値処理を適用し、ABC区分に応じた上限日数を設定して最終安全在庫を確定します。<br>需要データに含まれる統計的な上振れ異常値を検出・補正することで、安全在庫が過大に算定されるのを防ぎます。</div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 異常値処理のパラメータ設定
        st.markdown('<div class="step-sub-section">異常値処理のパラメータ設定</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            sigma_k = st.number_input(
                "σ係数（グローバル異常基準）",
                min_value=1.0,
                max_value=10.0,
                value=6.0,
                step=0.5,
                help="6σを超えるような極端なスパイクだけを「異常値」として扱います。",
                key="step3_sigma_k"
            )
        
        with col2:
            top_limit_mode = st.radio(
                "上位制限方式",
                options=['percent', 'count'],
                format_func=lambda x: "割合（％）" if x == 'percent' else "件数（N）",
                index=0,
                key="step3_top_limit_mode",
                horizontal=True
            )
        
        if top_limit_mode == 'count':
            top_limit_n = st.number_input(
                "上位カット件数（N）",
                min_value=1,
                max_value=100,
                value=2,
                step=1,
                help="上位N件を異常値として補正します。",
                key="step3_top_limit_n"
            )
            top_limit_p = None
        else:
            top_limit_p = st.number_input(
                "上位カット割合（％）",
                min_value=1.0,
                max_value=5.0,
                value=2.0,
                step=0.1,
                help="全期間のうち上位p%のスパイクだけを補正対象とします。",
                key="step3_top_limit_p"
            )
            top_limit_n = None
        
        # ABC区分ごとの上限日数設定
        st.markdown('<div class="step-sub-section">ABC区分ごとの上限日数設定</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">この上限日数は、異常値処理後に適用されます。</div>
        """, unsafe_allow_html=True)
        
        # analysis_resultから実際に存在する全ての区分を取得（「未分類」も含む）
        all_categories_in_data = analysis_result['abc_category'].apply(format_abc_category_for_display).unique().tolist()
        abc_categories = sorted([cat for cat in all_categories_in_data if str(cat).strip() != ""])
        
        if not abc_categories:
            abc_categories = ['A', 'B', 'C']
        
        # セッション状態の初期化（デフォルト値40日）
        if 'category_cap_days' not in st.session_state:
            st.session_state.category_cap_days = {cat: 40 for cat in abc_categories}
        else:
            # 新しい区分が追加された場合、デフォルト値40日を設定
            for cat in abc_categories:
                if cat not in st.session_state.category_cap_days:
                    st.session_state.category_cap_days[cat] = 40
        
        category_cap_days = {}
        
        # 区分ごとに上限日数を設定（3列レイアウト）
        num_cols = 3
        for i, cat in enumerate(abc_categories):
            col_idx = i % num_cols
            if col_idx == 0:
                cols = st.columns(num_cols)
            
            with cols[col_idx]:
                current_value = st.session_state.category_cap_days.get(cat, 40)
                cap_days = st.number_input(
                    f"{cat}区分の上限日数",
                    min_value=1,
                    max_value=365,
                    value=current_value,
                    step=1,
                    key=f"step3_cap_days_{cat}"
                )
                category_cap_days[cat] = cap_days
                st.session_state.category_cap_days[cat] = cap_days
        
        # セッション状態に保存
        st.session_state.category_cap_days = category_cap_days
        
        # 異常値処理と最終安全在庫の確定ボタン
        if st.button("異常値処理と上限カットを実施する", type="primary", use_container_width=True):
            # ②で算出した結果が存在するか確認
            if 'all_products_results' not in st.session_state or st.session_state.all_products_results is None:
                st.error("❌ 先に「② 全機種_安全在庫を算出する」を実行してください。")
                return
            
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
            
            # ②で算出した結果を取得
            before_results_df = st.session_state.all_products_results.copy()
            
            # パラメータを取得
            lead_time = st.session_state.get("shared_lead_time", 45)
            lead_time_type = st.session_state.get("shared_lead_time_type", "working_days")
            stockout_tolerance = st.session_state.get("shared_stockout_tolerance", 1.0)
            std_method = st.session_state.get("shared_std_method", STD_METHOD_FIXED)
            
            # 全機種に異常値処理を適用して最終安全在庫を算出
            final_results = []
            progress_bar = st.progress(0)
            total_products = len(product_list)
            
            for idx, product_code in enumerate(product_list):
                try:
                    # データ取得
                    plan_data = data_loader.get_daily_plan(product_code)
                    actual_data = data_loader.get_daily_actual(product_code)
                    working_dates = data_loader.get_working_dates()
                    
                    # ABC区分を取得
                    abc_category = None
                    abc_category = get_product_category(product_code)
                    
                    # 異常値処理を適用
                    outlier_handler = OutlierHandler(
                        actual_data=actual_data,
                        working_dates=working_dates,
                        sigma_k=sigma_k,
                        top_limit_mode=top_limit_mode,
                        top_limit_n=top_limit_n if top_limit_mode == 'count' else 2,
                        top_limit_p=top_limit_p if top_limit_mode == 'percent' else 2.0,
                        abc_category=abc_category
                    )
                    
                    processing_result = outlier_handler.detect_and_correct()
                    corrected_data = processing_result['corrected_data']
                    
                    # 異常値処理後のデータで安全在庫を再算出
                    calculator = SafetyStockCalculator(
                        plan_data=plan_data,
                        actual_data=corrected_data,
                        working_dates=working_dates,
                        lead_time=lead_time,
                        lead_time_type=lead_time_type,
                        stockout_tolerance_pct=stockout_tolerance,
                        std_calculation_method=std_method,
                        data_loader=data_loader,
                        product_code=product_code,
                        abc_category=abc_category,
                        category_cap_days={},  # ここでは上限カットは適用しない（後で適用）
                        original_actual_data=actual_data  # 異常値処理前のデータを保存
                    )
                    
                    results = calculator.calculate_all_models()
                    
                    # 日当たり実績平均を計算
                    daily_actual_mean = corrected_data.mean()
                    
                    # ABC区分に応じた上限日数を適用（安全在庫①・②・③すべてに適用）
                    def apply_cap_days(safety_stock_value, daily_mean, category):
                        """上限日数を適用して安全在庫をクリップ"""
                        if daily_mean > 0 and category:
                            cap_days = category_cap_days.get(category.upper())
                            if cap_days is not None:
                                max_stock = daily_mean * cap_days
                                return min(safety_stock_value, max_stock)
                        return safety_stock_value
                    
                    # 安全在庫①（理論値）
                    ss1_value = results['model1_theoretical']['safety_stock']
                    is_ss1_undefined = results['model1_theoretical'].get('is_undefined', False) or ss1_value is None
                    if not is_ss1_undefined and ss1_value is not None:
                        final_ss1_quantity = apply_cap_days(ss1_value, daily_actual_mean, abc_category)
                    else:
                        final_ss1_quantity = None
                    final_ss1_days = final_ss1_quantity / daily_actual_mean if (daily_actual_mean > 0 and final_ss1_quantity is not None) else 0
                    
                    # 安全在庫②（実績−平均）
                    ss2_value = results['model2_empirical_actual']['safety_stock']
                    final_ss2_quantity = apply_cap_days(ss2_value, daily_actual_mean, abc_category)
                    final_ss2_days = final_ss2_quantity / daily_actual_mean if daily_actual_mean > 0 else 0
                    
                    # 安全在庫③（実績−計画）
                    ss3_value = results['model3_empirical_plan']['safety_stock']
                    final_ss3_quantity = apply_cap_days(ss3_value, daily_actual_mean, abc_category)
                    final_ss3_days = final_ss3_quantity / daily_actual_mean if daily_actual_mean > 0 else 0
                    
                    # ②の結果から現行設定と安全在庫①②③（異常値処理前）を取得
                    before_row = before_results_df[before_results_df['商品コード'] == product_code]
                    if len(before_row) > 0:
                        current_qty = before_row.iloc[0]['現行設定_数量']
                        current_days = before_row.iloc[0]['現行設定_日数']
                        ss1_qty = before_row.iloc[0]['安全在庫①_数量']
                        ss1_days = before_row.iloc[0]['安全在庫①_日数']
                        ss2_qty = before_row.iloc[0]['安全在庫②_数量']
                        ss2_days = before_row.iloc[0]['安全在庫②_日数']
                        ss3_before_qty = before_row.iloc[0]['安全在庫③_数量']
                        ss3_before_days = before_row.iloc[0]['安全在庫③_日数']
                    else:
                        current_qty = 0
                        current_days = 0
                        ss1_qty = None
                        ss1_days = 0
                        ss2_qty = 0
                        ss2_days = 0
                        ss3_before_qty = 0
                        ss3_before_days = 0
                    
                    # 月当たり実績を取得（analysis_resultから）
                    monthly_avg_actual = 0.0
                    if 'monthly_avg_actual' in analysis_result.columns:
                        product_monthly = analysis_result[analysis_result['product_code'] == product_code]
                        if len(product_monthly) > 0:
                            monthly_avg_actual = product_monthly.iloc[0]['monthly_avg_actual']
                            if pd.isna(monthly_avg_actual):
                                monthly_avg_actual = 0.0
                    
                    # 最終結果を保存
                    result_row = {
                        '商品コード': product_code,
                        'ABC区分': format_abc_category_for_display(abc_category),
                        '月当たり実績': monthly_avg_actual,
                        '現行設定_数量': current_qty,
                        '現行設定_日数': current_days,
                        '安全在庫①_数量': ss1_qty,  # 異常値処理前
                        '安全在庫②_数量': ss2_qty,  # 異常値処理前
                        '安全在庫③_数量': ss3_before_qty,  # 異常値処理前
                        '最終安全在庫①_数量': final_ss1_quantity,  # 異常値処理＋上限カット後
                        '最終安全在庫②_数量': final_ss2_quantity,  # 異常値処理＋上限カット後
                        '最終安全在庫③_数量': final_ss3_quantity,  # 異常値処理＋上限カット後
                        '安全在庫①_日数': ss1_days,  # 異常値処理前
                        '安全在庫②_日数': ss2_days,  # 異常値処理前
                        '安全在庫③_日数': ss3_before_days,  # 異常値処理前
                        '最終安全在庫①_日数': final_ss1_days,  # 異常値処理＋上限カット後
                        '最終安全在庫②_日数': final_ss2_days,  # 異常値処理＋上限カット後
                        '最終安全在庫③_日数': final_ss3_days,  # 異常値処理＋上限カット後
                        '日当たり実績': daily_actual_mean,
                        '欠品許容率': stockout_tolerance
                    }
                    final_results.append(result_row)
                    
                except Exception as e:
                    st.warning(f"{product_code} の処理でエラーが発生しました: {str(e)}")
                    continue
                
                progress_bar.progress((idx + 1) / total_products)
            
            progress_bar.empty()
            
            # 結果をDataFrameに変換
            if final_results:
                final_results_df = pd.DataFrame(final_results)
                st.session_state.final_safety_stock_results = final_results_df
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>異常値処理と上限カット完了：</strong>{len(final_results)}機種の異常値処理と上限カットが完了しました。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.error("❌ 処理結果がありません。")
                return
        
        # 最終安全在庫の結果表示
        if 'final_safety_stock_results' in st.session_state and st.session_state.final_safety_stock_results is not None:
            final_results_df = st.session_state.final_safety_stock_results.copy()
            
            st.markdown("""
            <div class="step-middle-section">
                <p>安全在庫算出結果（異常値処理後）サマリー</p>
            </div>
            """, unsafe_allow_html=True)
            
            # ABC区分別_安全在庫比較マトリクス（異常値処理後）を表示
            # 最終安全在庫の列を安全在庫①②③の列として扱うために、一時的に列名を変更
            display_df = final_results_df.copy()
            display_df['安全在庫①_数量'] = display_df['最終安全在庫①_数量']
            display_df['安全在庫①_日数'] = display_df['最終安全在庫①_日数']
            display_df['安全在庫②_数量'] = display_df['最終安全在庫②_数量']
            display_df['安全在庫②_日数'] = display_df['最終安全在庫②_日数']
            display_df['安全在庫③_数量'] = display_df['最終安全在庫③_数量']
            display_df['安全在庫③_日数'] = display_df['最終安全在庫③_日数']
            
            if 'ABC区分' in display_df.columns:
                st.markdown('<div class="step-sub-section">ABC区分別_安全在庫比較マトリクス</div>', unsafe_allow_html=True)
                display_abc_matrix_comparison(display_df, key_prefix="abc_matrix_after")
                
                # 受注量別 安全在庫比較グラフ（異常値処理後）を追加
                # Before/Afterを1つのグラフに統合して表示
                st.markdown("""
                <div class="step-middle-section">
                    <p>受注量別 安全在庫 比較グラフ（異常値処理後）</p>
                </div>
                """, unsafe_allow_html=True)
                st.caption("安全在庫モデルを『現行設定』『安全在庫①』『安全在庫②』『安全在庫③』から選択してください。")
                
                # 安全在庫タイプ選択UI（異常値処理前と同じ選択を維持）
                col1, col2 = st.columns([1, 3])
                with col1:
                    safety_stock_type_after = st.selectbox(
                        "安全在庫モデル",
                        options=["current", "ss1", "ss2", "ss3"],
                        format_func=lambda x: {
                            "current": "現行設定",
                            "ss1": "安全在庫①",
                            "ss2": "安全在庫②",
                            "ss3": "安全在庫③"
                        }[x],
                        index=3,  # デフォルトは安全在庫③
                        key="safety_stock_type_after"
                    )
                
                with col2:
                    type_descriptions = {
                        "current": "<strong>現行設定</strong>：現行設定している安全在庫",
                        "ss1": "<strong>安全在庫①</strong>：理論値【理論モデル】",
                        "ss2": "<strong>安全在庫②</strong>：実測値（実績 − 平均）【実績の変動に基づくモデル】",
                        "ss3": "<strong>安全在庫③</strong>：実測値（実績 − 計画）【計画誤差を考慮した推奨モデル】"
                    }
                    st.markdown(f'<div style="color: #555555; margin-top: 28px; line-height: 38px; display: flex; align-items: center;">{type_descriptions[safety_stock_type_after]}</div>', unsafe_allow_html=True)
                
                # 異常値処理前のデータを取得（比較用）
                before_results_df = st.session_state.get('all_products_results')
                
                # 全データから最大値を計算（軸スケール統一用）
                all_quantity_cols_before = ['現行設定_数量', '安全在庫①_数量', '安全在庫②_数量', '安全在庫③_数量']
                all_days_cols_before = ['現行設定_日数', '安全在庫①_日数', '安全在庫②_日数', '安全在庫③_日数']
                all_quantity_cols_after = ['現行設定_数量', '最終安全在庫①_数量', '最終安全在庫②_数量', '最終安全在庫③_数量']
                all_days_cols_after = ['現行設定_日数', '最終安全在庫①_日数', '最終安全在庫②_日数', '最終安全在庫③_日数']
                
                max_quantity = 0
                max_days = 0
                
                # 異常値処理前のデータから最大値を計算
                if before_results_df is not None:
                    for col in all_quantity_cols_before:
                        if col in before_results_df.columns:
                            valid_values = before_results_df[col].dropna()
                            if len(valid_values) > 0:
                                max_quantity = max(max_quantity, valid_values.max())
                    for col in all_days_cols_before:
                        if col in before_results_df.columns:
                            valid_values = before_results_df[col].dropna()
                            if len(valid_values) > 0:
                                max_days = max(max_days, valid_values.max())
                
                # 異常値処理後のデータから最大値を計算
                for col in all_quantity_cols_after:
                    if col in display_df.columns:
                        valid_values = display_df[col].dropna()
                        if len(valid_values) > 0:
                            max_quantity = max(max_quantity, valid_values.max())
                for col in all_days_cols_after:
                    if col in display_df.columns:
                        valid_values = display_df[col].dropna()
                        if len(valid_values) > 0:
                            max_days = max(max_days, valid_values.max())
                
                # 通常の安全在庫列も確認（最終安全在庫が存在しない場合に備えて）
                for col in all_quantity_cols_before:
                    if col in display_df.columns:
                        valid_values = display_df[col].dropna()
                        if len(valid_values) > 0:
                            max_quantity = max(max_quantity, valid_values.max())
                for col in all_days_cols_before:
                    if col in display_df.columns:
                        valid_values = display_df[col].dropna()
                        if len(valid_values) > 0:
                            max_days = max(max_days, valid_values.max())
                
                # デフォルト値を計算（1.1倍のマージン）
                default_y1_max = max_quantity * 1.1 if max_quantity > 0 else 100
                default_y2_max = max_days * 1.1 if max_days > 0 else 50
                
                # セッション状態の初期化
                if 'step3_after_y1_max' not in st.session_state:
                    st.session_state.step3_after_y1_max = default_y1_max
                if 'step3_after_y2_max' not in st.session_state:
                    st.session_state.step3_after_y2_max = default_y2_max
                
                fig = create_order_volume_comparison_chart_after(
                    display_df, 
                    before_results_df=before_results_df, 
                    safety_stock_type=safety_stock_type_after,
                    y1_max=st.session_state.step3_after_y1_max,
                    y2_max=st.session_state.step3_after_y2_max
                )
                if len(fig.data) > 0:
                    st.plotly_chart(fig, use_container_width=True, key="order_volume_comparison_chart_after")
                    
                    # 縦軸最大値の入力欄を追加
                    col_y1, col_y2 = st.columns(2)
                    with col_y1:
                        y1_max_input = st.number_input(
                            "左縦軸「数量」最大値",
                            min_value=0.0,
                            value=float(st.session_state.step3_after_y1_max),
                            step=100.0,
                            key="step3_after_y1_max_input"
                        )
                        st.session_state.step3_after_y1_max = y1_max_input
                    
                    with col_y2:
                        y2_max_input = st.number_input(
                            "右縦軸「日数」最大値",
                            min_value=0.0,
                            value=float(st.session_state.step3_after_y2_max),
                            step=5.0,
                            key="step3_after_y2_max_input"
                        )
                        st.session_state.step3_after_y2_max = y2_max_input
                else:
                    st.warning("グラフ表示に必要なデータがありません。")
            
            # 詳細データ
            st.markdown('<div class="step-sub-section">詳細データ</div>', unsafe_allow_html=True)
            # 月当たり実績で降順ソート
            if '月当たり実績' in final_results_df.columns:
                final_results_df = final_results_df.sort_values('月当たり実績', ascending=False).reset_index(drop=True)
            # 列順を指定して並び替え（ABC区分の右隣に月当たり実績を配置）
            column_order = [
                '商品コード', 'ABC区分', '月当たり実績', '現行設定_数量', '現行設定_日数',
                '安全在庫①_数量', '安全在庫②_数量', '安全在庫③_数量',  # 異常値処理前
                '最終安全在庫①_数量', '最終安全在庫②_数量', '最終安全在庫③_数量',  # 異常値処理＋上限カット後
                '安全在庫①_日数', '安全在庫②_日数', '安全在庫③_日数',  # 異常値処理前
                '最終安全在庫①_日数', '最終安全在庫②_日数', '最終安全在庫③_日数',  # 異常値処理＋上限カット後
                '日当たり実績', '欠品許容率'
            ]
            available_columns = [col for col in column_order if col in final_results_df.columns]
            final_results_df_display = final_results_df[available_columns]
            # 横スクロールを有効化（use_container_width=Trueで自動的に横スクロール可能）
            st.dataframe(final_results_df_display, use_container_width=True, hide_index=True)
            
            # CSVエクスポート
            # Plotly標準の"Download as CSV"があるため、独自のダウンロードボタンは廃止
            
            # ========== 手順④：安全在庫登録データを作成する ==========
            st.divider()
            st.markdown("""
            <div class="step-middle-section">
                <p>手順④：安全在庫登録データを作成する</p>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class="step-description">③で確定した最終安全在庫をSCP登録用データとして出力します。<br>CSV形式でダウンロードでき、システムへの登録に使用できます。</div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("安全在庫登録データを作成する", type="primary", use_container_width=True):
                # 登録用データを作成（現行設定_数量、現行設定_日数を追加）
                registration_df = final_results_df[[
                    '商品コード', 'ABC区分', 
                    '最終安全在庫①_数量', '最終安全在庫①_日数',
                    '最終安全在庫②_数量', '最終安全在庫②_日数',
                    '最終安全在庫③_数量', '最終安全在庫③_日数',
                    '現行設定_数量', '現行設定_日数'
                ]].copy()
                
                # 列名を変更
                registration_df = registration_df.rename(columns={
                    '現行設定_数量': '現行設定_数量',
                    '現行設定_日数': '現行設定_日数'
                })
                
                # セッション状態に保存
                st.session_state.registration_data = registration_df
                st.markdown("""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>登録データ作成完了：</strong>安全在庫登録データの作成が完了しました。このデータはSCPソリューション用の登録ファイルとして利用できます。</div>
                </div>
                """, unsafe_allow_html=True)
            
            # 登録データのダウンロード
            if 'registration_data' in st.session_state and st.session_state.registration_data is not None:
                registration_df = st.session_state.registration_data.copy()
                
                # SCP登録用データを作成（商品コードと安全在庫③月数のみ）
                scp_registration_df = pd.DataFrame({
                    '商品コード': registration_df['商品コード'],
                    '安全在庫③月数': registration_df['最終安全在庫③_日数'] / 20
                })
                
                # CSV形式でダウンロード
                csv = scp_registration_df.to_csv(index=False, encoding='utf-8-sig')
                csv_bytes = csv.encode('utf-8-sig')
                st.download_button(
                    label="安全在庫登録データをダウンロード（SCP登録用）",
                    data=csv_bytes,
                    file_name=f"scp_registration_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_registration_data"
                )
                
                # 補足説明を追加
                st.markdown("""
                <div class="step-description">『商品コード』と『安全在庫③月数』のみをダウンロードします。安全在庫③月数は『安全在庫③_日数』÷20 で算出しています。</div>
                """, unsafe_allow_html=True)
                
                # 登録データのプレビュー（ダウンロード対象と同じ内容を表示）
                st.markdown('<div class="step-sub-section">登録データプレビュー</div>', unsafe_allow_html=True)
                # テーブルの横幅をさらにコンパクト化し、左寄せで表示（現在の約半分の幅）
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.dataframe(scp_registration_df, use_container_width=True, hide_index=True)


# ========================================
# STEP3専用のUIヘルパー関数
# ========================================

def display_abc_matrix_comparison(results_df, key_prefix="abc_matrix"):
    """
    ABC区分別 安全在庫比較結果をマトリクス形式で表示
    
    Args:
        results_df: 全機種の安全在庫算出結果DataFrame
        key_prefix: ダウンロードボタンの一意のキープレフィックス
    """
    # 見出しは呼び出し側で表示するため、ここでは表示しない
    
    # 在庫日数ビンの定義
    bins = ["0日（設定なし）", "0〜5日", "5〜10日", "10〜15日", "15〜20日", "20〜30日", "30〜40日", "40〜50日", "50日以上"]
    
    from utils.common import format_abc_category_for_display
    
    # ABC区分列を表示用に変換（NaNの場合は「未分類」）
    if 'ABC区分' in results_df.columns:
        results_df = results_df.copy()
        results_df['ABC区分'] = results_df['ABC区分'].apply(format_abc_category_for_display)
    
    # STEP1で生成された全区分を取得（'-'は除外し、「未分類」を含める）
    all_categories = sorted([cat for cat in results_df['ABC区分'].unique() if cat != '-'])
    
    # 区分名を「◯区分」形式に変換
    category_labels = {cat: f"{cat}区分" for cat in all_categories}
    
    # 安全在庫タイプの定義（表示名、日数列名、数量列名）
    ss_types = [
        ('現行設定', '現行設定_日数', '現行設定_数量'),
        ('安全在庫①', '安全在庫①_日数', '安全在庫①_数量'),
        ('安全在庫②', '安全在庫②_日数', '安全在庫②_数量'),
        ('安全在庫③', '安全在庫③_日数', '安全在庫③_数量')
    ]
    
    # 旧名称から新名称へのマッピング（内部処理用）
    old_to_new_label = {
        '現在庫': '現安全在庫',
        '安全①': '安全在庫①',
        '安全②': '安全在庫②',
        '安全③': '安全在庫③'
    }
    
    # マトリクスデータを構築（縦軸：在庫日数ビン、横軸：区分×安全在庫タイプ）
    matrix_rows = []
    
    # 各行（在庫日数ビン）のデータを作成
    for bin_name in bins:
        row_data = {'在庫日数': bin_name}
        
        # 合計ブロック（4列：現行設定、安全在庫①、安全在庫②、安全在庫③）
        for ss_type_name, days_col, qty_col in ss_types:
            if ss_type_name == '現行設定':
                mask = (results_df[days_col].apply(classify_inventory_days_bin) == bin_name)
            else:
                if bin_name == "0日（設定なし）":
                    mask = (
                        (results_df[days_col].apply(classify_inventory_days_bin) == bin_name) |
                        (results_df['日当たり実績'].isna()) |
                        (results_df['日当たり実績'] <= 0)
                    )
                else:
                    mask = (
                        (results_df[days_col].apply(classify_inventory_days_bin) == bin_name) &
                        (results_df['日当たり実績'].notna()) &
                        (results_df['日当たり実績'] > 0)
                    )
            
            count = mask.sum()
            row_data[('合計', ss_type_name)] = count
        
        # 各区分ブロック（各区分×4列）
        for category in all_categories:
            category_df = results_df[results_df['ABC区分'] == category]
            category_label = category_labels[category]
            
            for ss_type_name, days_col, qty_col in ss_types:
                if ss_type_name == '現行設定':
                    mask = (category_df[days_col].apply(classify_inventory_days_bin) == bin_name)
                else:
                    if bin_name == "0日（設定なし）":
                        mask = (
                            (category_df[days_col].apply(classify_inventory_days_bin) == bin_name) |
                            (category_df['日当たり実績'].isna()) |
                            (category_df['日当たり実績'] <= 0)
                        )
                    else:
                        mask = (
                            (category_df[days_col].apply(classify_inventory_days_bin) == bin_name) &
                            (category_df['日当たり実績'].notna()) &
                            (category_df['日当たり実績'] > 0)
                        )
                
                count = mask.sum()
                row_data[(category_label, ss_type_name)] = count
        
        matrix_rows.append(row_data)
    
    # マトリクスDataFrameを作成
    matrix_df = pd.DataFrame(matrix_rows)
    matrix_df = matrix_df.set_index('在庫日数')
    
    # 列名を「◯区分」形式に変換
    new_columns = []
    for col_tuple in matrix_df.columns:
        if col_tuple[0] in category_labels:
            new_columns.append((category_labels[col_tuple[0]], col_tuple[1]))
        else:
            new_columns.append(col_tuple)
    matrix_df.columns = pd.MultiIndex.from_tuples(new_columns)
    
    # サマリー行を追加（合計件数、安全在庫_数量、安全在庫_日数）
    summary_rows = []
    
    # 1. 合計件数行
    total_count_row = {'在庫日数': '合計件数'}
    for ss_type_name, days_col, qty_col in ss_types:
        # 合計ブロック
        total_count_row[('合計', ss_type_name)] = len(results_df)
        
        # 各区分ブロック
        for category in all_categories:
            category_df = results_df[results_df['ABC区分'] == category]
            category_label = category_labels[category]
            total_count_row[(category_label, ss_type_name)] = len(category_df)
    summary_rows.append(total_count_row)
    
    # 2. 安全在庫数行（四捨五入して整数表示、カンマ区切り）
    ss_quantity_row = {'在庫日数': '安全在庫_数量'}
    for ss_type_name, days_col, qty_col in ss_types:
        # 合計ブロック
        valid_mask = (
            (results_df['日当たり実績'].notna()) &
            (results_df['日当たり実績'] > 0) &
            (results_df[days_col].notna()) &
            (results_df[days_col] > 0)
        )
        
        if valid_mask.sum() > 0:
            valid_df = results_df[valid_mask]
            ss_quantity = (valid_df[days_col] * valid_df['日当たり実績']).sum()
            ss_quantity = round(ss_quantity)  # 四捨五入
        else:
            ss_quantity = 0
        ss_quantity_row[('合計', ss_type_name)] = f"{ss_quantity:,}"  # カンマ区切り
        
        # 各区分ブロック
        for category in all_categories:
            category_df = results_df[results_df['ABC区分'] == category]
            category_label = category_labels[category]
            category_valid_mask = (
                (category_df['日当たり実績'].notna()) &
                (category_df['日当たり実績'] > 0) &
                (category_df[days_col].notna()) &
                (category_df[days_col] > 0)
            )
            
            if category_valid_mask.sum() > 0:
                category_valid_df = category_df[category_valid_mask]
                category_ss_quantity = (category_valid_df[days_col] * category_valid_df['日当たり実績']).sum()
                category_ss_quantity = round(category_ss_quantity)  # 四捨五入
            else:
                category_ss_quantity = 0
            ss_quantity_row[(category_label, ss_type_name)] = f"{category_ss_quantity:,}"  # カンマ区切り
    summary_rows.append(ss_quantity_row)
    
    # 3. 安全在庫_日数行
    ss_days_row = {'在庫日数': '安全在庫_日数'}
    for ss_type_name, days_col, qty_col in ss_types:
        # 合計ブロック
        valid_mask = (
            (results_df['日当たり実績'].notna()) &
            (results_df['日当たり実績'] > 0) &
            (results_df[days_col].notna()) &
            (results_df[days_col] > 0)
        )
        
        if valid_mask.sum() > 0:
            valid_df = results_df[valid_mask]
            ss_quantity = (valid_df[days_col] * valid_df['日当たり実績']).sum()
            ss_days = ss_quantity / valid_df['日当たり実績'].sum() if valid_df['日当たり実績'].sum() > 0 else 0
        else:
            ss_days = 0
        ss_days_row[('合計', ss_type_name)] = f"{ss_days:.1f}日"
        
        # 各区分ブロック
        for category in all_categories:
            category_df = results_df[results_df['ABC区分'] == category]
            category_label = category_labels[category]
            category_valid_mask = (
                (category_df['日当たり実績'].notna()) &
                (category_df['日当たり実績'] > 0) &
                (category_df[days_col].notna()) &
                (category_df[days_col] > 0)
            )
            
            if category_valid_mask.sum() > 0:
                category_valid_df = category_df[category_valid_mask]
                category_ss_quantity = (category_valid_df[days_col] * category_valid_df['日当たり実績']).sum()
                category_ss_days = category_ss_quantity / category_valid_df['日当たり実績'].sum() if category_valid_df['日当たり実績'].sum() > 0 else 0
            else:
                category_ss_days = 0
            ss_days_row[(category_label, ss_type_name)] = f"{category_ss_days:.1f}日"
    summary_rows.append(ss_days_row)
    
    # サマリー行をマトリクスに追加（空白行は追加しない）
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        summary_df = summary_df.set_index('在庫日数')
        
        # 列名を「◯区分」形式に変換
        summary_new_columns = []
        for col_tuple in summary_df.columns:
            if col_tuple[0] in category_labels:
                summary_new_columns.append((category_labels[col_tuple[0]], col_tuple[1]))
            else:
                summary_new_columns.append(col_tuple)
        summary_df.columns = pd.MultiIndex.from_tuples(summary_new_columns)
        
        matrix_df = pd.concat([matrix_df, summary_df])
    
    # 空白行を完全に除去（NaNや空の行、全てが空文字列の行を削除）
    matrix_df = matrix_df.dropna(how='all')
    # 全てのセルが空文字列や空白のみの行も削除
    matrix_df = matrix_df[~matrix_df.apply(lambda row: row.astype(str).str.strip().eq('').all(), axis=1)]
    
    # 「安全在庫_日数」行の後の空白行を削除
    # 安全在庫_日数行のインデックスを取得
    if '安全在庫_日数' in matrix_df.index:
        ss_days_idx = matrix_df.index.get_loc('安全在庫_日数')
        # 安全在庫_日数行より後の行をチェックし、空白行を削除
        rows_to_drop = []
        for i in range(ss_days_idx + 1, len(matrix_df)):
            row = matrix_df.iloc[i]
            # 全てのセルがNaN、空文字列、または空白のみかチェック
            if row.isna().all() or row.astype(str).str.strip().eq('').all():
                rows_to_drop.append(matrix_df.index[i])
            else:
                # 空白でない行が見つかったら終了
                break
        if rows_to_drop:
            matrix_df = matrix_df.drop(rows_to_drop)
    
    # マトリクス表示用のスタイル設定
    def style_matrix(val):
        """セルのスタイル設定"""
        return 'text-align: right;'
    
    # マトリクスを表示（Styler使用）
    styled_matrix = matrix_df.style.applymap(style_matrix, subset=pd.IndexSlice[:, :])
    
    # 区分ごとの色付け（奇数番目の区分列ブロックに背景色を付与）
    def highlight_cols_by_category(col):
        """区分ごとの列色分け（奇数区分に色付け）"""
        # MultiIndexの列名から区分名を取得
        if isinstance(col.name, tuple) and len(col.name) >= 1:
            category_name = col.name[0]  # 1行目の区分名
        else:
            category_name = str(col.name)
        
        # 合計列は常に白背景
        if category_name == '合計':
            return ['background-color: #FFFFFF'] * len(col)
        
        # 区分名から文字部分を抽出（例：「A区分」→「A」）
        category_char = category_name.replace('区分', '')
        
        # 区分のインデックスを取得（A=0, B=1, C=2, ...）
        sorted_categories = sorted([cat for cat in all_categories])
        try:
            category_index = sorted_categories.index(category_char)
        except ValueError:
            # 区分が見つからない場合は白背景
            return ['background-color: #FFFFFF'] * len(col)
        
        # 奇数番目（インデックスが0から始まるため、インデックス%2==0が1番目、3番目...）
        # A区分=0（偶数）=1番目（奇数番目）、B区分=1（奇数）=2番目（偶数番目）、C区分=2（偶数）=3番目（奇数番目）
        if category_index % 2 == 0:  # 奇数番目の区分（A区分、C区分など）
            return ['background-color: #E0E0E0'] * len(col)  # グレー背景
        else:  # 偶数番目の区分（B区分、D区分など）
            return ['background-color: #FFFFFF'] * len(col)  # 白背景
    
    styled_matrix = styled_matrix.apply(highlight_cols_by_category, axis=0)
    
    # 重要行（安全在庫_数量、安全在庫_日数）の強調
    def highlight_important_rows(row):
        """重要行の強調（背景色＋太字＋縁取り）"""
        # 行名を取得（MultiIndexの場合は最初の要素）
        if hasattr(row, 'name'):
            row_name = row.name
            if isinstance(row_name, tuple):
                row_name = row_name[0] if len(row_name) > 0 else str(row_name)
            elif not isinstance(row_name, str):
                row_name = str(row_name)
        else:
            row_name = ''
        
        # 重要行の判定
        if row_name == '安全在庫_数量' or row_name == '安全在庫_日数':
            return ['background-color: #FFF9C4; font-weight: bold; border: 2px solid #F57F17'] * len(row)
        return [''] * len(row)
    
    styled_matrix = styled_matrix.apply(highlight_important_rows, axis=1)
    
    # Streamlitで表示
    st.dataframe(styled_matrix, use_container_width=True, height=500)
    
    # CSV出力ボタン
    # Plotly標準の"Download as CSV"があるため、独自のダウンロードボタンは廃止
    
    # 注記を表示
    st.markdown("---")
    st.markdown("""
    **※注記：**
    - 表内の数値は該当する機種数（SKU件数）です。
    - 現行設定_数量が0、または安全在庫①/②/③_数量が計算できない機種は、「0日（設定なし）」に分類します。
    - 安全在庫_数量は、各機種の［安全在庫_日数 × 日当たり実績］（※四捨五入して整数表示）を算出し、全件集計した値です。
    - 安全在庫_日数（加重平均）は、全件集計［安全在庫_数量］ ÷ 全件集計［日当たり実績］で算出します。
    - 安全在庫_日数は「稼働日ベース」です（非稼働日は日当たり実績に含みません）。
    - 日当たり実績が0または欠損、または安全在庫_日数を算出できない機種は、安全在庫_日数（加重平均）の対象外です。
    - 在庫日数の区分は、各範囲の上限値を含みます（例：5.0日は「0〜5日」、50.0日は「40〜50日」に分類）。
    """)

