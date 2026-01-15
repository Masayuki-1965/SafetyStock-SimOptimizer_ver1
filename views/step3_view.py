"""
STEP3 ビュー
安全在庫算出と登録値作成（全機種）のUI
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
    get_abc_analysis_with_fallback,
    calculate_plan_error_rate,
    is_plan_anomaly,
    format_abc_category_for_display,
    calculate_abc_category_ratio_r
)
from views.step2_view import determine_adopted_model
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
    <div class="step-description">全機種の安全在庫の算出に必要な条件（<strong>リードタイム</strong>、<strong>欠品許容率</strong>）を設定します。<br>
    これらの設定値は、後続の手順で適用される安全在庫モデルの結果に直接影響します。</div>
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
    if st.button("安全在庫を算出する", type="primary", width='stretch'):
        # STEP1のデータ整合性チェック結果から「計画のみ」の商品コードリストを取得
        plan_only_codes = set()
        mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
        if mismatch_detail_df is not None and not mismatch_detail_df.empty:
            plan_only_df = mismatch_detail_df[mismatch_detail_df['区分'] == '計画のみ']
            if not plan_only_df.empty:
                plan_only_codes = set(str(code) for code in plan_only_df['商品コード'].unique())
        
        # 全機種の安全在庫を算出
        all_results = []
        skipped_count = 0  # 「計画のみ」でスキップした件数
        progress_bar = st.progress(0)
        total_products = len(product_list)
        
        for idx, product_code in enumerate(product_list):
            # 「計画のみ」の商品は安全在庫算出対象外としてスキップ
            if str(product_code) in plan_only_codes:
                skipped_count += 1
                progress_bar.progress((idx + 1) / total_products)
                continue
            
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
                
            except KeyError as e:
                # KeyErrorの場合は、商品コードがデータに存在しない可能性がある
                st.warning(f"⚠️ {product_code} の計算でエラーが発生しました: 商品コードがデータに存在しない可能性があります。詳細: {str(e)}")
                continue
            except Exception as e:
                # その他のエラーの場合は、エラーの型とメッセージを表示
                error_type = type(e).__name__
                st.warning(f"⚠️ {product_code} の計算でエラーが発生しました ({error_type}): {str(e)}")
                continue
            
            progress_bar.progress((idx + 1) / total_products)
        
        progress_bar.empty()
        
        # 「計画のみ」の商品が存在する場合、警告メッセージを1回だけ表示
        if skipped_count > 0:
            st.markdown(f"""
            <div class="annotation-warning-box">
                <span class="icon">⚠</span>
                <div class="text">実績データが存在しない商品が {skipped_count}件 あるため、これらは安全在庫の算出対象外としました。<br>詳細は STEP1 のデータ整合性チェック結果サマリーにて、区分「計画のみ」をご確認ください。</div>
            </div>
            """, unsafe_allow_html=True)
        
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
            
            # 受注量の多い商品順 安全在庫比較グラフ（異常値処理前）を追加
            st.markdown("""
            <div class="step-middle-section">
                <p>受注量の多い商品順 安全在庫 比較グラフ（異常値処理前）</p>
            </div>
            """, unsafe_allow_html=True)
            st.caption("※ 安全在庫モデルを「現行設定」「安全在庫①」「安全在庫②」「安全在庫③」から選択してください。（初期値：安全在庫③）")
            
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
                    "current": "<strong>【現行設定】</strong> 現行設定している安全在庫",
                    "ss1": "<strong>【安全在庫①】</strong> 一般的な理論モデル",
                    "ss2": "<strong>【安全在庫②】</strong> 実績バラつき実測モデル",
                    "ss3": "<strong>【安全在庫③】</strong> 計画誤差実測モデル（推奨）"
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
                st.plotly_chart(fig, use_container_width=True, key="order_volume_comparison_chart_before", config={'displayModeBar': True, 'displaylogo': False})
                
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
        
        # 詳細テーブル（折り畳み式、デフォルト：非表示）
        with st.expander("詳細データを表示", expanded=False):
            # 表示用のDataFrameを作成（コピー）
            display_df = results_df.copy()
            
            # 列名を変更（異常処理前を明示）
            if '月当たり実績' in display_df.columns:
                display_df = display_df.rename(columns={'月当たり実績': '月当たり実績（異常処理前）'})
            if '日当たり実績' in display_df.columns:
                display_df = display_df.rename(columns={'日当たり実績': '日当たり実績（異常処理前）'})
            
            # 稼働日数を追加（データローダーから取得）
            try:
                if st.session_state.uploaded_data_loader is not None:
                    data_loader = st.session_state.uploaded_data_loader
                else:
                    data_loader = DataLoader("data/日次計画データ.csv", "data/日次実績データ.csv")
                    data_loader.load_data()
                working_dates = data_loader.get_working_dates()
                working_days_count = len(working_dates)
                display_df['稼働日数'] = working_days_count
            except:
                display_df['稼働日数'] = None
            
            # 月当たり実績（異常処理前）で降順ソート
            if '月当たり実績（異常処理前）' in display_df.columns:
                display_df = display_df.sort_values('月当たり実績（異常処理前）', ascending=False).reset_index(drop=True)
            
            # 列順を指定して並び替え（要件に基づく順序）
            column_order = [
                '商品コード',
                'ABC区分',
                '月当たり実績（異常処理前）',
                '現行設定_数量',
                '安全在庫①_数量',
                '安全在庫②_数量',
                '安全在庫③_数量',
                '現行設定_日数',
                '安全在庫①_日数',
                '安全在庫②_日数',
                '安全在庫③_日数',
                '日当たり実績（異常処理前）',
                '稼働日数',
                '欠品許容率'
            ]
            # 存在する列のみを選択
            available_columns = [col for col in column_order if col in display_df.columns]
            display_df_display = display_df[available_columns]
            # 横スクロールを有効化（width='stretch'で自動的に横スクロール可能）
            st.dataframe(display_df_display, width='stretch', hide_index=True)
        
        # CSVエクスポート（列順を指定）
        # Plotly標準の"Download as CSV"があるため、独自のダウンロードボタンは廃止
        
        # ========== 手順③：安全在庫を確定する（異常値処理） ==========
        st.divider()
        st.markdown("""
        <div class="step-middle-section">
            <p>手順③：安全在庫を確定する（異常値処理）</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div class="step-description">全機種に対して<strong> 実績異常値処理 → 計画異常値処理 → 上限カット </strong>の順に適用し、最終的な安全在庫を確定します。<br>
        実績異常値処理では、需要データの統計的な上振れ異常値を検出し補正します。<br>
        計画異常値処理では、計画誤差率が 許容範囲内なら安全在庫③（推奨）、超過する場合は安全在庫②'（補正モデル） を採用して精度を確保します。<br>
        最後に、ABC 区分ごとに設定した上限日数でカットし、過剰な安全在庫を抑制します。</div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 実績異常値処理のパラメータ設定
        st.markdown('<div class="step-sub-section">実績異常値処理のパラメータ設定</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            sigma_k = st.number_input(
                "異常基準：mean + σ × (係数)",
                min_value=1.0,
                max_value=10.0,
                value=6.0,
                step=0.5,
                help="※ 平均からどれだけ離れた値を異常とみなすか？",
                key="step3_sigma_k"
            )
        
        with col2:
            top_limit_p = st.number_input(
                "上位カット割合（％）",
                min_value=1.0,
                max_value=5.0,
                value=2.0,
                step=0.1,
                help="※ 上位何％を補正対象とするか？",
                key="step3_top_limit_p"
            )
        
        # 割合（％）のみで制御する仕様に統一
        top_limit_mode = 'percent'
        top_limit_n = None
        
        # 計画異常値処理のパラメータ設定
        st.markdown('<div class="step-sub-section">計画異常値処理のパラメータ設定</div>', unsafe_allow_html=True)
        col3, col4 = st.columns(2)
        with col3:
            plan_plus_threshold = st.number_input(
                "計画誤差率（プラス）の閾値（%）",
                min_value=0.0,
                max_value=500.0,
                value=st.session_state.get("step3_plan_plus_threshold", st.session_state.get("step2_plan_plus_threshold_final", 10.0)),
                step=5.0,
                help="計画誤差率がこの値を超える場合、安全在庫②'を採用します。",
                key="step3_plan_plus_threshold"
            )
        with col4:
            plan_minus_threshold = st.number_input(
                "計画誤差率（マイナス）の閾値（%）",
                min_value=-500.0,
                max_value=0.0,
                value=st.session_state.get("step3_plan_minus_threshold", st.session_state.get("step2_plan_minus_threshold_final", -10.0)),
                step=5.0,
                help="計画誤差率がこの値を下回る場合、安全在庫②'を採用します。",
                key="step3_plan_minus_threshold"
            )
        
        # r上限値の設定（折り畳み式）
        with st.expander("r 上限値の設定（任意）", expanded=False):
            ratio_r_upper_limit = st.number_input(
                "r上限値（閾値）",
                min_value=0.1,
                max_value=10.0,
                value=st.session_state.get("step3_ratio_r_upper_limit", 1.5),
                step=0.1,
                help="区分内のデータが極端に少ない場合のブレを避けるため",
                key="step3_ratio_r_upper_limit"
            )
            st.caption("※ r上限値（閾値）は、補正モデル②' を採用するか判断する基準値です（初期値1.5）。通常はこのままご使用ください。")
        
        # ABC区分ごとの上限日数設定
        st.markdown('<div class="step-sub-section">ABC区分ごとの上限日数設定</div>', unsafe_allow_html=True)
        st.caption("※ 0 を入力した場合は上限なし（制限なし）")
        
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
                    f"{cat}区分の上限日数（日）",
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
        
        # 実績異常値処理・計画異常値処理・上限カットと最終安全在庫の確定ボタン
        if st.button("実績異常値処理・計画異常値処理・上限カットを実施する", type="primary", width='stretch'):
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
            
            # STEP1のデータ整合性チェック結果から「計画のみ」の商品コードリストを取得
            plan_only_codes = set()
            mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
            if mismatch_detail_df is not None and not mismatch_detail_df.empty:
                plan_only_df = mismatch_detail_df[mismatch_detail_df['区分'] == '計画のみ']
                if not plan_only_df.empty:
                    plan_only_codes = set(str(code) for code in plan_only_df['商品コード'].unique())
            
            # パラメータを取得
            lead_time = st.session_state.get("shared_lead_time", 45)
            lead_time_type = st.session_state.get("shared_lead_time_type", "working_days")
            stockout_tolerance = st.session_state.get("shared_stockout_tolerance", 1.0)
            std_method = st.session_state.get("shared_std_method", STD_METHOD_FIXED)
            ratio_r_upper_limit = st.session_state.get("step3_ratio_r_upper_limit", 1.5)
            
            # 比率rを事前に算出（全商品の実績異常値処理後の安全在庫②・③から算出）
            from utils.common import calculate_abc_category_ratio_r
            ratio_r_by_category = calculate_abc_category_ratio_r(
                data_loader=data_loader,
                lead_time=lead_time,
                lead_time_type=lead_time_type,
                stockout_tolerance_pct=stockout_tolerance,
                sigma_k=sigma_k,
                top_limit_mode='percent',
                top_limit_n=2,
                top_limit_p=top_limit_p,
                category_cap_days={}  # 比率r算出時は上限カットを適用しない
            )
            
            # 全機種に異常値処理を適用して最終安全在庫を算出
            final_results = []
            skipped_count = 0  # 「計画のみ」でスキップした件数
            progress_bar = st.progress(0)
            total_products = len(product_list)
            
            for idx, product_code in enumerate(product_list):
                # 「計画のみ」の商品は安全在庫算出対象外としてスキップ
                if str(product_code) in plan_only_codes:
                    skipped_count += 1
                    progress_bar.progress((idx + 1) / total_products)
                    continue
                
                try:
                    # データ取得
                    plan_data = data_loader.get_daily_plan(product_code)
                    actual_data = data_loader.get_daily_actual(product_code)
                    working_dates = data_loader.get_working_dates()
                    
                    # ABC区分を取得
                    abc_category = None
                    abc_category = get_product_category(product_code)
                    
                    # 実績異常値処理を適用
                    outlier_handler = OutlierHandler(
                        actual_data=actual_data,
                        working_dates=working_dates,
                        sigma_k=sigma_k,
                        top_limit_mode='percent',
                        top_limit_n=2,
                        top_limit_p=top_limit_p,
                        abc_category=abc_category
                    )
                    
                    processing_result = outlier_handler.detect_and_correct()
                    corrected_data = processing_result['corrected_data']
                    is_outlier_processed = processing_result.get('processing_info', {}).get('final_count', 0) > 0
                    
                    # 実績異常値処理後のデータで安全在庫を再算出
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
                        category_cap_days={},  # ここでは上限カットは適用しない（後で適用する）
                        original_actual_data=actual_data  # 実績異常値処理前のデータを保存
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
                    
                    # 計画異常値処理の判定
                    plan_error_rate, plan_error, plan_total = calculate_plan_error_rate(actual_data, plan_data)
                    actual_total = actual_data.sum()
                    is_plan_anomaly_flag, _ = is_plan_anomaly(
                        plan_error_rate,
                        plan_plus_threshold,
                        plan_minus_threshold
                    )
                    
                    # ABC区分の表示名を取得（比率rのキーとして使用）
                    abc_category_display = format_abc_category_for_display(abc_category)
                    
                    # 安全在庫②'を全機種で計算（前提0)に基づき、常に計算する）
                    # 比率rを取得（区分別 → 全区分の順でフォールバック）
                    ratio_r_category = ratio_r_by_category.get('ratio_r', {}).get(abc_category_display) if ratio_r_by_category.get('ratio_r') else None
                    ratio_r_all = ratio_r_by_category.get('ratio_r_all')
                    
                    ratio_r = None
                    used_r_source = None
                    
                    # 区分別rのチェック
                    import math
                    if ratio_r_category is not None:
                        if (not math.isnan(ratio_r_category) and 
                            not math.isinf(ratio_r_category) and 
                            ratio_r_category > 0):
                            if ratio_r_category <= ratio_r_upper_limit:
                                ratio_r = ratio_r_category
                                used_r_source = "区分別"
                    
                    # 区分別rが使えない場合は全区分rを試す
                    if ratio_r is None and ratio_r_all is not None:
                        if (not math.isnan(ratio_r_all) and 
                            not math.isinf(ratio_r_all) and 
                            ratio_r_all > 0):
                            ratio_r = ratio_r_all
                            used_r_source = "全区分"
                    
                    # 安全在庫②'を全機種で計算（前提0)に基づき、常に計算する）
                    # rが算出できない場合でも、安全在庫②'は安全在庫②と同じ値として計算する
                    ss2_corrected = None
                    ss2_corrected_days = None
                    if ratio_r is not None:
                        # r < 1 の場合は補正を行わず「安全在庫②' = 安全在庫② と同値」で扱う
                        if ratio_r < 1.0:
                            ss2_corrected = final_ss2_quantity  # r < 1 の場合は補正を適用しない
                        else:
                            ss2_corrected = final_ss2_quantity * ratio_r
                    else:
                        # rが算出できない場合でも、安全在庫②'は安全在庫②と同じ値として計算する
                        ss2_corrected = final_ss2_quantity
                    ss2_corrected_days = ss2_corrected / daily_actual_mean if (daily_actual_mean > 0 and ss2_corrected is not None) else 0
                    
                    # 安全在庫②'を上限カット後に適用（条件カット後）
                    final_ss2_corrected_quantity = None
                    final_ss2_corrected_days = None
                    if ss2_corrected is not None:
                        final_ss2_corrected_quantity = apply_cap_days(ss2_corrected, daily_actual_mean, abc_category)
                        final_ss2_corrected_days = final_ss2_corrected_quantity / daily_actual_mean if daily_actual_mean > 0 else 0
                    else:
                        # ss2_correctedがNoneの場合は、安全在庫②と同じ値として扱う
                        final_ss2_corrected_quantity = final_ss2_quantity
                        final_ss2_corrected_days = final_ss2_days
                    
                    # 採用モデルを決定（安全在庫②'の算出後）
                    adopted_model, adopted_model_name, _, _, _ = determine_adopted_model(
                        plan_error_rate=plan_error_rate,
                        is_anomaly=is_plan_anomaly_flag,
                        abc_category=abc_category_display,
                        ratio_r_by_category=ratio_r_by_category,
                        ss2_value=final_ss2_quantity,
                        ss3_value=final_ss3_quantity,
                        daily_actual_mean=daily_actual_mean,
                        plan_plus_threshold=plan_plus_threshold,
                        plan_minus_threshold=plan_minus_threshold,
                        ratio_r_upper_limit=ratio_r_upper_limit,
                        actual_total=actual_total
                    )
                    
                    # 最終安全在庫の決定（採用モデルに基づく）
                    if adopted_model == "excluded":
                        # 判定対象外（実績合計 <= 0）の場合は安全在庫0扱い
                        final_safety_stock_quantity = 0.0
                        final_safety_stock_days = 0.0
                        final_model_name = "判定対象外"
                        # 採用モデルがないため、上限カットは適用されない
                        is_cap_applied = False
                    elif adopted_model == "ss2_corrected":
                        # 安全在庫②'を採用
                        final_safety_stock_quantity = final_ss2_corrected_quantity if final_ss2_corrected_quantity is not None else 0.0
                        final_safety_stock_days = final_ss2_corrected_days if final_ss2_corrected_days is not None else 0.0
                        final_model_name = "安全在庫②'"
                        # 採用モデル（安全在庫②'）に上限カットが適用されたかチェック
                        is_cap_applied = (final_ss2_corrected_quantity is not None and ss2_corrected is not None and final_ss2_corrected_quantity < ss2_corrected)
                    elif adopted_model == "ss3":
                        # 安全在庫③を採用
                        final_safety_stock_quantity = final_ss3_quantity
                        final_safety_stock_days = final_ss3_days
                        final_model_name = "安全在庫③"
                        # 採用モデル（安全在庫③）に上限カットが適用されたかチェック
                        is_cap_applied = (ss3_value is not None and final_ss3_quantity is not None and final_ss3_quantity < ss3_value)
                    else:
                        # その他の場合は安全在庫③を採用（フォールバック）
                        final_safety_stock_quantity = final_ss3_quantity
                        final_safety_stock_days = final_ss3_days
                        final_model_name = "安全在庫③"
                        # 採用モデル（安全在庫③）に上限カットが適用されたかチェック
                        is_cap_applied = (ss3_value is not None and final_ss3_quantity is not None and final_ss3_quantity < ss3_value)
                    
                    # 手順②の結果から現行設定と安全在庫①②③（実績異常値処理前）を取得
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
                    
                    # 月当たり実績を計算（実績異常値処理後のデータから）
                    # 対象期間の月数を計算
                    if len(working_dates) > 0:
                        start_date = working_dates[0]
                        end_date = working_dates[-1]
                        target_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
                        target_months = max(1, target_months)
                    else:
                        target_months = 1
                    
                    # 実績異常値処理後の実績合計を月数で割る
                    corrected_total = corrected_data.sum()
                    monthly_avg_actual = corrected_total / target_months if target_months > 0 else 0.0
                    
                    # 採用補正比率rを取得（安全在庫②'が計算された場合）
                    ratio_r_used = None
                    if final_ss2_corrected_quantity is not None and used_r_source:
                        if used_r_source == "区分別":
                            ratio_r_used = ratio_r_by_category.get('ratio_r', {}).get(abc_category_display)
                        elif used_r_source == "全区分":
                            ratio_r_used = ratio_r_by_category.get('ratio_r_all')
                    
                    # 最終結果を保存
                    result_row = {
                        '商品コード': product_code,
                        'ABC区分': abc_category_display,
                        '月当たり実績': monthly_avg_actual,
                        '現行設定_数量': current_qty,
                        '現行設定_日数': current_days,
                        '安全在庫①_数量': ss1_qty,  # 実績異常値処理前
                        '安全在庫②_数量': ss2_qty,  # 実績異常値処理前
                        '安全在庫③_数量': ss3_before_qty,  # 実績異常値処理前
                        '最終安全在庫①_数量': final_ss1_quantity,  # 実績異常値処理＋上限カット後
                        '最終安全在庫②_数量': final_ss2_quantity,  # 実績異常値処理＋上限カット後
                        '最終安全在庫②\'_数量': final_ss2_corrected_quantity if final_ss2_corrected_quantity is not None else 0.0,  # 実績異常値処理＋条件カット後（全機種で計算）
                        '最終安全在庫③_数量': final_ss3_quantity,  # 実績異常値処理＋上限カット後
                        '安全在庫①_日数': ss1_days,  # 実績異常値処理前
                        '安全在庫②_日数': ss2_days,  # 実績異常値処理前
                        '安全在庫③_日数': ss3_before_days,  # 実績異常値処理前
                        '最終安全在庫①_日数': final_ss1_days,  # 実績異常値処理＋上限カット後
                        '最終安全在庫②_日数': final_ss2_days,  # 実績異常値処理＋上限カット後
                        '最終安全在庫②\'_日数': final_ss2_corrected_days if final_ss2_corrected_days is not None else 0.0,  # 実績異常値処理＋条件カット後（全機種で計算）
                        '最終安全在庫③_日数': final_ss3_days,  # 実績異常値処理＋上限カット後
                        '日当たり実績': daily_actual_mean,
                        '欠品許容率': stockout_tolerance,
                        # 実績異常値処理・計画異常値処理・上限カットのフラグ
                        '実績異常値処理': is_outlier_processed,
                        '上限カット': is_cap_applied,
                        '計画異常値処理': is_plan_anomaly_flag if plan_error_rate is not None else False,
                        '計画誤差率': plan_error_rate,
                        '計画誤差率（実績合計 - 計画合計）': plan_error,
                        '実績合計': actual_total,
                        '計画合計': plan_total,
                        '最終安全在庫_数量': final_safety_stock_quantity,
                        '最終安全在庫_日数': final_safety_stock_days,
                        '採用モデル': final_model_name,
                        '採用補正比率r': ratio_r_used,
                        '採用rソース': used_r_source
                    }
                    final_results.append(result_row)
                    
                except KeyError as e:
                    # KeyErrorの場合は、商品コードがデータに存在しない可能性がある
                    st.warning(f"⚠️ {product_code} の処理でエラーが発生しました: 商品コードがデータに存在しない可能性があります。詳細: {str(e)}")
                    continue
                except Exception as e:
                    # その他のエラーの場合は、エラーの型とメッセージを表示
                    error_type = type(e).__name__
                    st.warning(f"⚠️ {product_code} の処理でエラーが発生しました ({error_type}): {str(e)}")
                    continue
                
                progress_bar.progress((idx + 1) / total_products)
            
            progress_bar.empty()
            
            # 「計画のみ」の商品が存在する場合、警告メッセージを1回だけ表示
            if skipped_count > 0:
                st.markdown(f"""
                <div class="annotation-warning-box">
                    <span class="icon">⚠</span>
                    <div class="text">実績データが存在しない商品が {skipped_count}件 あるため、これらは安全在庫の算出対象外としました。<br>詳細は STEP1 のデータ整合性チェック結果サマリーにて、区分「計画のみ」をご確認ください。</div>
                </div>
                """, unsafe_allow_html=True)
            
            # 結果をDataFrameに変換
            if final_results:
                final_results_df = pd.DataFrame(final_results)
                st.session_state.final_safety_stock_results = final_results_df
                st.markdown(f"""
                <div class="annotation-success-box">
                    <span class="icon">✅</span>
                    <div class="text"><strong>実績異常値処理・計画異常値処理・上限カット完了：</strong>{len(final_results)}機種の処理が完了しました。</div>
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
            
            # 異常値処理（実績異常値／計画異常値／上限カット）の実行結果
            st.markdown('<div class="step-sub-section">異常値処理（実績異常値／計画異常値／上限カット）の実行結果</div>', unsafe_allow_html=True)
            
            # 商品コードの総件数
            total_product_count = len(final_results_df)
            
            # ABC区分別のサマリーを作成
            summary_rows = []
            all_categories = sorted(final_results_df['ABC区分'].unique().tolist())
            
            for category in all_categories:
                category_df = final_results_df[final_results_df['ABC区分'] == category]
                product_count = len(category_df)
                outlier_count = int(category_df['実績異常値処理'].sum())
                cap_count = int(category_df['上限カット'].sum())
                plan_anomaly_count = int(category_df['計画異常値処理'].sum())
                
                # 割合%を計算（ABC区分内の商品コード総件数を分母、小数なしの整数表記）
                outlier_pct = round((outlier_count / product_count * 100) if product_count > 0 else 0.0)
                plan_anomaly_pct = round((plan_anomaly_count / product_count * 100) if product_count > 0 else 0.0)
                cap_pct = round((cap_count / product_count * 100) if product_count > 0 else 0.0)
                
                summary_rows.append({
                    'ABC区分': f"{category}区分",
                    '商品コード件数': f"{product_count}件（{100}%）",
                    '実績異常値処理件数（%）': f"{outlier_count}件（{outlier_pct}%）",
                    '計画異常値処理件数（%）': f"{plan_anomaly_count}件（{plan_anomaly_pct}%）",
                    '上限カット件数（%）': f"{cap_count}件（{cap_pct}%）"
                })
            
            # 合計行を追加
            total_outlier = int(final_results_df['実績異常値処理'].sum())
            total_cap = int(final_results_df['上限カット'].sum())
            total_plan_anomaly = int(final_results_df['計画異常値処理'].sum())
            
            # 合計行の割合%を計算（合計行は必ず100%）
            total_outlier_pct = round((total_outlier / total_product_count * 100) if total_product_count > 0 else 0.0)
            total_plan_anomaly_pct = round((total_plan_anomaly / total_product_count * 100) if total_product_count > 0 else 0.0)
            total_cap_pct = round((total_cap / total_product_count * 100) if total_product_count > 0 else 0.0)
            
            summary_rows.append({
                'ABC区分': '合計',
                '商品コード件数': f"{total_product_count}件（{100}%）",
                '実績異常値処理件数（%）': f"{total_outlier}件（{total_outlier_pct}%）",
                '計画異常値処理件数（%）': f"{total_plan_anomaly}件（{total_plan_anomaly_pct}%）",
                '上限カット件数（%）': f"{total_cap}件（{total_cap_pct}%）"
            })
            
            summary_df = pd.DataFrame(summary_rows)
            # 列順を指定（商品コード件数、実績異常値処理件数（%）、計画異常値処理件数（%）、上限カット件数（%））
            summary_df = summary_df[['ABC区分', '商品コード件数', '実績異常値処理件数（%）', '計画異常値処理件数（%）', '上限カット件数（%）']]
            
            # 合計行にスタイルを適用（薄緑背景・緑字）
            def style_summary_table(row):
                """合計行にスタイルを適用"""
                if row['ABC区分'] == '合計':
                    return ['background-color: #E8F5E9; color: #2E7D32'] * len(row)
                return [''] * len(row)
            
            styled_summary_df = summary_df.style.apply(style_summary_table, axis=1)
            st.dataframe(styled_summary_df, width='stretch', hide_index=True)
            
            # テーブル直下の補足説明を追加
            st.caption("※ カッコ内の％は、各 ABC区分内の商品コード総件数に対する割合です。算出式：割合（%）＝ 各処理件数 ÷ 当該 ABC区分の商品コード総件数 × 100")
            
            # 詳細データ（折り畳み式、デフォルト：非表示）
            with st.expander("詳細データを表示", expanded=False):
                # いずれかの処理が行われた商品のみを表示
                processed_df = final_results_df[
                    (final_results_df['実績異常値処理']) |
                    (final_results_df['上限カット']) |
                    (final_results_df['計画異常値処理'])
                ].copy()
                
                if not processed_df.empty:
                    # デフォルトソート：第1キー：ABC区分（A → B → C → … → Z）、第2キー：実績合計（昇順）
                    # ABC区分のソート順を定義（A, B, C, ..., Z, その他）
                    def get_abc_sort_key(abc_value):
                        """ABC区分のソートキーを取得"""
                        if pd.isna(abc_value) or abc_value == '' or abc_value == '-':
                            return (999, '')  # 未分類は最後
                        abc_str = str(abc_value).strip()
                        if len(abc_str) == 1 and abc_str.isalpha():
                            return (ord(abc_str.upper()), abc_str)
                        return (998, abc_str)  # その他の区分
                    
                    # ソート実行
                    processed_df['_abc_sort_key'] = processed_df['ABC区分'].apply(get_abc_sort_key)
                    processed_df = processed_df.sort_values(
                        by=['_abc_sort_key', '実績合計'],
                        ascending=[True, True]
                    ).reset_index(drop=True)
                    processed_df = processed_df.drop(columns=['_abc_sort_key'])
                    
                    # 表示用の列を選択（処理順に基づく順序）
                    detail_columns = [
                        '商品コード', 'ABC区分',
                        '実績異常値処理', '計画異常値処理',
                        '上限カット'
                    ]
                    detail_df = processed_df[detail_columns].copy()
                    
                    # ABC区分のフォーマット（A → A区分）
                    def format_abc_category_with_suffix(abc_value):
                        """ABC区分を「A区分」形式に変換"""
                        if pd.isna(abc_value) or abc_value is None:
                            return "未分類"
                        category_str = str(abc_value).strip()
                        if category_str == "" or category_str.lower() == "nan" or category_str == "-":
                            return "未分類"
                        # 既に「区分」が含まれている場合はそのまま返す
                        if "区分" in category_str:
                            return category_str
                        return f"{category_str}区分"
                    
                    detail_df['ABC区分'] = detail_df['ABC区分'].apply(format_abc_category_with_suffix)
                    
                    # フラグ列を表示用に変換（実施：✔ 実施、未実施：ー）
                    def format_processing_flag(value):
                        """処理フラグを表示用に変換"""
                        if value:
                            return '✔ 実施'
                        else:
                            return 'ー'
                    
                    detail_df['実績異常値処理'] = detail_df['実績異常値処理'].apply(format_processing_flag)
                    detail_df['計画異常値処理'] = detail_df['計画異常値処理'].apply(format_processing_flag)
                    detail_df['上限カット'] = detail_df['上限カット'].apply(format_processing_flag)
                    
                    # スタイル設定：実施フラグに薄緑の背景色を適用
                    def style_processing_cells(val):
                        """処理状況列のスタイル設定"""
                        if val == '✔ 実施':
                            return 'background-color: #E8F5E9; color: #2E7D32;'  # 薄緑背景、緑文字
                        return ''
                    
                    # スタイルを適用（処理状況列）
                    styled_df = detail_df.style.applymap(
                        style_processing_cells,
                        subset=['実績異常値処理', '計画異常値処理', '上限カット']
                    )
                    
                    # テーブルヘッダーのスタイル設定
                    header_styles = [
                        {
                            'selector': 'thead th',
                            'props': [
                                ('background-color', '#F5F5F5'),
                                ('border', '1px solid #DDDDDD'),
                                ('text-align', 'center'),
                                ('font-weight', 'bold'),
                                ('padding', '8px 4px')
                            ]
                        },
                        {
                            'selector': 'tbody td',
                            'props': [
                                ('border', '1px solid #DDDDDD'),
                                ('padding', '8px 4px')
                            ]
                        }
                    ]
                    
                    styled_df = styled_df.set_table_styles(header_styles)
                    
                    st.dataframe(styled_df, width='stretch', hide_index=True)
                else:
                    st.info("実績異常値処理・計画異常値処理・上限カットが実施された商品はありません。")
            
            st.divider()
            
            # ABC区分別_安全在庫比較マトリクス（異常値処理後）を表示
            # 表示用の列を準備：現行設定、安全在庫②'、安全在庫③、採用モデル
            # 前提0)に基づき、すべて異常値処理+上限カット後データを使用
            display_df = final_results_df.copy()
            # 採用モデルの数量・日数を追加
            display_df['採用モデル_数量'] = display_df['最終安全在庫_数量']
            display_df['採用モデル_日数'] = display_df['最終安全在庫_日数']
            # 安全在庫②'の列名を統一（'最終安全在庫②\'_数量' → '安全在庫②\'_数量'）
            # 全機種で計算されているはずなので、存在しない場合は0で埋める
            if '最終安全在庫②\'_数量' in display_df.columns:
                display_df['安全在庫②\'_数量'] = display_df['最終安全在庫②\'_数量'].fillna(0)
                display_df['安全在庫②\'_日数'] = display_df['最終安全在庫②\'_日数'].fillna(0)
            else:
                # 列が存在しない場合は0で埋める（全機種で計算されていない場合）
                display_df['安全在庫②\'_数量'] = 0.0
                display_df['安全在庫②\'_日数'] = 0.0
            # 安全在庫①②③の列名を統一（すべて上限カット後データを使用）
            display_df['安全在庫①_数量'] = display_df['最終安全在庫①_数量'].fillna(0)
            display_df['安全在庫①_日数'] = display_df['最終安全在庫①_日数'].fillna(0)
            display_df['安全在庫②_数量'] = display_df['最終安全在庫②_数量']
            display_df['安全在庫②_日数'] = display_df['最終安全在庫②_日数']
            display_df['安全在庫③_数量'] = display_df['最終安全在庫③_数量']
            display_df['安全在庫③_日数'] = display_df['最終安全在庫③_日数']
            
            if 'ABC区分' in display_df.columns:
                st.markdown('<div class="step-sub-section">ABC区分別_安全在庫比較マトリクス（異常値処理後）</div>', unsafe_allow_html=True)
                # 異常値処理前のデータを取得（現行設定の集計用）
                before_results_df = st.session_state.get('all_products_results')
                display_abc_matrix_comparison_after(display_df, before_results_df=before_results_df, key_prefix="abc_matrix_after")
                
                # 受注量の多い商品順 安全在庫比較グラフ（実績異常値処理・計画異常値処理・上限カット後）を追加
                # Before/Afterを1つのグラフに統合して表示
                st.markdown("""
                <div class="step-middle-section">
                    <p>受注量の多い商品順 安全在庫 比較グラフ（異常値処理後）</p>
                </div>
                """, unsafe_allow_html=True)
                st.caption("※ 安全在庫モデルを「現行設定」「安全在庫①」「安全在庫②」「安全在庫②'」「安全在庫③」「採用モデル」から選択してください。（初期値：採用モデル）")
                
                # 安全在庫タイプ選択UI（異常値処理後用）
                col1, col2 = st.columns([1, 3])
                with col1:
                    safety_stock_type_after = st.selectbox(
                        "安全在庫モデル",
                        options=["current", "ss1", "ss2", "ss2_corrected", "ss3", "adopted"],
                        format_func=lambda x: {
                            "current": "現行設定",
                            "ss1": "安全在庫①",
                            "ss2": "安全在庫②",
                            "ss2_corrected": "安全在庫②'",
                            "ss3": "安全在庫③",
                            "adopted": "採用モデル"
                        }[x],
                        index=5,  # デフォルトは採用モデル
                        key="safety_stock_type_after"
                    )
                
                with col2:
                    type_descriptions = {
                        "current": "<strong>【現行設定】</strong> 現行設定している安全在庫",
                        "ss1": "<strong>【安全在庫①】</strong> 一般的な理論モデル",
                        "ss2": "<strong>【安全在庫②】</strong> 実績バラつき実測モデル",
                        "ss2_corrected": "<strong>【安全在庫②'】</strong> 安全在庫②に計画誤差を加味した補正モデル",
                        "ss3": "<strong>【安全在庫③】</strong> 計画誤差実測モデル（推奨）",
                        "adopted": "<strong>【採用モデル】</strong> 計画誤差率に応じて採用したモデル（安全在庫③ または ②'）"
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
                    st.plotly_chart(fig, use_container_width=True, key="order_volume_comparison_chart_after", config={'displayModeBar': True, 'displaylogo': False})
                    
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
            
            # 詳細データ（折り畳み式、デフォルト：非表示）
            with st.expander("詳細データを表示", expanded=False):
                # 表示用のDataFrameを作成
                display_detail_df = final_results_df.copy()
                
                # 採用モデル在庫の数量・日数を追加（最終安全在庫_数量・日数を使用）
                display_detail_df['採用モデル在庫_数量'] = display_detail_df['最終安全在庫_数量']
                display_detail_df['採用モデル在庫_日数'] = display_detail_df['最終安全在庫_日数']
                
                # 安全在庫②'の列名を統一（'最終安全在庫②\'_数量' → '安全在庫②\'_数量'）
                if '最終安全在庫②\'_数量' in display_detail_df.columns:
                    display_detail_df['安全在庫②\'_数量'] = display_detail_df['最終安全在庫②\'_数量']
                    display_detail_df['安全在庫②\'_日数'] = display_detail_df['最終安全在庫②\'_日数']
                else:
                    display_detail_df['安全在庫②\'_数量'] = None
                    display_detail_df['安全在庫②\'_日数'] = None
                
                # 安全在庫①②③の列名を統一（異常値処理後）
                display_detail_df['安全在庫①_数量'] = display_detail_df['最終安全在庫①_数量']
                display_detail_df['安全在庫①_日数'] = display_detail_df['最終安全在庫①_日数']
                display_detail_df['安全在庫②_数量'] = display_detail_df['最終安全在庫②_数量']
                display_detail_df['安全在庫②_日数'] = display_detail_df['最終安全在庫②_日数']
                display_detail_df['安全在庫③_数量'] = display_detail_df['最終安全在庫③_数量']
                display_detail_df['安全在庫③_日数'] = display_detail_df['最終安全在庫③_日数']
                
                # 列名を変更（異常処理後を明示）
                if '月当たり実績' in display_detail_df.columns:
                    display_detail_df = display_detail_df.rename(columns={'月当たり実績': '月当たり実績（異常処理後）'})
                if '日当たり実績' in display_detail_df.columns:
                    display_detail_df = display_detail_df.rename(columns={'日当たり実績': '日当たり実績（異常処理後）'})
                
                # 稼働日数を追加（データローダーから取得）
                try:
                    if st.session_state.uploaded_data_loader is not None:
                        data_loader = st.session_state.uploaded_data_loader
                    else:
                        data_loader = DataLoader("data/日次計画データ.csv", "data/日次実績データ.csv")
                        data_loader.load_data()
                    working_dates = data_loader.get_working_dates()
                    working_days_count = len(working_dates)
                    display_detail_df['稼働日数'] = working_days_count
                except:
                    display_detail_df['稼働日数'] = None
                
                # 月当たり実績（異常処理後）で降順ソート
                if '月当たり実績（異常処理後）' in display_detail_df.columns:
                    display_detail_df = display_detail_df.sort_values('月当たり実績（異常処理後）', ascending=False).reset_index(drop=True)
                
                # 列順を指定して並び替え（要件に基づく順序）
                column_order = [
                    '商品コード',
                    'ABC区分',
                    '月当たり実績（異常処理後）',
                    '現行設定_数量',
                    '安全在庫①_数量',
                    '安全在庫②_数量',
                    '安全在庫②\'_数量',
                    '安全在庫③_数量',
                    '採用モデル在庫_数量',
                    '現行設定_日数',
                    '安全在庫①_日数',
                    '安全在庫②_日数',
                    '安全在庫②\'_日数',
                    '安全在庫③_日数',
                    '採用モデル在庫_日数',
                    '採用モデル',
                    '計画誤差率',
                    '計画合計',
                    '実績合計',
                    '採用補正比率r',
                    '採用rソース',
                    '欠品許容率',
                    '稼働日数',
                    '日当たり実績（異常処理後）'
                ]
                
                # 列名のマッピング（実際の列名に合わせる）
                column_mapping = {
                    '採用補正比率r': '採用補正比率r',
                    '採用rソース': '採用rソース'
                }
                
                # 存在する列のみを選択
                available_columns = []
                for col in column_order:
                    if col in display_detail_df.columns:
                        available_columns.append(col)
                    elif col in column_mapping and column_mapping[col] in display_detail_df.columns:
                        available_columns.append(column_mapping[col])
                
                display_detail_df_display = display_detail_df[available_columns]
                # 横スクロールを有効化（width='stretch'で自動的に横スクロール可能）
                st.dataframe(display_detail_df_display, width='stretch', hide_index=True)
            
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
            <div class="step-description">手順③で確定した最終安全在庫を、SCP 登録用データ（CSV 形式）として出力します。</div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("安全在庫登録データを作成する", type="primary", width='stretch'):
                # 登録用データを作成（最終安全在庫を使用）
                registration_df = final_results_df[[
                    '商品コード', 'ABC区分', 
                    '最終安全在庫_数量', '最終安全在庫_日数',
                    '採用モデル',
                    '現行設定_数量', '現行設定_日数'
                ]].copy()
                
                # 列名は変更不要（そのまま使用）
                
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
                
                # SCP登録用データを作成（商品コードと最終安全在庫月数）
                scp_registration_df = pd.DataFrame({
                    '商品コード': registration_df['商品コード'],
                    '安全在庫月数': registration_df['最終安全在庫_日数'] / 20
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
                st.caption("※「商品コード」と「安全在庫月数」のみをダウンロードします。安全在庫月数は「最終安全在庫_日数」÷20 で算出しています。")
                
                # 登録データのプレビュー（ダウンロード対象と同じ内容を表示）
                st.markdown('<div class="step-sub-section">登録データプレビュー</div>', unsafe_allow_html=True)
                # テーブルの横幅をさらにコンパクト化し、左寄せで表示（現在の約半分の幅）
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.dataframe(scp_registration_df, width='stretch', hide_index=True)


# ========================================
# STEP3専用のUIヘルパー関数
# ========================================

def display_abc_matrix_comparison_after(results_df, before_results_df=None, key_prefix="abc_matrix"):
    """
    ABC区分別 安全在庫比較結果をマトリクス形式で表示（異常値処理後用）
    
    Args:
        results_df: 全機種の安全在庫算出結果DataFrame（異常値処理後）
        before_results_df: 異常値処理前のDataFrame（現行設定の集計用、オプション）
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
    
    # 安全在庫タイプの定義（表示名、日数列名、数量列名）- 異常値処理後用
    ss_types = [
        ('現行設定', '現行設定_日数', '現行設定_数量'),
        ('安全在庫②\'', '安全在庫②\'_日数', '安全在庫②\'_数量'),
        ('安全在庫③', '安全在庫③_日数', '安全在庫③_数量'),
        ('採用モデル', '採用モデル_日数', '採用モデル_数量')
    ]
    
    # マトリクスデータを構築（縦軸：在庫日数ビン、横軸：区分×安全在庫タイプ）
    matrix_rows = []
    
    # 各行（在庫日数ビン）のデータを作成
    for bin_name in bins:
        row_data = {'在庫日数': bin_name}
        
        # 合計ブロック（4列：現行設定、安全在庫②'、安全在庫③、採用モデル）
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
    
    # 表示用DataFrameを新規に構築（必ず2階層MultiIndexに統一）
    # level0：合計 / A区分 / B区分 / C区分
    # level1：現行設定 / 安全在庫②' / 安全在庫③ / 採用モデル
    # 列順を固定：合計 → A区分 → B区分 → C区分、各区分内で 現行設定 → 安全在庫②' → 安全在庫③ → 採用モデル
    
    # 列順を定義（固定）
    display_categories = ['合計'] + [category_labels[cat] for cat in all_categories]
    display_ss_types = ['現行設定', '安全在庫②\'', '安全在庫③', '採用モデル']
    
    # 新しい列構造を作成（2階層MultiIndex）
    new_columns = []
    for category in display_categories:
        for ss_type in display_ss_types:
            new_columns.append((category, ss_type))
    
    # 既存のデータから値を取得して新しいDataFrameを構築
    new_matrix_data = {}
    for category, ss_type in new_columns:
        # 既存のDataFrameから値を取得
        if (category, ss_type) in matrix_df.columns:
            new_matrix_data[(category, ss_type)] = matrix_df[(category, ss_type)]
        else:
            # 列が存在しない場合は0で埋める
            new_matrix_data[(category, ss_type)] = 0
    
    # 新しいDataFrameを作成（必ず2階層MultiIndex）
    matrix_df = pd.DataFrame(new_matrix_data, index=matrix_df.index)
    matrix_df.columns = pd.MultiIndex.from_tuples(matrix_df.columns, names=['区分', '安全在庫タイプ'])
    
    # デバッグログ（本番環境ではコメントアウト）
    # st.write(f"[DEBUG STEP3 異常値処理後 修正後] type(matrix_df.columns): {type(matrix_df.columns)}")
    # st.write(f"[DEBUG STEP3 異常値処理後 修正後] nlevels: {getattr(matrix_df.columns, 'nlevels', 1)}")
    # st.write(f"[DEBUG STEP3 異常値処理後 修正後] columns先頭20件: {matrix_df.columns.tolist()[:20]}")
    # group_headers = list(matrix_df.columns.get_level_values(0))
    # item_headers = list(matrix_df.columns.get_level_values(1))
    # st.write(f"[DEBUG STEP3 異常値処理後] group_headers先頭20件: {group_headers[:20]}")
    # st.write(f"[DEBUG STEP3 異常値処理後] item_headers先頭20件: {item_headers[:20]}")
    # tuple_strings = [h for h in item_headers if isinstance(h, str) and h.startswith('(')]
    # if tuple_strings:
    #     st.write(f"[DEBUG STEP3 異常値処理後] ⚠️ タプル文字列が検出されました: {tuple_strings[:10]}")
    # else:
    #     st.write(f"[DEBUG STEP3 異常値処理後] ✅ item_headersにタプル文字列はありません")
    
    # サマリー行を追加（合計件数、安全在庫_数量、安全在庫_日数）
    # サマリー行も同じ列構造（2階層MultiIndex）を使用
    summary_rows = []
    
    # ss_typeから列名へのマッピング
    ss_type_mapping = {
        '現行設定': ('現行設定_日数', '現行設定_数量'),
        '安全在庫②\'': ('安全在庫②\'_日数', '安全在庫②\'_数量'),
        '安全在庫③': ('安全在庫③_日数', '安全在庫③_数量'),
        '採用モデル': ('採用モデル_日数', '採用モデル_数量')
    }
    
    # 1. 合計件数行
    total_count_row = {'在庫日数': '合計件数'}
    for category in display_categories:
        for ss_type in display_ss_types:
            if category == '合計':
                total_count_row[(category, ss_type)] = len(results_df)
            else:
                # 区分名から元の区分名を取得（例：「A区分」→「A」）
                category_char = category.replace('区分', '')
                category_df = results_df[results_df['ABC区分'] == category_char]
                total_count_row[(category, ss_type)] = len(category_df)
    summary_rows.append(total_count_row)
    
    # 2. 安全在庫数行（四捨五入して整数表示、カンマ区切り）
    ss_quantity_row = {'在庫日数': '安全在庫_数量'}
    for category in display_categories:
        for ss_type in display_ss_types:
            days_col, qty_col = ss_type_mapping.get(ss_type, ('', ''))
            
            if category == '合計':
                target_df = results_df
            else:
                category_char = category.replace('区分', '')
                target_df = results_df[results_df['ABC区分'] == category_char]
            
            # 現行設定の数量合計は処理後の日当たり実績×固定日数で計算
            # 日数は不変だが、数量は処理後の実績で換算するため変動する
            if ss_type == '現行設定':
                # 処理後の日当たり実績を使用（数量合計を処理後実績×固定日数で計算）
                merged_df = target_df
                daily_actual_col = '日当たり実績'  # 処理後の日当たり実績を使用
            else:
                merged_df = target_df
                daily_actual_col = '日当たり実績'
            
            valid_mask = (
                (merged_df[daily_actual_col].notna()) &
                (merged_df[daily_actual_col] > 0) &
                (merged_df[days_col].notna()) &
                (merged_df[days_col] > 0)
            )
            
            if valid_mask.sum() > 0:
                valid_df = merged_df[valid_mask]
                ss_quantity = (valid_df[days_col] * valid_df[daily_actual_col]).sum()
                ss_quantity = round(ss_quantity)  # 四捨五入
            else:
                ss_quantity = 0
            ss_quantity_row[(category, ss_type)] = f"{ss_quantity:,}"  # カンマ区切り
    summary_rows.append(ss_quantity_row)
    
    # 3. 安全在庫_日数行
    ss_days_row = {'在庫日数': '安全在庫_日数'}
    for category in display_categories:
        for ss_type in display_ss_types:
            days_col, qty_col = ss_type_mapping.get(ss_type, ('', ''))
            
            if category == '合計':
                target_df = results_df
            else:
                category_char = category.replace('区分', '')
                target_df = results_df[results_df['ABC区分'] == category_char]
            
            # 現行設定の日数計算も処理後の日当たり実績を使用
            # 数量合計 = 処理後の日当たり実績×固定日数の合計
            # 日当たり実績合計 = 処理後の日当たり実績の合計
            # 加重平均日数 = 数量合計 / 日当たり実績合計
            # これにより、商品コード単位の日数は固定だが、サマリーの加重平均日数は変動する
            merged_df = target_df
            daily_actual_col = '日当たり実績'  # 処理後の日当たり実績を使用
            
            valid_mask = (
                (merged_df[daily_actual_col].notna()) &
                (merged_df[daily_actual_col] > 0) &
                (merged_df[days_col].notna()) &
                (merged_df[days_col] > 0)
            )
            
            if valid_mask.sum() > 0:
                valid_df = merged_df[valid_mask]
                total_ss_quantity = (valid_df[days_col] * valid_df[daily_actual_col]).sum()
                total_daily_actual = valid_df[daily_actual_col].sum()
                ss_days = total_ss_quantity / total_daily_actual if total_daily_actual > 0 else 0
            else:
                ss_days = 0
            ss_days_row[(category, ss_type)] = f"{ss_days:.1f}日"
    summary_rows.append(ss_days_row)
    
    # サマリー行をマトリクスに追加（空白行は追加しない）
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        summary_df = summary_df.set_index('在庫日数')
        
        # サマリー行も同じ列構造（2階層MultiIndex）を使用
        summary_df.columns = pd.MultiIndex.from_tuples(summary_df.columns, names=['区分', '安全在庫タイプ'])
        
        # 列順を統一（matrix_dfと同じ順序）
        summary_df = summary_df.reindex(columns=matrix_df.columns, fill_value=0)
        
        # pd.concatの後でもMultiIndexを維持するため、事前に確認
        if not isinstance(matrix_df.columns, pd.MultiIndex):
            matrix_df.columns = pd.MultiIndex.from_tuples(
                list(matrix_df.columns),
                names=["区分", "項目"]
            )
        if not isinstance(summary_df.columns, pd.MultiIndex):
            summary_df.columns = pd.MultiIndex.from_tuples(
                list(summary_df.columns),
                names=["区分", "項目"]
            )
        
        matrix_df = pd.concat([matrix_df, summary_df])
        
        # pd.concatの後でもMultiIndexが維持されていることを確認
        if not isinstance(matrix_df.columns, pd.MultiIndex):
            matrix_df.columns = pd.MultiIndex.from_tuples(
                list(matrix_df.columns),
                names=["区分", "項目"]
            )
        
        # PyArrowの警告を解消するため、すべての列を文字列型に変換
        # カンマ区切りの数値文字列が含まれているため、明示的に文字列型に変換
        for col in matrix_df.columns:
            matrix_df[col] = matrix_df[col].astype(str)
    
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
    
    # 【必須修正】表示直前でdf_to_showに統一し、columnsを必ずMultiIndexに変換
    df_to_show = matrix_df
    
    # 1) 必ず MultiIndex 化
    if not isinstance(df_to_show.columns, pd.MultiIndex):
        cols = list(df_to_show.columns)  # 期待：[(区分, 項目), ...]
        lvl0 = [c[0] for c in cols]
        lvl1 = [c[1] for c in cols]
        
        # 2) 半角アポストロフィを禁止（Streamlitがrepr表示に化ける可能性があるため）
        lvl1 = [s.replace("安全在庫②'", "安全在庫②′") for s in lvl1]  # PRIME推奨
        
        df_to_show.columns = pd.MultiIndex.from_arrays(
            [lvl0, lvl1],
            names=["区分", "項目"]
        )
    else:
        # 既にMultiIndexの場合でも、level1の'を置換して再生成
        lvl0 = df_to_show.columns.get_level_values(0).tolist()
        lvl1 = [s.replace("安全在庫②'", "安全在庫②′") for s in df_to_show.columns.get_level_values(1).tolist()]
        df_to_show.columns = pd.MultiIndex.from_arrays(
            [lvl0, lvl1],
            names=["区分", "項目"]
        )
    
    # 3) 再発防止：タプル文字列っぽい要素が level1 に残っていたら止める
    bad_chars = set("()'\",")
    lvl1_chk = [str(x) for x in df_to_show.columns.get_level_values(1).tolist()]
    assert not any(any(ch in s for ch in bad_chars) for s in lvl1_chk), f"level1に禁止文字が残っています: {lvl1_chk[:10]}"
    
    # assertで2段ヘッダ構造を保証
    assert isinstance(df_to_show.columns, pd.MultiIndex)
    assert df_to_show.columns.nlevels == 2
    
    # 4) Stylerでスタイル適用（異常値処理前のコードを複製）
    styled_df = df_to_show.style
    
    # 行・列ヘッダのデザイン統一（背景色#F5F5F5、罫線#DDDDDD）
    table_styles = [
        {
            'selector': 'thead th',
            'props': [
                ('background-color', '#F5F5F5'),
                ('border', '1px solid #DDDDDD'),
                ('border-collapse', 'collapse')
            ]
        },
        {
            'selector': 'tbody th',
            'props': [
                ('background-color', '#F5F5F5'),
                ('border', '1px solid #DDDDDD'),
                ('border-collapse', 'collapse')
            ]
        },
        {
            'selector': 'td',
            'props': [
                ('border', '1px solid #DDDDDD'),
                ('border-collapse', 'collapse')
            ]
        }
    ]
    
    # ① 上位ヘッダ（区分ラベル）の視認性強調：上段MultiIndexヘッダの下側に太線を追加
    table_styles.append({
        'selector': 'thead th.level0',
        'props': [
            ('border-bottom', '3px solid #BBBBBB')
        ]
    })
    
    # ② 区分境界線をわずかに強調：各区分ブロック先頭列の左側縦線を2px #BBBBBBに
    # 列構造：インデックス列(1) + 合計ブロック(4列) + 各区分ブロック(各4列)
    # 合計ブロックの先頭列は2列目（インデックス列を除く）
    # A区分ブロックの先頭列は6列目（合計4列 + インデックス列1列）
    # B区分ブロックの先頭列は10列目（合計4列 + A区分4列 + インデックス列1列）
    ss_types_count = len(ss_types)  # 4列（現行設定、安全在庫②'、安全在庫③、採用モデル）
    
    # 合計ブロックの先頭列（2列目）
    table_styles.append({
        'selector': 'thead th.level0:nth-child(2), thead th.level1:nth-child(2), td:nth-child(2)',
        'props': [
            ('border-left', '2px solid #BBBBBB')
        ]
    })
    
    # 各区分ブロックの先頭列を計算
    # 合計ブロック: 列2-5（インデックス列を除く）
    # A区分ブロック: 列6-9
    # B区分ブロック: 列10-13
    # C区分ブロック: 列14-17
    # 先頭列は 2, 6, 10, 14, ... = 2 + 4*n (n=0,1,2,...)
    # n=0: 合計ブロック（既に追加済み）
    # n=1,2,3,...: 各区分ブロック
    for i in range(len(all_categories)):
        col_position = 2 + (i + 1) * ss_types_count  # インデックス列(1) + 合計ブロック(4) + 区分ブロック数*4
        table_styles.append({
            'selector': f'thead th.level0:nth-child({col_position}), thead th.level1:nth-child({col_position}), td:nth-child({col_position})',
            'props': [
                ('border-left', '2px solid #BBBBBB')
            ]
        })
    
    styled_df = styled_df.set_table_styles(table_styles)
    
    # 区分ごとの色付け（合計、B区分、D区分、F区分...に#F5F5F5、A区分、C区分、E区分...は白）
    def highlight_cols_by_category(col):
        """区分ごとの列色分け（合計と偶数番目の区分に色付け）"""
        # MultiIndexの列名から区分名を取得
        if isinstance(col.name, tuple) and len(col.name) >= 1:
            category_name = col.name[0]  # level0の区分名
        else:
            category_name = str(col.name)
        
        # 合計列は#F5F5F5背景
        if category_name == '合計':
            return ['background-color: #F5F5F5'] * len(col)
        
        # display_categoriesの順序でインデックスを取得
        # display_categories = ['合計'] + [category_labels[cat] for cat in all_categories]
        # 合計=0, A=1, B=2, C=3...なので、B=2, D=4...が偶数番目
        try:
            category_index = display_categories.index(category_name)
        except ValueError:
            # 区分が見つからない場合は白背景
            return ['background-color: #FFFFFF'] * len(col)
        
        # 合計は0番目なので除外（既に処理済み）
        # 偶数番目ブロック（B区分=2, D区分=4...）に#F5F5F5、それ以外は白
        # ただし、合計（0番目）は既に処理済みなので、1番目以降で判定
        if category_index > 0 and (category_index - 1) % 2 == 1:  # 偶数番目の区分（B区分、D区分など）
            return ['background-color: #F5F5F5'] * len(col)  # 薄いグレー背景
        else:  # 奇数番目の区分（A区分、C区分など）または合計以外
            return ['background-color: #FFFFFF'] * len(col)  # 白背景
    
    styled_df = styled_df.apply(highlight_cols_by_category, axis=0)
    
    # KPI行（合計件数、安全在庫_数量、安全在庫_日数）の強調
    def highlight_important_rows(row):
        """KPI行の強調"""
        # 行名を取得（MultiIndexの場合は最初の要素）
        if hasattr(row, 'name'):
            row_name = row.name
            if isinstance(row_name, tuple):
                row_name = row_name[0] if len(row_name) > 0 else str(row_name)
            elif not isinstance(row_name, str):
                row_name = str(row_name)
        else:
            row_name = ''
        
        # KPI行の判定
        if row_name == '合計件数':
            return ['background-color: #E8F5E9; color: #2E7D32; font-weight: normal'] * len(row)
        elif row_name == '安全在庫_数量':
            return ['background-color: #E8F5E9; color: #2E7D32; font-weight: normal'] * len(row)
        elif row_name == '安全在庫_日数':
            return ['background-color: #C8E6C9; color: #2E7D32; font-weight: bold; font-size: 1.1em'] * len(row)
        return [''] * len(row)
    
    styled_df = styled_df.apply(highlight_important_rows, axis=1)
    
    # セル値の右揃えを適用
    styled_df = styled_df.set_properties(**{'text-align': 'right'})
    
    # KPI行のインデックス列も強調するためのCSS
    st.markdown("""
    <style>
    /* マトリクスのインデックス列（項目名）の背景色を統一 */
    div[data-testid="stDataFrame"] table thead th:first-child,
    div[data-testid="stDataFrame"] table tbody tr th {
        background-color: #F5F5F5 !important;
        border: 1px solid #DDDDDD !important;
    }
    /* 「合計件数」「安全在庫_数量」行のインデックス列 */
    div[data-testid="stDataFrame"] table tbody tr:has(td[style*="background-color: #E8F5E9"]) th {
        background-color: #E8F5E9 !important;
        color: #2E7D32 !important;
        font-weight: normal !important;
        border: 1px solid #DDDDDD !important;
    }
    /* 「安全在庫_日数」行のインデックス列 */
    div[data-testid="stDataFrame"] table tbody tr:has(td[style*="background-color: #C8E6C9"]) th {
        background-color: #C8E6C9 !important;
        color: #2E7D32 !important;
        font-weight: bold !important;
        font-size: 1.1em !important;
        border: 1px solid #DDDDDD !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 表示直前で構造保証（assert）
    try:
        assert isinstance(df_to_show.columns, pd.MultiIndex)
        assert df_to_show.columns.nlevels == 2
    except AssertionError as e:
        st.error(f"マトリクスの列構造が不正です: {e}")
        st.stop()
    
    # Streamlitで表示（Stylerオブジェクトを渡すことでスタイルを維持）
    st.dataframe(styled_df, width='stretch', height=500)
    
    # マトリクスの直下に注意文を追加
    st.caption("※ 表内の数値は該当する商品コードの件数です。")
    
    # 注記を展開式で表示（初期状態は閉じた状態）
    with st.expander("ABC区分別_安全在庫比較マトリクスの見方", expanded=False):
        st.markdown("""
        - 表内の数値は、該当する商品コードの件数です。
        - 現行設定_数量が 0、または安全在庫②'/③/採用モデル_数量が算出できない商品コードは、「0日（設定なし）」に分類します。
        - 安全在庫_数量は、各商品コードの［安全在庫_日数 × 日当たり実績］を算出し、全件集計した値です。
        - 安全在庫_日数は、全件集計した［安全在庫_数量］を全件集計した［日当たり実績］で割って求める加重平均です。
        - 安全在庫_日数は「稼働日ベース」です。
        - 在庫日数の区分は、各範囲の上限値を含みます（例：5.0日は「0〜5日」、50.0日は「40〜50日」に分類）。
        """)


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
        
        # PyArrowの警告を解消するため、すべての列を文字列型に変換
        # カンマ区切りの数値文字列が含まれているため、明示的に文字列型に変換
        for col in matrix_df.columns:
            matrix_df[col] = matrix_df[col].astype(str)
    
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
    
    # 行・列ヘッダのデザイン統一（背景色#F5F5F5、罫線#DDDDDD）
    table_styles = [
        {
            'selector': 'thead th',
            'props': [
                ('background-color', '#F5F5F5'),
                ('border', '1px solid #DDDDDD'),
                ('border-collapse', 'collapse')
            ]
        },
        {
            'selector': 'tbody th',
            'props': [
                ('background-color', '#F5F5F5'),
                ('border', '1px solid #DDDDDD'),
                ('border-collapse', 'collapse')
            ]
        },
        {
            'selector': 'td',
            'props': [
                ('border', '1px solid #DDDDDD'),
                ('border-collapse', 'collapse')
            ]
        }
    ]
    
    # ① 上位ヘッダ（区分ラベル）の視認性強調：上段MultiIndexヘッダの下側に太線を追加
    table_styles.append({
        'selector': 'thead th.level0',
        'props': [
            ('border-bottom', '3px solid #BBBBBB')
        ]
    })
    
    # ② 区分境界線をわずかに強調：各区分ブロック先頭列の左側縦線を2px #BBBBBBに
    # 列構造：インデックス列(1) + 合計ブロック(4列) + 各区分ブロック(各4列)
    # 合計ブロックの先頭列は2列目（インデックス列を除く）
    # A区分ブロックの先頭列は6列目（合計4列 + インデックス列1列）
    # B区分ブロックの先頭列は10列目（合計4列 + A区分4列 + インデックス列1列）
    ss_types_count = len(ss_types)  # 4列（現行設定、安全在庫①、安全在庫②、安全在庫③）
    
    # 合計ブロックの先頭列（2列目）
    table_styles.append({
        'selector': 'thead th.level0:nth-child(2), thead th.level1:nth-child(2), td:nth-child(2)',
        'props': [
            ('border-left', '2px solid #BBBBBB')
        ]
    })
    
    # 各区分ブロックの先頭列を計算
    # 合計ブロック: 列2-5（インデックス列を除く）
    # A区分ブロック: 列6-9
    # B区分ブロック: 列10-13
    # C区分ブロック: 列14-17
    # 先頭列は 2, 6, 10, 14, ... = 2 + 4*n (n=0,1,2,...)
    # n=0: 合計ブロック（既に追加済み）
    # n=1,2,3,...: 各区分ブロック
    for i in range(len(all_categories)):
        col_position = 2 + (i + 1) * ss_types_count  # インデックス列(1) + 合計ブロック(4) + 区分ブロック数*4
        table_styles.append({
            'selector': f'thead th.level0:nth-child({col_position}), thead th.level1:nth-child({col_position}), td:nth-child({col_position})',
            'props': [
                ('border-left', '2px solid #BBBBBB')
            ]
        })
    
    styled_matrix = styled_matrix.set_table_styles(table_styles)
    
    # 区分ごとの色付け（合計、B区分、D区分、F区分...に#F5F5F5、A区分、C区分、E区分...は白）
    def highlight_cols_by_category(col):
        """区分ごとの列色分け（合計と偶数番目の区分に色付け）"""
        # MultiIndexの列名から区分名を取得
        if isinstance(col.name, tuple) and len(col.name) >= 1:
            category_name = col.name[0]  # 1行目の区分名
        else:
            category_name = str(col.name)
        
        # 合計列は#F5F5F5背景
        if category_name == '合計':
            return ['background-color: #F5F5F5'] * len(col)
        
        # 区分名から文字部分を抽出（例：「A区分」→「A」）
        category_char = category_name.replace('区分', '')
        
        # 区分のインデックスを取得（A=0, B=1, C=2, ...）
        sorted_categories = sorted([cat for cat in all_categories])
        try:
            category_index = sorted_categories.index(category_char)
        except ValueError:
            # 区分が見つからない場合は白背景
            return ['background-color: #FFFFFF'] * len(col)
        
        # 偶数番目の区分（B区分、D区分など）に#F5F5F5、奇数番目の区分（A区分、C区分など）は白
        if category_index % 2 == 1:  # 偶数番目の区分（B区分、D区分など）
            return ['background-color: #F5F5F5'] * len(col)  # 薄いグレー背景
        else:  # 奇数番目の区分（A区分、C区分など）
            return ['background-color: #FFFFFF'] * len(col)  # 白背景
    
    styled_matrix = styled_matrix.apply(highlight_cols_by_category, axis=0)
    
    # KPI行（合計件数、安全在庫_数量、安全在庫_日数）の強調
    def highlight_important_rows(row):
        """KPI行の強調"""
        # 行名を取得（MultiIndexの場合は最初の要素）
        if hasattr(row, 'name'):
            row_name = row.name
            if isinstance(row_name, tuple):
                row_name = row_name[0] if len(row_name) > 0 else str(row_name)
            elif not isinstance(row_name, str):
                row_name = str(row_name)
        else:
            row_name = ''
        
        # KPI行の判定
        if row_name == '合計件数':
            return ['background-color: #E8F5E9; color: #2E7D32; font-weight: normal'] * len(row)
        elif row_name == '安全在庫_数量':
            return ['background-color: #E8F5E9; color: #2E7D32; font-weight: normal'] * len(row)
        elif row_name == '安全在庫_日数':
            return ['background-color: #C8E6C9; color: #2E7D32; font-weight: bold; font-size: 1.1em'] * len(row)
        return [''] * len(row)
    
    styled_matrix = styled_matrix.apply(highlight_important_rows, axis=1)
    
    # KPI行のインデックス列も強調するためのCSS
    st.markdown("""
    <style>
    /* マトリクスのインデックス列（項目名）の背景色を統一 */
    div[data-testid="stDataFrame"] table thead th:first-child,
    div[data-testid="stDataFrame"] table tbody tr th {
        background-color: #F5F5F5 !important;
        border: 1px solid #DDDDDD !important;
    }
    /* 「合計件数」「安全在庫_数量」行のインデックス列 */
    div[data-testid="stDataFrame"] table tbody tr:has(td[style*="background-color: #E8F5E9"]) th {
        background-color: #E8F5E9 !important;
        color: #2E7D32 !important;
        font-weight: normal !important;
        border: 1px solid #DDDDDD !important;
    }
    /* 「安全在庫_日数」行のインデックス列 */
    div[data-testid="stDataFrame"] table tbody tr:has(td[style*="background-color: #C8E6C9"]) th {
        background-color: #C8E6C9 !important;
        color: #2E7D32 !important;
        font-weight: bold !important;
        font-size: 1.1em !important;
        border: 1px solid #DDDDDD !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Streamlitで表示
    st.dataframe(styled_matrix, width='stretch', height=500)
    
    # マトリクスの直下に注意文を追加
    st.caption("※ 表内の数値は該当する商品コードの件数です。")
    
    # CSV出力ボタン
    # Plotly標準の"Download as CSV"があるため、独自のダウンロードボタンは廃止
    
    # 注記を展開式で表示（初期状態は閉じた状態）
    # マトリクス直下の罫線は削除（滑らかに繋げるため）
    with st.expander("ABC区分別_安全在庫比較マトリクスの見方", expanded=False):
        st.markdown("""
        - 表内の数値は、該当する商品コードの件数です。
        - 現行設定_数量が 0、または安全在庫①/②/③_数量が算出できない商品コードは、「0日（設定なし）」に分類します。
        - 安全在庫_数量は、各商品コードの［安全在庫_日数 × 日当たり実績］を算出し、全件集計した値です。
        - 安全在庫_日数は、全件集計した［安全在庫_数量］を全件集計した［日当たり実績］で割って求める加重平均です。
        - 安全在庫_日数は「稼働日ベース」です。
        - 在庫日数の区分は、各範囲の上限値を含みます（例：5.0日は「0〜5日」、50.0日は「40〜50日」に分類）。
        """)

