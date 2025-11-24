"""
共通ユーティリティ関数
"""

import pandas as pd
import streamlit as st
from typing import Dict, List, Tuple
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

