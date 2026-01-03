"""
共通ユーティリティ関数
"""

import pandas as pd
import streamlit as st
from typing import Dict, List, Tuple, Optional
from modules.data_loader import DataLoader


def classify_inventory_days_bin(days_value: float) -> str:
    """
    在庫日数をビンに分類
    
    Args:
        days_value: 在庫日数（floatまたはNaN）
    
    Returns:
        str: ビン名
    """
    if pd.isna(days_value) or days_value <= 0:
        return "0日（設定なし）"
    elif days_value < 5:
        return "0〜5日"
    elif days_value < 10:
        return "5〜10日"
    elif days_value < 15:
        return "10〜15日"
    elif days_value < 20:
        return "15〜20日"
    elif days_value < 30:
        return "20〜30日"
    elif days_value < 40:
        return "30〜40日"
    elif days_value < 50:
        return "40〜50日"
    else:
        return "50日以上"


def format_abc_category_for_display(abc_category) -> str:
    """
    ABC区分を表示用に変換（NaNの場合は「未分類」）
    
    Args:
        abc_category: ABC区分（str、float、NaNなど）
    
    Returns:
        str: 表示用のABC区分（NaNの場合は「未分類」）
    """
    if pd.isna(abc_category) or abc_category is None:
        return "未分類"
    category_str = str(abc_category).strip()
    if category_str == "" or category_str.lower() == "nan":
        return "未分類"
    return category_str


def add_abc_category_display_column(df: pd.DataFrame, abc_category_col: str = 'abc_category') -> pd.DataFrame:
    """
    DataFrameにABC区分表示列を追加
    
    Args:
        df: 対象のDataFrame
        abc_category_col: ABC区分の列名（デフォルト: 'abc_category'）
    
    Returns:
        pd.DataFrame: ABC区分表示列が追加されたDataFrame
    """
    df = df.copy()
    if abc_category_col in df.columns:
        df['ABC区分表示'] = df[abc_category_col].apply(format_abc_category_for_display)
    else:
        df['ABC区分表示'] = '未分類'
    return df


def check_has_unclassified_products(df: pd.DataFrame, abc_category_col: str = 'abc_category') -> bool:
    """
    ABC区分がNaNの商品が存在するかチェック
    
    Args:
        df: 対象のDataFrame
        abc_category_col: ABC区分の列名（デフォルト: 'abc_category'）
    
    Returns:
        bool: ABC区分がNaNの商品が1件以上存在する場合True
    """
    if abc_category_col not in df.columns:
        return False
    return df[abc_category_col].isna().any()


def has_existing_abc_data() -> bool:
    """
    セッションに現行ABC区分データが読み込まれているかを判定

    Returns:
        bool: データが存在し、空でない場合にTrue
    """
    existing_df = st.session_state.get('existing_abc_df')
    if existing_df is None:
        return False
    try:
        return not existing_df.empty
    except AttributeError:
        # DataFrame以外が誤って格納された場合はFalse扱い
        return False


def get_representative_products_by_abc(data_loader: DataLoader) -> Dict[str, str]:
    """
    ABC区分ごとの上位機種（代表機種）を自動選定
    
    Args:
        data_loader: DataLoaderインスタンス
        
    Returns:
        Dict[str, str]: ABC区分をキー、商品コードを値とする辞書
    """
    representative_products = {}
    
    try:
        analysis_result, categories, _ = get_abc_analysis_with_fallback(data_loader)
        
        for category in categories:
            category_df = analysis_result[analysis_result['abc_category'] == category].copy()
            if category_df.empty or 'total_actual' not in category_df.columns:
                continue
            top_product = category_df.loc[category_df['total_actual'].idxmax(), 'product_code']
            representative_products[category] = top_product
        
        return representative_products
    
    except Exception as e:
        st.warning(f"代表機種の選定でエラーが発生しました: {str(e)}")
        return representative_products


def get_abc_analysis_with_fallback(
    data_loader: DataLoader,
    product_list: List[str] | None = None,
    analysis_result: pd.DataFrame | None = None
) -> Tuple[pd.DataFrame, List[str], bool]:
    """
    ABC分析結果を取得。存在しない場合や区分が付与できない場合はフォールバックを返す。
    
    Returns:
        Tuple[pd.DataFrame, List[str], bool]: (分析結果, ABC区分一覧, 注意喚起の必要有無)
    """
    if product_list is None:
        try:
            product_list = data_loader.get_product_list()
        except Exception:
            product_list = []
    
    if analysis_result is None:
        analysis_result = None
        if 'abc_analysis_result' in st.session_state and st.session_state.abc_analysis_result is not None:
            analysis_result = st.session_state.abc_analysis_result.get('analysis')
    
    if analysis_result is not None:
        prepared_df = analysis_result.copy()
    else:
        prepared_df = pd.DataFrame(columns=['product_code', 'abc_category', 'total_actual', 'monthly_avg_actual'])
    
    warning_needed = False
    
    if prepared_df.empty:
        warning_needed = True
        prepared_df = _build_fallback_analysis_df(data_loader, product_list)
    
    if 'abc_category' not in prepared_df.columns:
        prepared_df['abc_category'] = None
    
    # ABC区分がNaNの場合は「未分類」として扱う
    prepared_df['abc_category'] = prepared_df['abc_category'].apply(format_abc_category_for_display)
    
    valid_categories = [
        cat for cat in prepared_df['abc_category'].unique()
        if str(cat).strip() != ""
    ]
    valid_categories = sorted(valid_categories)
    
    if not valid_categories:
        warning_needed = True
        prepared_df['abc_category'] = '未分類'
        valid_categories = ['未分類']
    
    return prepared_df, valid_categories, warning_needed


def get_target_product_count(data_loader: 'DataLoader', exclude_plan_only: bool = True, exclude_actual_only: bool = True) -> int | None:
    """
    対象商品コード数を取得（ABC区分がない場合でも取得可能）
    
    Args:
        data_loader: DataLoaderインスタンス
        exclude_plan_only: 「計画のみ」の商品コードを除外するかどうか（デフォルト: True）
        exclude_actual_only: 「実績のみ」の商品コードを除外するかどうか（デフォルト: True）
    
    Returns:
        int | None: 対象商品コード数。取得できない場合はNone
    """
    try:
        # まずABC区分の集計結果から取得を試みる
        abc_analysis_result = st.session_state.get('abc_analysis_result')
        if abc_analysis_result is not None and 'aggregation' in abc_analysis_result:
            aggregation_df = abc_analysis_result['aggregation']
            total_row = aggregation_df[aggregation_df['ABC区分'] == '合計']
            if not total_row.empty:
                if '商品コード数（件数）' in total_row.columns:
                    return int(total_row['商品コード数（件数）'].iloc[0])
                elif 'count' in total_row.columns:
                    return int(total_row['count'].iloc[0])
        
        # ABC区分がない場合、data_loaderから直接取得
        product_list = data_loader.get_product_list()
        
        # 「計画のみ」「実績のみ」の商品コードを除外
        if exclude_plan_only or exclude_actual_only:
            mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
            if mismatch_detail_df is not None and not mismatch_detail_df.empty:
                excluded_codes = set()
                if exclude_plan_only:
                    plan_only_codes = mismatch_detail_df[
                        mismatch_detail_df['区分'] == '計画のみ'
                    ]['商品コード'].tolist()
                    excluded_codes.update(plan_only_codes)
                if exclude_actual_only:
                    actual_only_codes = mismatch_detail_df[
                        mismatch_detail_df['区分'] == '実績のみ'
                    ]['商品コード'].tolist()
                    excluded_codes.update(actual_only_codes)
                product_list = [code for code in product_list if str(code) not in excluded_codes]
        
        return len(product_list) if product_list else None
    except Exception:
        return None


def _build_fallback_analysis_df(data_loader: DataLoader, product_list: List[str]) -> pd.DataFrame:
    """ABC区分が付与できない場合のフォールバックデータを生成"""
    rows = []
    for product_code in product_list:
        total_actual = 0.0
        monthly_avg = 0.0
        try:
            actual_series = data_loader.get_daily_actual(product_code)
            if actual_series is not None:
                total_actual = float(actual_series.sum())
                days = len(actual_series)
                months = max(1, days / 30) if days else 1
                monthly_avg = total_actual / months
        except Exception:
            pass
        rows.append({
            'product_code': product_code,
            'abc_category': '未分類',
            'total_actual': total_actual,
            'monthly_avg_actual': monthly_avg
        })
    
    if not rows:
        return pd.DataFrame(columns=['product_code', 'abc_category', 'total_actual', 'monthly_avg_actual'])
    
    return pd.DataFrame(rows)


def _sync_from_slider(key_prefix: str):
    """スライダーから値を同期"""
    base_key = key_prefix
    slider_key = f"{key_prefix}_slider"
    number_key = f"{key_prefix}_number"
    st.session_state[base_key] = st.session_state[slider_key]
    st.session_state[number_key] = st.session_state[base_key]


def _sync_from_number(key_prefix: str):
    """数値入力から値を同期"""
    base_key = key_prefix
    slider_key = f"{key_prefix}_slider"
    number_key = f"{key_prefix}_number"
    st.session_state[base_key] = st.session_state[number_key]
    st.session_state[slider_key] = st.session_state[base_key]


def slider_with_number_input(
    label: str,
    min_value,
    max_value,
    default_value,
    key_prefix: str,
    *,
    step=1,
    help: str | None = None,
    format: str | None = None
):
    """
    スライダーと数値入力を組み合わせたUIコンポーネント。
    値は st.session_state[key_prefix] に保存され、ステップ間で共有される。
    """
    contains_float = any(isinstance(v, float) for v in (min_value, max_value, default_value, step))
    value_type = float if contains_float else int

    # セッション状態の初期化（存在しない場合のみ）
    if key_prefix not in st.session_state:
        st.session_state[key_prefix] = value_type(default_value)
    
    # ウィジェットのキー
    slider_key = f"{key_prefix}_slider"
    number_key = f"{key_prefix}_number"
    
    # ウィジェットのキーが存在しない場合のみ初期化
    if slider_key not in st.session_state:
        st.session_state[slider_key] = value_type(st.session_state[key_prefix])
    if number_key not in st.session_state:
        st.session_state[number_key] = value_type(st.session_state[key_prefix])

    col_slider, col_input = st.columns([4, 1])
    
    # スライダーの設定
    slider_kwargs = {
        "label": label,
        "min_value": min_value,
        "max_value": max_value,
        "key": slider_key,
        "step": step,
        "help": help,
        "on_change": _sync_from_slider,
        "args": (key_prefix,)
    }
    
    if format is not None:
        slider_kwargs["format"] = format

    slider_value = col_slider.slider(**slider_kwargs)

    # 数値入力の設定
    number_kwargs = {
        "label": " ",
        "min_value": min_value,
        "max_value": max_value,
        "key": number_key,
        "step": step,
        "label_visibility": "collapsed"
    }
    
    if format is not None:
        number_kwargs["format"] = format

    number_value = col_input.number_input(
        on_change=_sync_from_number,
        args=(key_prefix,),
        **number_kwargs
    )

    # 最新値を返す（slider_value/number_valueはいずれも最新セッション値）
    return value_type(st.session_state[key_prefix])


def calculate_plan_error_rate(actual_data: pd.Series, plan_data: pd.Series) -> Tuple[float | None, float, float]:
    """
    計画誤差率を計算
    
    計画誤差率 = (計画合計 - 実績合計) / 実績合計 × 100%
    
    Args:
        actual_data: 日次実績データ（Series）
        plan_data: 日次計画データ（Series）
    
    Returns:
        Tuple[float | None, float, float]: (計画誤差率（%）、計画誤差（計画合計 - 実績合計）、計画合計)
           実績合計が0の場合は計画誤差率はNoneを返す
    """
    actual_total = float(actual_data.sum())
    plan_total = float(plan_data.sum())
    plan_error = plan_total - actual_total
    
    if actual_total == 0:
        return None, plan_error, plan_total
    
    plan_error_rate = (plan_error / actual_total) * 100.0
    return plan_error_rate, plan_error, plan_total


def calculate_weighted_average_plan_error_rate(
    data_loader: 'DataLoader',
    analysis_result: pd.DataFrame | None = None,
    exclude_plan_only: bool = True,
    exclude_actual_only: bool = True
) -> float | None:
    """
    全体計画誤差率（評価用：絶対値・加重平均）を計算
    
    各商品コードの計画誤差率の絶対値を、各商品コードの実績数量合計で加重平均した値
    
    Args:
        data_loader: DataLoaderインスタンス
        analysis_result: ABC分析結果のDataFrame（Noneの場合は全商品コードを使用）
        exclude_plan_only: 「計画のみ」の商品コードを除外するかどうか（デフォルト: True）
        exclude_actual_only: 「実績のみ」の商品コードを除外するかどうか（デフォルト: True）
    
    Returns:
        float | None: 全体計画誤差率（評価用：絶対値・加重平均）（%）。計算できない場合はNone
    """
    # 対象商品コードリストを取得
    if analysis_result is not None:
        product_list = analysis_result['product_code'].tolist()
    else:
        product_list = data_loader.get_product_list()
    
    # 「計画のみ」「実績のみ」の商品コードを除外
    if exclude_plan_only or exclude_actual_only:
        mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
        if mismatch_detail_df is not None and not mismatch_detail_df.empty:
            excluded_codes = set()
            if exclude_plan_only:
                plan_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '計画のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(plan_only_codes)
            if exclude_actual_only:
                actual_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '実績のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(actual_only_codes)
            product_list = [code for code in product_list if str(code) not in excluded_codes]
    
    if not product_list:
        return None
    
    # 各商品コードの計画誤差率の絶対値と実績数量合計を計算
    weighted_sum = 0.0
    total_weight = 0.0
    
    for product_code in product_list:
        try:
            plan_data = data_loader.get_daily_plan(product_code)
            actual_data = data_loader.get_daily_actual(product_code)
            
            # 計画誤差率を計算
            plan_error_rate, _, _ = calculate_plan_error_rate(actual_data, plan_data)
            
            # 実績数量合計を取得（重み）
            actual_total = float(actual_data.sum())
            
            # 計画誤差率が計算可能で、実績数量が0より大きい場合のみ加算
            if plan_error_rate is not None and actual_total > 0:
                # 絶対値を使用して加重平均を計算
                weighted_sum += abs(plan_error_rate) * actual_total
                total_weight += actual_total
        except Exception:
            # エラーが発生した商品コードはスキップ
            continue
    
    # 加重平均を計算
    if total_weight == 0:
        return None
    
    weighted_average = weighted_sum / total_weight
    return weighted_average


def calculate_weighted_average_lead_time_plan_error_rate(
    data_loader: 'DataLoader',
    lead_time_days: int,
    analysis_result: pd.DataFrame | None = None,
    exclude_plan_only: bool = True,
    exclude_actual_only: bool = True
) -> float | None:
    """
    リードタイム期間の全体計画誤差率（評価用：絶対値・加重平均）を計算
    
    各商品コードのリードタイム期間合計（計画・実績）に対する計画誤差率の絶対値を、
    各商品コードの実績合計で加重平均した値
    
    Args:
        data_loader: DataLoaderインスタンス
        lead_time_days: リードタイム日数（整数）
        analysis_result: ABC分析結果のDataFrame（Noneの場合は全商品コードを使用）
        exclude_plan_only: 「計画のみ」の商品コードを除外するかどうか（デフォルト: True）
        exclude_actual_only: 「実績のみ」の商品コードを除外するかどうか（デフォルト: True）
    
    Returns:
        float | None: リードタイム期間の全体計画誤差率（評価用：絶対値・加重平均）（%）。計算できない場合はNone
    """
    # 対象商品コードリストを取得
    if analysis_result is not None:
        product_list = analysis_result['product_code'].tolist()
    else:
        product_list = data_loader.get_product_list()
    
    # 「計画のみ」「実績のみ」の商品コードを除外
    if exclude_plan_only or exclude_actual_only:
        mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
        if mismatch_detail_df is not None and not mismatch_detail_df.empty:
            excluded_codes = set()
            if exclude_plan_only:
                plan_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '計画のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(plan_only_codes)
            if exclude_actual_only:
                actual_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '実績のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(actual_only_codes)
            product_list = [code for code in product_list if str(code) not in excluded_codes]
    
    if not product_list:
        return None
    
    # 各商品コードのリードタイム期間の計画誤差率の絶対値と実績合計を計算
    weighted_sum = 0.0
    total_weight = 0.0
    
    for product_code in product_list:
        try:
            plan_data = data_loader.get_daily_plan(product_code)
            actual_data = data_loader.get_daily_actual(product_code)
            
            # リードタイム期間の計画合計と実績合計を計算（1日ずつスライド）
            plan_sums = plan_data.rolling(window=lead_time_days).sum().dropna()
            actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
            
            # 共通インデックスを取得
            common_idx = plan_sums.index.intersection(actual_sums.index)
            if len(common_idx) == 0:
                continue
            
            plan_sums_common = plan_sums.loc[common_idx]
            actual_sums_common = actual_sums.loc[common_idx]
            
            # リードタイム期間の計画誤差率を計算
            # 計画誤差率 = (実績合計 - 計画合計) ÷ 実績合計 × 100%
            actual_total = float(actual_sums_common.sum())
            plan_total = float(plan_sums_common.sum())
            
            if actual_total == 0:
                continue
            
            plan_error_rate = ((actual_total - plan_total) / actual_total) * 100.0
            
            # 実績合計を取得（重み）
            # リードタイム期間の実績合計の合計を使用
            # 絶対値を使用して加重平均を計算
            if actual_total > 0:
                weighted_sum += abs(plan_error_rate) * actual_total
                total_weight += actual_total
        except Exception:
            # エラーが発生した商品コードはスキップ
            continue
    
    # 加重平均を計算
    if total_weight == 0:
        return None
    
    weighted_average = weighted_sum / total_weight
    return weighted_average


def calculate_weighted_average_plan_error_rate_by_abc_category(
    data_loader: 'DataLoader',
    abc_category: str,
    analysis_result: pd.DataFrame | None = None,
    exclude_plan_only: bool = True,
    exclude_actual_only: bool = True
) -> Tuple[float | None, int]:
    """
    指定されたABC区分の計画誤差率（評価用：絶対値・加重平均）を計算
    
    各商品コードの計画誤差率の絶対値を、各商品コードの実績数量合計で加重平均した値
    
    Args:
        data_loader: DataLoaderインスタンス
        abc_category: ABC区分（例：'A', 'B', 'C', 'D'）
        analysis_result: ABC分析結果のDataFrame（Noneの場合は全商品コードを使用）
        exclude_plan_only: 「計画のみ」の商品コードを除外するかどうか（デフォルト: True）
        exclude_actual_only: 「実績のみ」の商品コードを除外するかどうか（デフォルト: True）
    
    Returns:
        Tuple[float | None, int]: (ABC区分の計画誤差率（評価用：絶対値・加重平均）（%）、対象商品コード数)
            計算できない場合はNone、商品コード数は0
    """
    # ABC分析結果を取得
    if analysis_result is None:
        analysis_result, _, _ = get_abc_analysis_with_fallback(data_loader)
    
    if analysis_result is None or analysis_result.empty:
        return None, 0
    
    # ABC区分でフィルタリング
    category_df = analysis_result[analysis_result['abc_category'] == abc_category].copy()
    
    if category_df.empty:
        return None, 0
    
    # 対象商品コードリストを取得
    product_list = category_df['product_code'].tolist()
    
    # 「計画のみ」「実績のみ」の商品コードを除外
    if exclude_plan_only or exclude_actual_only:
        mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
        if mismatch_detail_df is not None and not mismatch_detail_df.empty:
            excluded_codes = set()
            if exclude_plan_only:
                plan_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '計画のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(plan_only_codes)
            if exclude_actual_only:
                actual_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '実績のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(actual_only_codes)
            product_list = [code for code in product_list if str(code) not in excluded_codes]
    
    if not product_list:
        return None, 0
    
    # 各商品コードの計画誤差率の絶対値と実績数量合計を計算
    weighted_sum = 0.0
    total_weight = 0.0
    
    for product_code in product_list:
        try:
            plan_data = data_loader.get_daily_plan(product_code)
            actual_data = data_loader.get_daily_actual(product_code)
            
            # 計画誤差率を計算
            plan_error_rate, _, _ = calculate_plan_error_rate(actual_data, plan_data)
            
            # 実績数量合計を取得（重み）
            actual_total = float(actual_data.sum())
            
            # 計画誤差率が計算可能で、実績数量が0より大きい場合のみ加算
            if plan_error_rate is not None and actual_total > 0:
                # 絶対値を使用して加重平均を計算
                weighted_sum += abs(plan_error_rate) * actual_total
                total_weight += actual_total
        except Exception:
            # エラーが発生した商品コードはスキップ
            continue
    
    # 加重平均を計算
    if total_weight == 0:
        return None, len(product_list)
    
    weighted_average = weighted_sum / total_weight
    return weighted_average, len(product_list)


def calculate_weighted_average_lead_time_plan_error_rate_by_abc_category(
    data_loader: 'DataLoader',
    abc_category: str,
    lead_time_days: int,
    analysis_result: pd.DataFrame | None = None,
    exclude_plan_only: bool = True,
    exclude_actual_only: bool = True
) -> Tuple[float | None, int]:
    """
    指定されたABC区分のリードタイム期間の計画誤差率（評価用：絶対値・加重平均）を計算
    
    各商品コードのリードタイム期間合計（計画・実績）に対する計画誤差率の絶対値を、
    各商品コードの実績合計で加重平均した値
    
    Args:
        data_loader: DataLoaderインスタンス
        abc_category: ABC区分（例：'A', 'B', 'C', 'D'）
        lead_time_days: リードタイム日数（整数）
        analysis_result: ABC分析結果のDataFrame（Noneの場合は全商品コードを使用）
        exclude_plan_only: 「計画のみ」の商品コードを除外するかどうか（デフォルト: True）
        exclude_actual_only: 「実績のみ」の商品コードを除外するかどうか（デフォルト: True）
    
    Returns:
        Tuple[float | None, int]: (ABC区分のリードタイム期間の計画誤差率（評価用：絶対値・加重平均）（%）、対象商品コード数)
            計算できない場合はNone、商品コード数は0
    """
    # ABC分析結果を取得
    if analysis_result is None:
        analysis_result, _, _ = get_abc_analysis_with_fallback(data_loader)
    
    if analysis_result is None or analysis_result.empty:
        return None, 0
    
    # ABC区分でフィルタリング
    category_df = analysis_result[analysis_result['abc_category'] == abc_category].copy()
    
    if category_df.empty:
        return None, 0
    
    # 対象商品コードリストを取得
    product_list = category_df['product_code'].tolist()
    
    # 「計画のみ」「実績のみ」の商品コードを除外
    if exclude_plan_only or exclude_actual_only:
        mismatch_detail_df = st.session_state.get('product_code_mismatch_detail_df')
        if mismatch_detail_df is not None and not mismatch_detail_df.empty:
            excluded_codes = set()
            if exclude_plan_only:
                plan_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '計画のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(plan_only_codes)
            if exclude_actual_only:
                actual_only_codes = mismatch_detail_df[
                    mismatch_detail_df['区分'] == '実績のみ'
                ]['商品コード'].tolist()
                excluded_codes.update(actual_only_codes)
            product_list = [code for code in product_list if str(code) not in excluded_codes]
    
    if not product_list:
        return None, 0
    
    # 各商品コードのリードタイム期間の計画誤差率の絶対値と実績合計を計算
    weighted_sum = 0.0
    total_weight = 0.0
    
    for product_code in product_list:
        try:
            plan_data = data_loader.get_daily_plan(product_code)
            actual_data = data_loader.get_daily_actual(product_code)
            
            # リードタイム期間の計画合計と実績合計を計算（1日ずつスライド）
            plan_sums = plan_data.rolling(window=lead_time_days).sum().dropna()
            actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
            
            # 共通インデックスを取得
            common_idx = plan_sums.index.intersection(actual_sums.index)
            if len(common_idx) == 0:
                continue
            
            plan_sums_common = plan_sums.loc[common_idx]
            actual_sums_common = actual_sums.loc[common_idx]
            
            # リードタイム期間の計画誤差率を計算
            # 計画誤差率 = (実績合計 - 計画合計) ÷ 実績合計 × 100%
            actual_total = float(actual_sums_common.sum())
            plan_total = float(plan_sums_common.sum())
            
            if actual_total == 0:
                continue
            
            plan_error_rate = ((actual_total - plan_total) / actual_total) * 100.0
            
            # 実績合計を取得（重み）
            # リードタイム期間の実績合計の合計を使用
            # 絶対値を使用して加重平均を計算
            if actual_total > 0:
                weighted_sum += abs(plan_error_rate) * actual_total
                total_weight += actual_total
        except Exception:
            # エラーが発生した商品コードはスキップ
            continue
    
    # 加重平均を計算
    if total_weight == 0:
        return None, len(product_list)
    
    weighted_average = weighted_sum / total_weight
    return weighted_average, len(product_list)


def is_plan_anomaly(
    plan_error_rate: float | None,
    plus_threshold: float,
    minus_threshold: float
) -> Tuple[bool, str]:
    """
    計画異常値処理の判定
    
    Args:
        plan_error_rate: 計画誤差率（%）。Noneの場合は計算不可
        plus_threshold: プラス誤差の閾値（%）
        minus_threshold: マイナス誤差の閾値（%）。負の値で指定（例：-50.0）
    
    Returns:
        Tuple[bool, str]: (異常判定結果、判定理由)
           異常の場合True、正常の場合False
    """
    if plan_error_rate is None:
        return False, "計画誤差率計算不可"
    
    if plan_error_rate > plus_threshold:
        return True, f"計画誤差率が+{plan_error_rate:.1f}%で、閾値（+{plus_threshold:.1f}%）を超過"
    
    if plan_error_rate < minus_threshold:
        return True, f"計画誤差率が{plan_error_rate:.1f}%で、閾値（{minus_threshold:.1f}%）を下回る"
    
    return False, f"計画誤差率は{plan_error_rate:.1f}%で許容範囲内"


def calculate_abc_category_ratio_r(
    data_loader: DataLoader,
    lead_time: int,
    lead_time_type: str,
    stockout_tolerance_pct: float,
    sigma_k: float,
    top_limit_mode: str,
    top_limit_n: int,
    top_limit_p: float,
    category_cap_days: Dict[str, Optional[int]] = None
) -> Dict[str, float]:
    """
    ABC区分別の比率rを算出
    
    比率r = (ABC区分の安全在庫③合計) / (ABC区分の安全在庫②合計)
    
    Args:
        data_loader: DataLoaderインスタンス
        lead_time: リードタイム
        lead_time_type: 'calendar' or 'working_days'
        stockout_tolerance_pct: 欠品許容率（%）
        sigma_k: グローバル異常基準の係数
        top_limit_mode: 上位制限方式（'count' or 'percent'）
        top_limit_n: 上位カット件数
        top_limit_p: 上位カット割合（%）
        category_cap_days: 区分別日数上限の辞書
    
    Returns:
        Dict[str, float]: ABC区分をキー、比率rを値とする辞書
                         安全在庫②合計が0の区分は含まれない
    """
    from modules.safety_stock_models import SafetyStockCalculator
    from modules.outlier_handler import OutlierHandler
    
    # ABC分析結果を取得（同じファイル内の関数なので直接呼び出し）
    analysis_result, categories, _ = get_abc_analysis_with_fallback(data_loader)
    
    # 全商品の安全在庫②・③を計算
    product_list = data_loader.get_product_list()
    working_dates = data_loader.get_working_dates()
    
    # ABC区分別の安全在庫②・③合計を格納
    ss2_by_category = {}
    ss3_by_category = {}
    
    for product_code in product_list:
        try:
            # データ取得
            plan_data = data_loader.get_daily_plan(product_code)
            actual_data = data_loader.get_daily_actual(product_code)
            
            # ABC区分を取得
            product_row = analysis_result[analysis_result['product_code'] == product_code]
            if product_row.empty:
                abc_category = None
                abc_category_display = '未分類'
            else:
                abc_category = product_row.iloc[0]['abc_category']
                # NaNや空文字の場合はNoneに変換
                if pd.isna(abc_category) or str(abc_category).strip() == '':
                    abc_category = None
                    abc_category_display = '未分類'
                else:
                    abc_category_display = format_abc_category_for_display(abc_category)
            
            # 実績異常値処理を適用
            outlier_handler = OutlierHandler(
                actual_data=actual_data,
                working_dates=working_dates,
                sigma_k=sigma_k,
                top_limit_mode=top_limit_mode,
                top_limit_n=top_limit_n,
                top_limit_p=top_limit_p,
                abc_category=abc_category
            )
            
            processing_result = outlier_handler.detect_and_correct()
            corrected_data = processing_result['corrected_data']
            
            # 安全在庫を計算
            calculator = SafetyStockCalculator(
                plan_data=plan_data,
                actual_data=corrected_data,
                working_dates=working_dates,
                lead_time=lead_time,
                lead_time_type=lead_time_type,
                stockout_tolerance_pct=stockout_tolerance_pct,
                std_calculation_method='population',
                data_loader=data_loader,
                product_code=product_code,
                abc_category=abc_category,
                category_cap_days=category_cap_days or {},
                original_actual_data=actual_data
            )
            
            results = calculator.calculate_all_models()
            
            # 安全在庫②・③を取得
            ss2 = results['model2_empirical_actual']['safety_stock']
            ss3 = results['model3_empirical_plan']['safety_stock']
            
            # NoneやNaNの場合は0として扱う
            if ss2 is None or pd.isna(ss2):
                ss2 = 0.0
            if ss3 is None or pd.isna(ss3):
                ss3 = 0.0
            
            # ABC区分別に集計（表示用の区分名を使用）
            category_key = abc_category_display
            if category_key not in ss2_by_category:
                ss2_by_category[category_key] = 0.0
                ss3_by_category[category_key] = 0.0
            
            ss2_by_category[category_key] += ss2
            ss3_by_category[category_key] += ss3
            
        except Exception as e:
            # エラーが発生した商品はスキップ
            continue
    
    # 比率rを算出
    ratio_r_by_category = {}
    ss2_total_by_category = {}
    ss3_total_by_category = {}
    
    for category in ss2_by_category.keys():
        ss2_total = ss2_by_category[category]
        ss3_total = ss3_by_category[category]
        
        # ABC区分別の合計を保存
        ss2_total_by_category[category] = ss2_total
        ss3_total_by_category[category] = ss3_total
        
        # ゼロ割を回避
        if ss2_total > 0:
            ratio_r = ss3_total / ss2_total
            ratio_r_by_category[category] = ratio_r
    
    return {
        'ratio_r': ratio_r_by_category,
        'ss2_total': ss2_total_by_category,
        'ss3_total': ss3_total_by_category
    }
