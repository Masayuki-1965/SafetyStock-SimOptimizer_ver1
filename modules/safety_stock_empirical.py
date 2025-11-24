"""
安全在庫②（実測値）計算モジュール

計画値と実績値の差分分布から、欠品許容率を加味して安全在庫を算出
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
from modules.utils import get_lead_time_in_working_days


class EmpiricalSafetyStock:
    """実測値による安全在庫計算クラス"""
    
    def __init__(self,
                 plan_data: pd.Series,
                 actual_data: pd.Series,
                 working_dates: pd.DatetimeIndex,
                 lead_time: int,
                 lead_time_type: str,
                 stockout_tolerance_pct: float):
        """
        初期化
        
        Args:
            plan_data: 日次計画データ（インデックス=日付）
            actual_data: 日次実績データ（インデックス=日付）
            working_dates: 稼働日のインデックス
            lead_time: リードタイム
            lead_time_type: 'calendar' or 'working_days'
            stockout_tolerance_pct: 欠品許容率（%）
        """
        self.plan_data = plan_data
        self.actual_data = actual_data
        self.working_dates = working_dates
        self.lead_time = lead_time
        self.lead_time_type = lead_time_type
        self.stockout_tolerance_pct = stockout_tolerance_pct
        
        # 計算結果を保存
        self.results = {}
        self.differences = []
        
    def calculate(self) -> Dict:
        """
        安全在庫を計算
        
        Returns:
            Dict: 計算結果
        """
        # リードタイムを稼働日数に変換
        lead_time_working_days = get_lead_time_in_working_days(
            self.lead_time, 
            self.lead_time_type, 
            self.working_dates
        )
        
        lead_time_days = int(np.ceil(lead_time_working_days))
        
        # 差分分布を計算
        self.differences = self._calculate_difference_distribution(lead_time_days)
        
        # 欠品許容率に基づく閾値を計算
        # 左側（1 - 欠品許容率）の分位点
        percentile = 100 - self.stockout_tolerance_pct
        safety_stock = np.percentile(self.differences, percentile)
        
        # 統計量を計算
        mean_diff = np.mean(self.differences)
        std_diff = np.std(self.differences)
        median_diff = np.median(self.differences)
        min_diff = np.min(self.differences)
        max_diff = np.max(self.differences)
        
        # 結果を保存
        self.results = {
            'safety_stock': safety_stock,
            'lead_time_working_days': lead_time_working_days,
            'stockout_tolerance_pct': self.stockout_tolerance_pct,
            'service_level_pct': 100 - self.stockout_tolerance_pct,
            'mean_difference': mean_diff,
            'std_difference': std_diff,
            'median_difference': median_diff,
            'min_difference': min_diff,
            'max_difference': max_diff,
            'sample_size': len(self.differences),
            'percentile': percentile
        }
        
        return self.results
    
    def _calculate_difference_distribution(self, lead_time_days: int) -> List[float]:
        """
        リードタイム期間の計画値と実績値の差分分布を計算
        
        差分 = 計画値合計 - 実績値合計
        
        Args:
            lead_time_days: リードタイム（稼働日数）
        
        Returns:
            List[float]: 差分のリスト
        """
        differences = []
        
        # スライディングウィンドウで各区間の差分を計算
        for i in range(len(self.plan_data) - lead_time_days + 1):
            plan_sum = self.plan_data.iloc[i:i+lead_time_days].sum()
            actual_sum = self.actual_data.iloc[i:i+lead_time_days].sum()
            diff = plan_sum - actual_sum
            differences.append(diff)
        
        return differences
    
    def get_summary_stats(self) -> Dict:
        """
        要約統計量を取得
        
        Returns:
            Dict: 要約統計量
        """
        if not self.results:
            self.calculate()
        
        return {
            '安全在庫（実測値）': self.results['safety_stock'],
            'リードタイム（稼働日）': self.results['lead_time_working_days'],
            'サービスレベル（%）': self.results['service_level_pct'],
            '欠品許容率（%）': self.results['stockout_tolerance_pct'],
            '差分平均': self.results['mean_difference'],
            '差分標準偏差': self.results['std_difference'],
            '差分中央値': self.results['median_difference'],
            '差分最小値': self.results['min_difference'],
            '差分最大値': self.results['max_difference'],
            'サンプル数': self.results['sample_size'],
            '分位点（%）': self.results['percentile']
        }
    
    def get_distribution_data(self) -> pd.DataFrame:
        """
        差分分布データをDataFrameで取得
        
        Returns:
            pd.DataFrame: 差分分布データ
        """
        if not self.differences:
            self.calculate()
        
        df = pd.DataFrame({
            'difference': self.differences
        })
        
        return df
    
    def get_stockout_risk_stats(self) -> Dict:
        """
        欠品リスクに関する統計を取得
        
        Returns:
            Dict: 欠品リスク統計
        """
        if not self.results:
            self.calculate()
        
        # 安全在庫を超える差分の割合
        exceeding_count = sum(1 for d in self.differences if d > self.results['safety_stock'])
        exceeding_rate = (exceeding_count / len(self.differences)) * 100
        
        # 差分がマイナス（実績が計画を下回る）の割合
        negative_count = sum(1 for d in self.differences if d < 0)
        negative_rate = (negative_count / len(self.differences)) * 100
        
        return {
            '安全在庫超過回数': exceeding_count,
            '安全在庫超過率（%）': exceeding_rate,
            '計画未達回数': negative_count,
            '計画未達率（%）': negative_rate
        }


