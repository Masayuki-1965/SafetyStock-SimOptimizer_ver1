"""
ユーティリティ関数モジュール
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
from typing import Tuple, List
import json
import os


def get_base_path():
    """アプリケーションのベースパスを取得（EXE対応）"""
    if getattr(sys, 'frozen', False):
        # PyInstallerでビルドされた場合
        return sys._MEIPASS
    else:
        # 通常のPython実行
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(config_path: str = "config/settings.json") -> dict:
    """設定ファイルを読み込む"""
    base_path = get_base_path()
    full_path = os.path.join(base_path, config_path)
    
    with open(full_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return config


def calculate_safety_factor(stockout_tolerance_pct: float) -> float:
    """
    欠品許容率から安全係数を計算
    
    Args:
        stockout_tolerance_pct: 欠品許容率（%）
    
    Returns:
        float: 安全係数（Z値）
    """
    # 欠品許容率をサービスレベルに変換
    service_level = 1.0 - (stockout_tolerance_pct / 100.0)
    
    # 正規分布の分位点（片側）
    safety_factor = stats.norm.ppf(service_level)
    
    return safety_factor


def is_working_day(date: pd.Timestamp, working_dates: pd.DatetimeIndex) -> bool:
    """
    指定された日付が稼働日かどうかを判定
    
    Args:
        date: 判定対象の日付
        working_dates: 稼働日のインデックス
    
    Returns:
        bool: 稼働日ならTrue
    """
    return date in working_dates


def count_working_days(start_date: pd.Timestamp, end_date: pd.Timestamp, 
                       working_dates: pd.DatetimeIndex) -> int:
    """
    期間内の稼働日数をカウント
    
    Args:
        start_date: 開始日
        end_date: 終了日
        working_dates: 稼働日のインデックス
    
    Returns:
        int: 稼働日数
    """
    period_dates = pd.date_range(start=start_date, end=end_date, freq='D')
    count = sum(1 for date in period_dates if date in working_dates)
    return count


def get_lead_time_in_working_days(lead_time: int, lead_time_type: str,
                                   working_dates: pd.DatetimeIndex) -> float:
    """
    リードタイムを稼働日数に変換
    
    Args:
        lead_time: リードタイム
        lead_time_type: 'calendar' or 'working_days'
        working_dates: 稼働日のインデックス
    
    Returns:
        float: 稼働日数でのリードタイム
    """
    if lead_time_type == 'working_days':
        return float(lead_time)
    else:  # calendar
        # カレンダー期間をスライドして平均稼働日数を算出
        working_days_counts = []
        
        for i in range(len(working_dates) - lead_time + 1):
            start_date = working_dates[i]
            end_date = start_date + timedelta(days=lead_time - 1)
            working_day_count = count_working_days(start_date, end_date, working_dates)
            working_days_counts.append(working_day_count)
        
        return np.mean(working_days_counts) if working_days_counts else lead_time


def format_number(value: float, decimals: int = 2) -> str:
    """
    数値をフォーマットして文字列に変換
    
    Args:
        value: 数値
        decimals: 小数点以下の桁数
    
    Returns:
        str: フォーマットされた文字列
    """
    return f"{value:.{decimals}f}"


def create_export_filename(product_code: str, analysis_type: str, 
                           extension: str, timestamp: bool = True) -> str:
    """
    エクスポート用のファイル名を生成
    
    Args:
        product_code: 商品コード
        analysis_type: 分析種別（'theoretical', 'empirical', 'comparison'）
        extension: 拡張子（'png', 'csv'）
        timestamp: タイムスタンプを含めるか
    
    Returns:
        str: ファイル名
    """
    timestamp_str = ""
    if timestamp:
        timestamp_str = f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return f"{product_code}_{analysis_type}{timestamp_str}.{extension}"


import sys  # sysのインポートを追加


