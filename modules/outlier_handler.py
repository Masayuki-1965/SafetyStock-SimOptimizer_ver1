"""
異常値検出・補正モジュール

異常値検出方法：
1. グローバル異常基準（上振れのみ）: threshold_global = mean(all) + sigma_k * std(all)
   - 平均・標準偏差は全データ（ゼロ含む）で計算（UIに表示される統計情報と整合）
   - ゼロ出荷日は異常値検出対象から除外（検出時のみ除外）
   - 異常値は上側（上振れ）のみを検出対象
   - sigma_k（デフォルト6）: 6σを超えるような極端なスパイクだけを"異常値"として扱い、それ以外のばらつきはすべて実需として安全在庫に反映します。

2. 上位カット: 上位N件または上位p%に制限
   - デフォルト: 件数指定（N=2）

補正ロジック：
- 補正は削除ではなく上限クリップ（threshold_final = 上位N+1番目の値）で実施
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from scipy import stats


class OutlierHandler:
    """異常値検出・補正クラス"""
    
    def __init__(self,
                 actual_data: pd.Series,
                 working_dates: pd.DatetimeIndex,
                 sigma_k: float = 6.0,
                 top_limit_mode: str = 'count',  # 'count' or 'percent'
                 top_limit_n: int = 2,
                 top_limit_p: float = 2.0,
                 abc_category: Optional[str] = None):
        """
        初期化
        
        Args:
            actual_data: 日次実績データ（インデックス=日付）
            working_dates: 稼働日のインデックス
            sigma_k: グローバル異常基準の係数（デフォルト6.0）
                     6σを超えるような極端なスパイクだけを"異常値"として扱い、それ以外のばらつきはすべて実需として安全在庫に反映します。
            top_limit_mode: 上位制限方式（'count'=件数N、'percent'=割合p%）
            top_limit_n: 上位カット件数（デフォルト2）
            top_limit_p: 上位カット割合（%）（デフォルト2.0）
            abc_category: ABC区分（'A', 'B', 'C'など）
        """
        self.actual_data = actual_data.copy()
        self.working_dates = working_dates
        self.sigma_k = sigma_k
        self.top_limit_mode = top_limit_mode
        self.top_limit_n = top_limit_n
        self.top_limit_p = top_limit_p
        self.abc_category = abc_category
        
        # 処理結果を保存
        self.outlier_candidate_indices = []  # 候補（threshold_global超）
        self.outlier_final_indices = []  # 最終（上位カット後）
        self.corrected_data = None
        self.processing_info = {}
        self.threshold_global = None
        self.threshold_final = None
    
    def detect_and_correct(self) -> Dict:
        """
        異常値を検出して補正（上限クリップ）
        
        Returns:
            Dict: 処理結果（補正後データ、異常値インデックス、処理情報）
        """
        # [1] グローバル異常基準で候補を検出
        candidate_indices = self._detect_global_outliers()
        self.outlier_candidate_indices = candidate_indices
        
        # 候補が0件の場合は補正しない
        if len(candidate_indices) == 0:
            self.corrected_data = self.actual_data.copy()
            self.outlier_final_indices = []
            self.threshold_global = None
            self.threshold_final = None
            
            self.processing_info = {
                'candidate_count': 0,
                'final_count': 0,
                'threshold_global': None,
                'threshold_final': None,
                'correction_method': 'mean+sigma',
                'sigma_k': self.sigma_k,
                'top_limit_mode': self.top_limit_mode,
                'top_limit_value': self.top_limit_n if self.top_limit_mode == 'count' else self.top_limit_p,
                'skipped': True
            }
            
            return {
                'corrected_data': self.corrected_data,
                'imputed_data': self.corrected_data,  # 後方互換性のため
                'outlier_indices': [],
                'processing_info': self.processing_info
            }
        
        # [2] 上位カットを適用
        final_indices = self._apply_top_limit(candidate_indices)
        self.outlier_final_indices = final_indices
        
        # [3] 補正（上限クリップ）
        corrected_data = self._correct_outliers(final_indices)
        self.corrected_data = corrected_data
        
        # 処理情報をまとめる
        # 上位カット割合（％）の場合、分母情報と上限値を追加
        top_limit_denominator = None
        top_limit_calculated_count = None
        if self.top_limit_mode == 'percent':
            top_limit_denominator = len(self.actual_data)  # 全観測日数（ゼロを含む）
            top_limit_calculated_count = max(1, int(np.ceil(top_limit_denominator * self.top_limit_p / 100.0)))  # カット対象件数の上限値
        
        self.processing_info = {
            'candidate_count': len(candidate_indices),
            'final_count': len(final_indices),
            'threshold_global': self.threshold_global,
            'threshold_final': self.threshold_final,
            'correction_method': 'mean+sigma',
            'sigma_k': self.sigma_k,
            'top_limit_mode': self.top_limit_mode,
            'top_limit_value': self.top_limit_n if self.top_limit_mode == 'count' else self.top_limit_p,
            'top_limit_denominator': top_limit_denominator,  # 上位カット割合の分母（全観測日数）
            'top_limit_calculated_count': top_limit_calculated_count,  # カット対象件数の上限値（全観測日数×上位カット割合）
            'outlier_dates': [self.actual_data.index[i] for i in final_indices] if final_indices else [],
            'skipped': False
        }
        
        return {
            'corrected_data': corrected_data,
            'imputed_data': corrected_data,  # 後方互換性のため
            'outlier_indices': final_indices,
            'processing_info': self.processing_info
        }
    
    def detect_and_impute(self) -> Dict:
        """
        後方互換性のためのエイリアス
        """
        return self.detect_and_correct()
    
    def _detect_global_outliers(self) -> List[int]:
        """
        グローバル異常基準で異常値を検出（上側のみ、ゼロ出荷日は除外）
        
        平均・標準偏差は全データ（ゼロ含む）で計算し、UIに表示される統計情報と整合させる。
        異常値検出時はゼロ出荷日を除外する。
        
        Returns:
            List[int]: 異常値候補のインデックスリスト
        """
        # 全データ（ゼロ含む）で平均と標準偏差を計算（UIに表示される統計情報と整合）
        if len(self.actual_data) == 0:
            self.threshold_global = None
            return []
        
        mean = self.actual_data.mean()
        std = self.actual_data.std()
        
        if std == 0:
            self.threshold_global = None
            return []
        
        # グローバル異常基準: threshold_global = mean + sigma_k * std
        self.threshold_global = mean + self.sigma_k * std
        
        # 異常値検出（上側のみ）
        candidate_indices = []
        for i, value in enumerate(self.actual_data.values):
            # ゼロ出荷日は異常値検出対象から除外
            if value == 0:
                continue
            
            # 上側（上振れ）のみを検出
            if value > self.threshold_global:
                candidate_indices.append(i)
        
        return sorted(candidate_indices)
    
    def _apply_top_limit(self, candidate_indices: List[int]) -> List[int]:
        """
        上位カットを適用（上位N件または上位p%）
        
        上位カット割合（％）の分母は全観測日数（ゼロを含む）を使用する。
        ゼロ値そのものはカット対象にはしない（上位カットなので、上位側のみ対象）。
        
        Args:
            candidate_indices: 異常値候補のインデックスリスト
        
        Returns:
            List[int]: 最終的な異常値のインデックスリスト
        """
        if len(candidate_indices) == 0:
            return []
        
        # 候補の値を取得してソート（降順）
        candidate_values = [(i, self.actual_data.iloc[i]) for i in candidate_indices]
        candidate_values.sort(key=lambda x: x[1], reverse=True)
        
        if self.top_limit_mode == 'count':
            # 上位N件
            limit_count = min(self.top_limit_n, len(candidate_values))
            final_values = candidate_values[:limit_count]
        else:
            # 上位p%: 分母は全観測日数（ゼロを含む全データ件数）
            # 例：240日×2% = 4.8 → 5件（切り上げ）
            N_all = len(self.actual_data)  # 全観測日数（ゼロを含む）
            max_outliers = max(1, int(np.ceil(N_all * self.top_limit_p / 100.0)))  # カット対象件数の上限値
            # 候補の中から大きい順にmax_outliers件を選ぶ（上限値と候補数の小さい方）
            # ゼロ値は候補に含まれないため、自動的にカット対象外となる
            limit_count = min(max_outliers, len(candidate_values))  # 実際のカット対象件数
            final_values = candidate_values[:limit_count]
        
        # 最終的な異常値インデックスを取得
        final_indices = [idx for idx, _ in final_values]
        
        # threshold_final: 上位N+1番目の値（正常データの最大値）
        if len(candidate_values) > len(final_values):
            # 上位N+1番目の値が存在する場合
            self.threshold_final = candidate_values[len(final_values)][1]
        else:
            # すべてが対象の場合、threshold_globalを使用
            self.threshold_final = self.threshold_global
        
        return sorted(final_indices)
    
    def _is_spike_outlier(self, idx: int, value: float) -> bool:
        """
        スパイク検出（前日比or同曜日比5倍以上）
        A区分のみで使用
        
        Args:
            idx: データのインデックス
            value: 現在の値
        
        Returns:
            bool: スパイク異常値かどうか
        """
        values = self.actual_data.values
        spike_threshold = 5.0
        
        # 前日比チェック
        if idx > 0:
            prev_value = values[idx - 1]
            if prev_value > 0:
                ratio_prev = value / prev_value
                if ratio_prev >= spike_threshold:
                    return True
        
        # 同曜日比チェック（7日前、14日前、21日前、28日前の平均と比較）
        weekday_values = []
        for days_back in [7, 14, 21, 28]:
            if idx >= days_back:
                weekday_value = values[idx - days_back]
                if weekday_value > 0:
                    weekday_values.append(weekday_value)
        
        if weekday_values:
            avg_weekday = np.mean(weekday_values)
            if avg_weekday > 0:
                ratio_weekday = value / avg_weekday
                if ratio_weekday >= spike_threshold:
                    return True
        
        return False
    
    def _correct_outliers(self, outlier_indices: List[int]) -> pd.Series:
        """
        異常値を補正（上限クリップ方式）
        threshold_global（平均 + σ係数 × 標準偏差）でクリップ
        
        Args:
            outlier_indices: 異常値のインデックスリスト
        
        Returns:
            pd.Series: 補正後のデータ
        """
        corrected_data = self.actual_data.copy()
        
        if self.threshold_global is None:
            return corrected_data
        
        # すべての異常値を上限クリップで補正
        for idx in outlier_indices:
            # 上限クリップ: threshold_global を超える値は threshold_global にクリップ
            if corrected_data.iloc[idx] > self.threshold_global:
                corrected_data.iloc[idx] = self.threshold_global
        
        return corrected_data
    
    def get_comparison_stats(self) -> Dict:
        """
        Before/Afterの統計情報を取得
        
        Returns:
            Dict: 統計情報
        """
        corrected_data = self.corrected_data if self.corrected_data is not None else self.imputed_data
        if corrected_data is None:
            return {}
        
        before_mean = np.mean(self.actual_data.values)
        after_mean = np.mean(corrected_data.values)
        
        before_std = np.std(self.actual_data.values)
        after_std = np.std(corrected_data.values)
        
        return {
            'before_mean': before_mean,
            'after_mean': after_mean,
            'before_std': before_std,
            'after_std': after_std,
            'mean_change': after_mean - before_mean,
            'std_change': after_std - before_std,
            'candidate_count': len(self.outlier_candidate_indices),
            'final_count': len(self.outlier_final_indices),
            'outlier_count': len(self.outlier_final_indices),  # 後方互換性のため
            'corrected_days': len(self.outlier_final_indices),
            'imputed_days': len(self.outlier_final_indices)  # 後方互換性のため
        }

