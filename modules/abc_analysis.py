"""
ABC分析モジュール

ABC区分自動生成機能
- 構成比率で区分：実績値の多い順にソートし、累積構成比率で分類
- 数量範囲で区分：月平均実績値の多い順にソートし、数量範囲で分類
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import OrderedDict


class ABCAnalysis:
    """ABC分析クラス"""
    
    # 利用可能な区分ラベル（A〜Z）
    AVAILABLE_CATEGORIES = [chr(ord('A') + i) for i in range(26)]
    # 追加可能な区分（要件：D〜H と Z）
    ALLOWED_ADDITIONAL_CATEGORIES = ['D', 'E', 'F', 'G', 'H', 'Z']
    
    def __init__(self, data_loader, classification_unit: Optional[str] = None):
        """
        初期化
        
        Args:
            data_loader: DataLoaderインスタンス
            classification_unit: 分類単位（Noneの場合は全商品を対象）
        """
        self.data_loader = data_loader
        self.classification_unit = classification_unit

    def _get_target_months(self) -> int:
        """分析対象期間の月数（開始月/終了月を含む）を返す"""
        working_dates = self.data_loader.get_working_dates()
        if len(working_dates) == 0:
            return 1
        start_date = working_dates[0]
        end_date = working_dates[-1]
        months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
        return max(1, months_diff)
        
    def get_all_products_data(self) -> pd.DataFrame:
        """
        全商品の実績データを取得
        
        Returns:
            pd.DataFrame: 商品コードと実績値合計、月平均実績値を含むDataFrame
        """
        if self.data_loader.actual_df is None:
            self.data_loader.load_data()
        
        # 全期間の実績値合計を計算
        actual_totals = self.data_loader.actual_df.sum(axis=1)
        
        # 対象月数を計算
        target_months = self._get_target_months()
        
        # 月平均実績値を計算
        monthly_avg = actual_totals / target_months
        
        # DataFrameを作成
        result_df = pd.DataFrame({
            'product_code': actual_totals.index,
            'total_actual': actual_totals.values,
            'monthly_avg_actual': monthly_avg.values
        })
        
        # 分類単位でフィルタリング（指定されている場合）
        if self.classification_unit and self.classification_unit != "全て":
            # 分類単位は商品コードの特定部分を抽出する想定
            # ここでは簡易的に商品コードの先頭部分で判定
            result_df = result_df[
                result_df['product_code'].str.startswith(self.classification_unit)
            ]
        
        return result_df
    
    def analyze_by_ratio(
        self,
        categories: List[str],
        end_ratios: Dict[str, float]
    ) -> pd.DataFrame:
        """
        構成比率でABC分析を実行
        
        Args:
            categories: 区分ラベルのリスト（例: ['A', 'B', 'C']）
            end_ratios: 各区分の終了％の辞書（例: {'A': 50, 'B': 80, 'C': 100}）
        
        Returns:
            pd.DataFrame: 商品コード、ABC区分を含むDataFrame
        """
        # 全商品の実績値合計を取得
        products_df = self.get_all_products_data()
        
        # 実績値の多い順にソート
        products_df = products_df.sort_values('total_actual', ascending=False).reset_index(drop=True)
        
        # 累積実績値を計算
        total_sum = products_df['total_actual'].sum()
        products_df['cumulative_actual'] = products_df['total_actual'].cumsum()
        products_df['cumulative_ratio'] = (products_df['cumulative_actual'] / total_sum * 100) if total_sum > 0 else 0
        
        # ABC区分を割り当て
        products_df['abc_category'] = None
        
        # 各区分の開始％と終了％を計算
        start_ratios = {}
        prev_end = 0
        for i, cat in enumerate(categories):
            if i == 0:
                start_ratios[cat] = 0
            else:
                start_ratios[cat] = end_ratios[categories[i-1]]
            prev_end = end_ratios[cat]
        
        # 各区分に商品を割り当て
        for cat in categories:
            start_ratio = start_ratios[cat]
            end_ratio = end_ratios[cat]
            
            # 累積構成比率に基づいて区分を割り当て
            mask = (products_df['cumulative_ratio'] > start_ratio) & (products_df['cumulative_ratio'] <= end_ratio)
            products_df.loc[mask, 'abc_category'] = cat
        
        # 最終区分に残りの商品を割り当て（念のため）
        if categories:
            last_cat = categories[-1]
            products_df.loc[products_df['abc_category'].isna(), 'abc_category'] = last_cat
        
        return products_df[['product_code', 'abc_category', 'total_actual', 'monthly_avg_actual', 'cumulative_ratio']]
    
    def analyze_by_range(
        self,
        categories: List[str],
        lower_limits: Dict[str, float]
    ) -> pd.DataFrame:
        """
        数量範囲でABC分析を実行
        
        Args:
            categories: 区分ラベルのリスト（例: ['A', 'B', 'C']）
            lower_limits: 各区分の下限値の辞書（例: {'A': 115, 'B': 25, 'C': 0}）
        
        Returns:
            pd.DataFrame: 商品コード、ABC区分を含むDataFrame
        """
        # 全商品のデータを取得（total_actual と monthly_avg_actual を両方持つ）
        products_df = self.get_all_products_data()
        
        # しきい値（月平均で入力）→ 全期間数量へ変換
        target_months = self._get_target_months()
        lower_limits_total = {cat: float(lower_limits.get(cat, 0.0)) * target_months for cat in categories}
        
        # 実績合計の多い順にソート（集計も実績合計ベースのため）
        products_df = products_df.sort_values('total_actual', ascending=False).reset_index(drop=True)
        
        # ABC区分を割り当て（連続したしきい値で範囲分割）
        products_df['abc_category'] = None
        
        # 直前区分の下限値を上限として使用（Aは上限なし＝inf）
        prev_lower = float('inf')
        for i, cat in enumerate(categories):
            current_lower = float(lower_limits_total.get(cat, 0.0))
            if i == 0:
                # A区分：current_lower より大きい全て（実績合計ベース）
                mask = products_df['total_actual'] > current_lower
            elif i == len(categories) - 1:
                # 最終区分：current_lower 以下（0固定を想定）
                mask = products_df['total_actual'] <= current_lower
            else:
                # 中間区分：current_lower < x <= prev_lower（実績合計ベース）
                mask = (products_df['total_actual'] > current_lower) & (products_df['total_actual'] <= prev_lower)
            
            products_df.loc[mask, 'abc_category'] = cat
            prev_lower = current_lower
        
        # 未割り当ての商品を最後の区分に割り当て（念のため）
        if categories:
            last_cat = categories[-1]
            products_df.loc[products_df['abc_category'].isna(), 'abc_category'] = last_cat
        
        return products_df[['product_code', 'abc_category', 'total_actual', 'monthly_avg_actual']]
    
    def calculate_aggregation_results(self, analysis_result: pd.DataFrame) -> pd.DataFrame:
        """
        ABC区分ごとの集計結果を計算
        
        Args:
            analysis_result: ABC分析の結果DataFrame
        
        Returns:
            pd.DataFrame: ABC区分ごとの件数・実績合計・構成比率
        """
        # 区分ごとに集計
        aggregation = analysis_result.groupby('abc_category').agg({
            'product_code': 'count',
            'total_actual': 'sum'
        }).rename(columns={
            'product_code': 'count',
            'total_actual': 'total_actual'
        })
        
        # 構成比率を計算
        total_actual_sum = analysis_result['total_actual'].sum()
        aggregation['composition_ratio'] = (aggregation['total_actual'] / total_actual_sum * 100) if total_actual_sum > 0 else 0
        
        # 合計行を追加
        total_row = pd.DataFrame({
            'count': [aggregation['count'].sum()],
            'total_actual': [aggregation['total_actual'].sum()],
            'composition_ratio': [100.0]
        }, index=['合計'])
        
        aggregation = pd.concat([aggregation, total_row])
        
        # インデックス名を設定
        aggregation.index.name = 'ABC区分'
        
        return aggregation.reset_index()
    
    def calculate_dynamic_defaults(self, categories: List[str]) -> Dict[str, float]:
        """
        数量範囲方式用の動的デフォルト値（累積構成比率50%・80%に相当する値）を計算
        
        Args:
            categories: 区分ラベルのリスト（例: ['A', 'B', 'C']）
        
        Returns:
            Dict[str, float]: 各区分の下限値の辞書
        """
        # 全商品のデータを取得
        products_df = self.get_all_products_data()
        
        # 累積実績（全期間合計）を計算し、合計ベースで50%・80%を求める
        products_df = products_df.sort_values('total_actual', ascending=False).reset_index(drop=True)
        total_sum = products_df['total_actual'].sum()
        products_df['cumulative_actual'] = products_df['total_actual'].cumsum()
        products_df['cumulative_ratio'] = (products_df['cumulative_actual'] / total_sum * 100) if total_sum > 0 else 0
        
        # A区分とB区分の下限値を計算（累積構成比率50%・80%、全期間合計ベース）
        defaults = {}
        target_months = self._get_target_months()
        
        # 最終区分の下限値は0（追加区分を含めた最後の要素）
        if len(categories) > 0:
            defaults[categories[-1]] = 0.0
        
        # B区分の下限値（累積構成比率80%に相当）
        if 'B' in categories:
            b_threshold_idx = products_df[products_df['cumulative_ratio'] <= 80].index
            if len(b_threshold_idx) > 0:
                b_threshold_total = products_df.loc[b_threshold_idx[-1], 'total_actual']
                # 表示は月平均のため月数で割る
                defaults['B'] = max(0.0, b_threshold_total / target_months)
            else:
                defaults['B'] = 0.0
        
        # A区分の下限値（累積構成比率50%に相当）
        if 'A' in categories:
            a_threshold_idx = products_df[products_df['cumulative_ratio'] <= 50].index
            if len(a_threshold_idx) > 0:
                a_threshold_total = products_df.loc[a_threshold_idx[-1], 'total_actual']
                defaults['A'] = max(0.0, a_threshold_total / target_months)
            else:
                defaults['A'] = 0.0
        
        # A・B 以外の残り区分（Cや追加区分）は 0.0 を設定
        for cat in categories:
            if cat not in defaults:
                defaults[cat] = 0.0
        
        return defaults
    
    @staticmethod
    def get_available_categories(existing_categories: List[str]) -> List[str]:
        """
        追加可能な区分ラベルのリストを取得
        
        Args:
            existing_categories: 既存の区分ラベル
        
        Returns:
            List[str]: 追加可能な区分ラベルのリスト
        """
        allowed = set(ABCAnalysis.ALLOWED_ADDITIONAL_CATEGORIES)
        available = [
            cat for cat in ABCAnalysis.AVAILABLE_CATEGORIES
            if cat not in existing_categories and cat in allowed
        ]
        return available

