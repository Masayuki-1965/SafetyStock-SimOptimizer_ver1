"""
安全在庫①（理論値）計算モジュール

理論式: 安全在庫 = 安全係数 × 受注数の標準偏差 × √（リードタイム + 間隔）
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
from modules.utils import calculate_safety_factor, get_lead_time_in_working_days


class TheoreticalSafetyStock:
    """理論値による安全在庫計算クラス"""
    
    def __init__(self, 
                 actual_data: pd.Series,
                 working_dates: pd.DatetimeIndex,
                 lead_time: int,
                 lead_time_type: str,
                 stockout_tolerance_pct: float,
                 std_calculation_method: str = 'interval_average'):
        """
        初期化
        
        Args:
            actual_data: 日次実績データ（インデックス=日付）
            working_dates: 稼働日のインデックス
            lead_time: リードタイム
            lead_time_type: 'calendar' or 'working_days'
            stockout_tolerance_pct: 欠品許容率（%）
            std_calculation_method: 'overall' or 'interval_average'
        """
        self.actual_data = actual_data
        self.working_dates = working_dates
        self.lead_time = lead_time
        self.lead_time_type = lead_time_type
        self.stockout_tolerance_pct = stockout_tolerance_pct
        self.std_calculation_method = std_calculation_method
        
        # 計算結果を保存
        self.results = {}
        
    def calculate(self) -> Dict:
        """
        安全在庫を計算
        
        Returns:
            Dict: 計算結果
        """
        # 安全係数を計算
        safety_factor = calculate_safety_factor(self.stockout_tolerance_pct)
        
        # リードタイムを稼働日数に変換
        lead_time_working_days = get_lead_time_in_working_days(
            self.lead_time, 
            self.lead_time_type, 
            self.working_dates
        )
        
        # 間隔は0（都度生産）
        interval = 0
        
        # 標準偏差を計算
        if self.std_calculation_method == 'overall':
            std_dev = self._calculate_overall_std()
        else:  # interval_average
            std_dev = self._calculate_interval_average_std(int(np.ceil(lead_time_working_days)))
        
        # 安全在庫を計算
        safety_stock = safety_factor * std_dev * np.sqrt(lead_time_working_days + interval)
        
        # 理論分布のパラメータ
        mean_demand = self.actual_data.mean()
        
        # 結果を保存
        self.results = {
            'safety_stock': safety_stock,
            'safety_factor': safety_factor,
            'std_dev': std_dev,
            'lead_time_working_days': lead_time_working_days,
            'interval': interval,
            'mean_demand': mean_demand,
            'stockout_tolerance_pct': self.stockout_tolerance_pct,
            'service_level_pct': 100 - self.stockout_tolerance_pct,
            'std_calculation_method': self.std_calculation_method,
            'sample_size': len(self.actual_data)
        }
        
        return self.results
    
    def _calculate_overall_std(self) -> float:
        """
        全期間の標準偏差を計算
        
        Returns:
            float: 標準偏差
        """
        return self.actual_data.std()
    
    def _calculate_interval_average_std(self, lead_time_days: int) -> float:
        """
        各リードタイム区間ごとの標準偏差の平均を計算
        
        Args:
            lead_time_days: リードタイム（稼働日数）
        
        Returns:
            float: 区間標準偏差の平均
        """
        interval_stds = []
        
        # スライディングウィンドウで各区間の合計を計算
        for i in range(len(self.actual_data) - lead_time_days + 1):
            interval_sum = self.actual_data.iloc[i:i+lead_time_days].sum()
            interval_stds.append(interval_sum)
        
        # 各区間合計の標準偏差
        if len(interval_stds) > 0:
            return np.std(interval_stds)
        else:
            return 0.0
    
    def generate_theoretical_distribution(self, num_samples: int = 10000) -> np.ndarray:
        """
        理論的な正規分布を生成
        
        Args:
            num_samples: サンプル数
        
        Returns:
            np.ndarray: 正規分布のサンプル
        """
        if not self.results:
            self.calculate()
        
        # リードタイム期間の需要の平均
        mean = self.results['mean_demand'] * self.results['lead_time_working_days']
        
        # リードタイム期間の需要の標準偏差
        std = self.results['std_dev'] * np.sqrt(
            self.results['lead_time_working_days'] + self.results['interval']
        )
        
        # 正規分布からサンプリング
        samples = np.random.normal(mean, std, num_samples)
        
        return samples
    
    def get_summary_stats(self) -> Dict:
        """
        要約統計量を取得
        
        Returns:
            Dict: 要約統計量
        """
        if not self.results:
            self.calculate()
        
        return {
            '安全在庫（理論値）': self.results['safety_stock'],
            '安全係数': self.results['safety_factor'],
            '標準偏差': self.results['std_dev'],
            'リードタイム（稼働日）': self.results['lead_time_working_days'],
            '平均需要（日次）': self.results['mean_demand'],
            'サービスレベル（%）': self.results['service_level_pct'],
            '欠品許容率（%）': self.results['stockout_tolerance_pct'],
            'サンプル数': self.results['sample_size'],
            '標準偏差計算方法': self.results['std_calculation_method']
        }
    
    def get_distribution_data(self) -> pd.DataFrame:
        """
        分布データをDataFrameで取得
        
        Returns:
            pd.DataFrame: 分布データ
        """
        samples = self.generate_theoretical_distribution()
        
        df = pd.DataFrame({
            'demand': samples
        })
        
        return df


