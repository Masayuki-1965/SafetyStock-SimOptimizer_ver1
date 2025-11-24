"""
異常値処理ロジック
既存のOutlierHandlerをラップして提供
"""

from modules.outlier_handler import OutlierHandler
from typing import Dict, Optional
import pandas as pd


def detect_and_correct_outliers(
    actual_data: pd.Series,
    working_dates: pd.DatetimeIndex,
    sigma_k: float = 6.0,
    top_limit_mode: str = 'count',
    top_limit_n: int = 2,
    top_limit_p: float = 2.0,
    abc_category: Optional[str] = None
) -> Dict:
    """
    異常値を検出して補正
    
    Args:
        actual_data: 日次実績データ（インデックス=日付）
        working_dates: 稼働日のインデックス
        sigma_k: グローバル異常基準の係数（デフォルト6.0）
        top_limit_mode: 上位制限方式（'count'=件数N、'percent'=割合p%）
        top_limit_n: 上位カット件数（デフォルト2）
        top_limit_p: 上位カット割合（%）（デフォルト2.0）
        abc_category: ABC区分（'A', 'B', 'C'など）
    
    Returns:
        Dict: 処理結果（補正後データ、異常値インデックス、処理情報）
    """
    handler = OutlierHandler(
        actual_data=actual_data,
        working_dates=working_dates,
        sigma_k=sigma_k,
        top_limit_mode=top_limit_mode,
        top_limit_n=top_limit_n,
        top_limit_p=top_limit_p,
        abc_category=abc_category
    )
    
    return handler.detect_and_correct()


# 既存のクラスも直接エクスポート（後方互換性のため）
OutlierHandler = OutlierHandler

