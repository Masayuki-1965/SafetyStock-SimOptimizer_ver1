"""
安全在庫計算ロジック
既存のSafetyStockCalculatorをラップして提供
"""

from modules.safety_stock_models import SafetyStockCalculator
from typing import Dict, Optional
import pandas as pd


def calculate_safety_stock(
    plan_data: pd.Series,
    actual_data: pd.Series,
    working_dates: pd.DatetimeIndex,
    lead_time: int,
    lead_time_type: str,
    stockout_tolerance_pct: float = 1.0,
    std_calculation_method: str = 'population',
    data_loader=None,
    product_code: Optional[str] = None,
    abc_category: Optional[str] = None,
    category_cap_days: Optional[Dict[str, Optional[int]]] = None,
    original_actual_data: Optional[pd.Series] = None
) -> Dict:
    """
    安全在庫を計算
    
    Args:
        plan_data: 日次計画データ（インデックス=日付）
        actual_data: 日次実績データ（インデックス=日付）
        working_dates: 稼働日のインデックス
        lead_time: リードタイム
        lead_time_type: 'calendar' or 'working_days'
        stockout_tolerance_pct: 欠品許容率（%）
        std_calculation_method: 'population' or 'unbiased'
        data_loader: DataLoaderインスタンス（現行安全在庫計算用）
        product_code: 商品コード（現行安全在庫計算用）
        abc_category: ABC区分（'A', 'B', 'C'など）
        category_cap_days: 区分別日数上限の辞書（例: {'C': 40}）
        original_actual_data: 異常値処理前の実績データ（安全在庫②の平均計算用）
    
    Returns:
        Dict: 安全在庫計算結果
    """
    calculator = SafetyStockCalculator(
        plan_data=plan_data,
        actual_data=actual_data,
        working_dates=working_dates,
        lead_time=lead_time,
        lead_time_type=lead_time_type,
        stockout_tolerance_pct=stockout_tolerance_pct,
        std_calculation_method=std_calculation_method,
        data_loader=data_loader,
        product_code=product_code,
        abc_category=abc_category,
        category_cap_days=category_cap_days,
        original_actual_data=original_actual_data
    )
    
    # 安全在庫を計算
    results = calculator.calculate_all_models()
    
    return results


# 既存のクラスも直接エクスポート（後方互換性のため）
SafetyStockCalculator = SafetyStockCalculator

