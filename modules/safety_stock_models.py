"""
安全在庫計算モジュール（3モデル対応）

安全在庫①：理論値（教科書基準）
安全在庫②：実測値（実績−平均）
安全在庫③：実測値（実績−計画）【推奨モデル】

更新: C区分の安全在庫上限処理を追加
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional
from scipy.stats import norm
import warnings
warnings.filterwarnings('ignore')


class SafetyStockCalculator:
    """安全在庫計算クラス（3モデル対応）"""
    
    def __init__(self,
                 plan_data: pd.Series,
                 actual_data: pd.Series,
                 working_dates: pd.DatetimeIndex,
                 lead_time: int,
                 lead_time_type: str,
                 stockout_tolerance_pct: float = 5.0,
                 std_calculation_method: str = 'population',
                 data_loader=None,
                 product_code=None,
                 abc_category: Optional[str] = None,
                 category_cap_days: Optional[Dict[str, Optional[int]]] = None,
                 original_actual_data: Optional[pd.Series] = None):
        """
        初期化
        
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
            category_cap_days: 区分別日数上限の辞書（例: {'C': 40}）。Noneの場合はデフォルト（C区分=40日）
            original_actual_data: 異常値処理前の実績データ（安全在庫②の平均計算用）。Noneの場合はactual_dataを使用
        """
        self.plan_data = plan_data
        self.actual_data = actual_data
        self.working_dates = working_dates
        self.lead_time = lead_time
        self.lead_time_type = lead_time_type
        self.stockout_tolerance_pct = stockout_tolerance_pct
        self.std_calculation_method = std_calculation_method
        self.data_loader = data_loader
        self.product_code = product_code
        self.abc_category = abc_category
        
        # 区分別日数上限の設定
        # Noneの場合は空の辞書（上限カットなし）、空の辞書の場合はそのまま、それ以外は指定された値を使用
        if category_cap_days is None:
            self.category_cap_days = {}  # 上限カットなし
        else:
            self.category_cap_days = category_cap_days
        
        # 異常値処理前の実績データ（安全在庫②の平均計算用）
        # original_actual_dataが指定されている場合はそれを使用、そうでない場合はactual_dataを使用
        self.original_actual_data = original_actual_data if original_actual_data is not None else actual_data
        
        # 計算結果を保存
        self.results = {}
        
    def calculate_all_models(self) -> Dict:
        """
        全3モデルの安全在庫を計算
        
        Returns:
            Dict: 全モデルの計算結果
        """
        # リードタイムを稼働日数に変換
        lead_time_working_days = self._get_lead_time_in_working_days()
        lead_time_days = int(np.ceil(lead_time_working_days))
        
        # 安全係数を計算（p=0%の場合はNone）
        safety_factor = self._calculate_safety_factor()
        
        # モデル①：理論値（教科書基準）
        model1_results = self._calculate_theoretical_model(safety_factor, lead_time_working_days)
        
        # モデル②：実測値（実績−平均）
        model2_results = self._calculate_empirical_actual_model(lead_time_days)
        
        # モデル③：実測値（実績−計画）【推奨】
        model3_results = self._calculate_empirical_plan_model(lead_time_days)
        
        # 現行安全在庫：月数ベースから稼働日ベースに換算
        current_safety_stock_results = self._calculate_current_safety_stock()
        
        # 区分別安全在庫上限を適用
        if self.abc_category:
            cap_days = self.category_cap_days.get(self.abc_category.upper())
            if cap_days is not None:
                model1_results = self._apply_category_limit(model1_results, cap_days)
                model2_results = self._apply_category_limit(model2_results, cap_days)
                model3_results = self._apply_category_limit(model3_results, cap_days)
        
        # 結果を統合
        self.results = {
            'model1_theoretical': model1_results,
            'model2_empirical_actual': model2_results,
            'model3_empirical_plan': model3_results,
            'current_safety_stock': current_safety_stock_results,
            'common_params': {
                'lead_time_working_days': lead_time_working_days,
                'lead_time_days': lead_time_days,
                'stockout_tolerance_pct': self.stockout_tolerance_pct,
                'service_level_pct': 100 - self.stockout_tolerance_pct,
                'safety_factor': safety_factor
            }
        }
        
        return self.results
    
    def _get_lead_time_in_working_days(self) -> float:
        """
        リードタイムを稼働日数に変換
        
        Returns:
            float: 稼働日数
        """
        if self.lead_time_type == 'working_days':
            return float(self.lead_time)
        else:  # calendar
            # カレンダー日数を稼働日数に変換（概算）
            # 土日祝を除く稼働日は約70%と仮定
            return float(self.lead_time) * 0.7
    
    def _calculate_safety_factor(self) -> Optional[float]:
        """
        安全係数を計算
        
        Returns:
            float or None: 安全係数（Z値）、p=0%の場合はNone
        """
        if self.stockout_tolerance_pct <= 0:
            return None  # p=0%の時はZ=∞で定義不可
        p = self.stockout_tolerance_pct / 100.0
        return norm.ppf(1 - p)
    
    def _calculate_theoretical_model(self, safety_factor: Optional[float], lead_time_working_days: float) -> Dict:
        """
        モデル①：理論値（教科書基準）を計算
        
        Args:
            safety_factor: 安全係数（p=0%の場合はNone）
            lead_time_working_days: リードタイム（稼働日数）
        
        Returns:
            Dict: 計算結果（p=0%の場合は計算不可）
        """
        # p=0%の時は計算不可
        if safety_factor is None:
            return {
                'safety_stock': None,
                'sigma_daily': self.actual_data.std(ddof=0) if self.std_calculation_method == 'population' else self.actual_data.std(ddof=1),
                'mean_demand': self.actual_data.mean(),
                'method': 'theoretical',
                'formula': '計算不可（p=0→Z=∞）',
                'is_undefined': True
            }
        
        # 日次実績の標準偏差
        if self.std_calculation_method == 'population':
            sigma_daily = self.actual_data.std(ddof=0)
        else:  # unbiased
            sigma_daily = self.actual_data.std(ddof=1)
        
        # 安全在庫① = Z × σ × √L
        safety_stock = safety_factor * sigma_daily * np.sqrt(lead_time_working_days)
        
        # 統計量
        mean_demand = self.actual_data.mean()
        
        return {
            'safety_stock': safety_stock,
            'sigma_daily': sigma_daily,
            'mean_demand': mean_demand,
            'method': 'theoretical',
            'formula': f'Z × σ × √L = {safety_factor:.3f} × {sigma_daily:.3f} × √{lead_time_working_days:.1f}',
            'is_undefined': False
        }
    
    def _calculate_empirical_actual_model(self, lead_time_days: int) -> Dict:
        """
        モデル②：実測値（実績−平均）を計算
        
        Args:
            lead_time_days: リードタイム（日数）
        
        Returns:
            Dict: 計算結果
        """
        # リードタイム期間の実績合計を計算（異常値処理後のデータを使用）
        actual_sums = self.actual_data.rolling(window=lead_time_days).sum().dropna()
        
        # 平均は異常値処理前のデータから計算（異常値補正の影響を適切に反映するため）
        # インデックスを一致させるため、同じデータ長で計算
        original_actual_sums = self.original_actual_data.rolling(window=lead_time_days).sum().dropna()
        mean_actual_sums = original_actual_sums.mean()
        
        # 差分 = 実績合計（異常値処理後） - 平均（異常値処理前）
        # actual_sumsとoriginal_actual_sumsのインデックスが一致していることを確認
        delta2 = actual_sums - mean_actual_sums
        
        # 右側（正の差分、欠品リスク側）のみを抽出
        delta2_positive = delta2[delta2 > 0]
        N_pos = len(delta2_positive)
        
        # 右側が空の場合は0を返す
        if N_pos == 0:
            safety_stock = 0.0
            percentile = None
        # p=0%の時は右側（欠品側）分布の最大差分
        elif self.stockout_tolerance_pct <= 0:
            # 右側サンプルが存在することを確認してからmax()を実行
            if len(delta2_positive) > 0:
                safety_stock = delta2_positive.max()
            else:
                safety_stock = 0.0
            percentile = None
        else:
            # 分位点 q = 1 - p/100（片側）で設定
            q = 1 - self.stockout_tolerance_pct / 100.0
            # 離散データは k = max(1, ceil(q * N_pos)) を用い、右側（正の差分）の昇順 k 番目を採用
            k = max(1, int(np.ceil(q * N_pos)))
            # 右側（正の差分）を昇順にソート
            delta2_positive_sorted = np.sort(delta2_positive.values)
            # k番目（0-indexedなので k-1）を採用
            safety_stock = delta2_positive_sorted[k - 1]
            percentile = 100 - self.stockout_tolerance_pct
        
        # 統計量
        mean_delta = delta2.mean()
        std_delta = delta2.std()
        
        return {
            'safety_stock': safety_stock,
            'delta_data': delta2.tolist(),
            'mean_delta': mean_delta,
            'std_delta': std_delta,
            'percentile': percentile,
            'method': 'empirical_actual',
            'formula': f'P{percentile}(実績合計 - 平均)' if percentile is not None else 'max(実績合計 - 平均, 0)'
        }
    
    def _calculate_empirical_plan_model(self, lead_time_days: int) -> Dict:
        """
        モデル③：実測値（実績−計画）を計算【推奨モデル】
        
        Args:
            lead_time_days: リードタイム（日数）
        
        Returns:
            Dict: 計算結果
        """
        # リードタイム期間の実績合計と計画合計を計算
        actual_sums = self.actual_data.rolling(window=lead_time_days).sum().dropna()
        plan_sums = self.plan_data.rolling(window=lead_time_days).sum().dropna()
        
        # 共通のインデックスを取得
        common_idx = actual_sums.index.intersection(plan_sums.index)
        actual_sums_common = actual_sums.loc[common_idx]
        plan_sums_common = plan_sums.loc[common_idx]
        
        # 差分 = 実績合計 - 計画合計
        delta3 = actual_sums_common - plan_sums_common
        
        # 右側（正の差分、欠品リスク側）のみを抽出
        delta3_positive = delta3[delta3 > 0]
        N_pos = len(delta3_positive)
        
        # 右側が空の場合は0を返す
        if N_pos == 0:
            safety_stock = 0.0
            percentile = None
        # p=0%の時は右側（欠品側）分布の最大差分
        elif self.stockout_tolerance_pct <= 0:
            # 右側サンプルが存在することを確認してからmax()を実行
            if len(delta3_positive) > 0:
                safety_stock = delta3_positive.max()
            else:
                safety_stock = 0.0
            percentile = None
        else:
            # 分位点 q = 1 - p/100（片側）で設定
            q = 1 - self.stockout_tolerance_pct / 100.0
            # 離散データは k = max(1, ceil(q * N_pos)) を用い、右側（正の差分）の昇順 k 番目を採用
            k = max(1, int(np.ceil(q * N_pos)))
            # 右側（正の差分）を昇順にソート
            delta3_positive_sorted = np.sort(delta3_positive.values)
            # k番目（0-indexedなので k-1）を採用
            safety_stock = delta3_positive_sorted[k - 1]
            percentile = 100 - self.stockout_tolerance_pct
        
        # 統計量
        mean_delta = delta3.mean()
        std_delta = delta3.std()
        
        return {
            'safety_stock': safety_stock,
            'delta_data': delta3.tolist(),
            'mean_delta': mean_delta,
            'std_delta': std_delta,
            'percentile': percentile,
            'method': 'empirical_plan',
            'formula': f'P{percentile}(実績合計 - 計画合計)' if percentile is not None else 'max(実績合計 - 計画合計, 0)'
        }
    
    def _calculate_current_safety_stock(self) -> Dict:
        """
        現行安全在庫（月数ベース）を稼働日ベースに換算
        
        Returns:
            Dict: 現行安全在庫の計算結果
        """
        if self.data_loader is None:
            return {
                'safety_stock': 0.0,
                'safety_stock_days': 0.0,
                'monthly_stock': 0.0,
                'avg_working_days_per_month': 0.0,
                'daily_actual_mean': 0.0,
                'method': 'current_monthly',
                'formula': '月数ベース → 稼働日ベース換算'
            }
        
        # 商品コードを取得
        product_code = self.product_code
        
        if product_code is None:
            return {
                'safety_stock': 0.0,
                'safety_stock_days': 0.0,
                'monthly_stock': 0.0,
                'avg_working_days_per_month': 0.0,
                'daily_actual_mean': 0.0,
                'method': 'current_monthly',
                'formula': '月数ベース → 稼働日ベース換算'
            }
        
        # 現行安全在庫月数を取得
        monthly_stock = self.data_loader.get_safety_stock_monthly(product_code)
        
        # 月平均稼働日数を取得
        avg_working_days_per_month = self.data_loader.calculate_monthly_working_days()
        
        # 日当たり実績平均を計算
        daily_actual_mean = self.actual_data.mean()
        
        # 在庫日数に換算
        safety_stock_days = monthly_stock * avg_working_days_per_month
        
        # 在庫数量に換算
        safety_stock = safety_stock_days * daily_actual_mean
        
        return {
            'safety_stock': safety_stock,
            'safety_stock_days': safety_stock_days,
            'monthly_stock': monthly_stock,
            'avg_working_days_per_month': avg_working_days_per_month,
            'daily_actual_mean': daily_actual_mean,
            'method': 'current_monthly',
            'formula': f'{monthly_stock:.1f}月 × {avg_working_days_per_month:.1f}日/月 × {daily_actual_mean:.2f}個/日'
        }
    
    def get_comparison_table(self) -> pd.DataFrame:
        """
        3モデルの比較テーブルを取得
        
        Returns:
            pd.DataFrame: 比較テーブル
        """
        if not self.results:
            self.calculate_all_models()
        
        data = []
        for model_name, model_key in [
            ('理論値（教科書基準）', 'model1_theoretical'),
            ('実測値（実績−平均）', 'model2_empirical_actual'),
            ('実測値（実績−計画）', 'model3_empirical_plan')
        ]:
            model_result = self.results[model_key]
            data.append({
                'モデル': model_name,
                '安全在庫': f"{model_result['safety_stock']:.2f}",
                '計算方法': model_result['method'],
                '式': model_result['formula']
            })
        
        return pd.DataFrame(data)
    
    def get_histogram_data(self) -> Dict:
        """
        ヒストグラム用データを取得
        
        Returns:
            Dict: ヒストグラム用データ
        """
        if not self.results:
            self.calculate_all_models()
        
        # ①が定義不可の場合はNoneを返す
        model1_line = self.results['model1_theoretical']['safety_stock'] if not self.results['model1_theoretical'].get('is_undefined', False) else None
        
        return {
            'model2_delta': self.results['model2_empirical_actual']['delta_data'],
            'model3_delta': self.results['model3_empirical_plan']['delta_data'],
            'model1_theoretical_line': model1_line,
            'model2_p95_line': self.results['model2_empirical_actual']['safety_stock'],
            'model3_p95_line': self.results['model3_empirical_plan']['safety_stock'],
            'is_p_zero': self.stockout_tolerance_pct <= 0
        }
    
    def _apply_category_limit(self, model_result: Dict, cap_days: int) -> Dict:
        """
        区分別安全在庫上限を適用（日数ベース）
        
        Args:
            model_result: モデルの計算結果
            cap_days: 上限日数
        
        Returns:
            Dict: 上限適用後の計算結果
        """
        # 安全在庫がNoneの場合はそのまま返す
        if model_result.get('safety_stock') is None:
            return model_result
        
        # 日当たり実績平均を計算
        daily_mean = self.actual_data.mean()
        
        if daily_mean <= 0:
            return model_result
        
        # 上限値 = 日平均需要 × 上限日数
        max_stock = daily_mean * cap_days
        
        # 算出された安全在庫と上限値の小さい方を採用
        original_stock = model_result['safety_stock']
        final_safety_stock = min(original_stock, max_stock)
        
        # 実際にカットされたかどうかを判定（元の値が上限値を超えていた場合のみ）
        limit_applied = original_stock > max_stock
        
        # 結果を更新
        model_result['safety_stock'] = final_safety_stock
        model_result['category_limit_applied'] = limit_applied  # 実際にカットされた場合のみTrue
        model_result['category_cap_days'] = cap_days
        model_result['category_max_stock'] = max_stock
        model_result['category_original_stock'] = original_stock
        
        return model_result
    
    def get_summary_stats(self) -> Dict:
        """
        要約統計量を取得
        
        Returns:
            Dict: 要約統計量
        """
        if not self.results:
            self.calculate_all_models()
        
        return {
            '安全在庫①（理論値）': f"{self.results['model1_theoretical']['safety_stock']:.2f}",
            '安全在庫②（実績−平均）': f"{self.results['model2_empirical_actual']['safety_stock']:.2f}",
            '安全在庫③（実績−計画）': f"{self.results['model3_empirical_plan']['safety_stock']:.2f}",
            'リードタイム（稼働日）': f"{self.results['common_params']['lead_time_working_days']:.1f}",
            '欠品許容率（%）': f"{self.results['common_params']['stockout_tolerance_pct']:.1f}",
            'サービスレベル（%）': f"{self.results['common_params']['service_level_pct']:.1f}",
            '安全係数': f"{self.results['common_params']['safety_factor']:.3f}"
        }
