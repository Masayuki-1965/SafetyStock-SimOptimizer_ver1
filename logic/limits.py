"""
上限カットロジック
ABC区分ごとの上限日数設定に基づいて安全在庫をカットする処理
"""

from typing import Dict, Optional
import pandas as pd


def apply_category_limit(
    model_result: Dict,
    daily_mean: float,
    cap_days: Optional[int]
) -> Dict:
    """
    区分別安全在庫上限を適用（日数ベース）
    
    Args:
        model_result: モデルの計算結果（safety_stockキーを含む）
        daily_mean: 日当たり実績平均
        cap_days: 上限日数（Noneの場合は上限なし）
    
    Returns:
        Dict: 上限適用後の計算結果
    """
    # 上限日数がNoneまたは0の場合は上限なし
    if cap_days is None or cap_days == 0:
        return model_result
    
    # 安全在庫がNoneの場合はそのまま返す
    if model_result.get('safety_stock') is None:
        return model_result
    
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


def apply_limits_to_results(
    results: Dict,
    daily_mean: float,
    category_cap_days: Dict[str, Optional[int]],
    abc_category: Optional[str] = None
) -> Dict:
    """
    安全在庫計算結果に上限カットを適用
    
    Args:
        results: 安全在庫計算結果（model1_theoretical, model2_empirical_actual, model3_empirical_planを含む）
        daily_mean: 日当たり実績平均
        category_cap_days: 区分別上限日数の辞書（例: {'A': 40, 'B': 40, 'C': 40}）
        abc_category: ABC区分（'A', 'B', 'C'など）
    
    Returns:
        Dict: 上限適用後の計算結果
    """
    # ABC区分に応じた上限日数を取得
    cap_days = None
    if abc_category and abc_category in category_cap_days:
        cap_days = category_cap_days[abc_category]
    
    # 各モデルの結果に上限を適用
    updated_results = results.copy()
    
    if 'model1_theoretical' in updated_results:
        updated_results['model1_theoretical'] = apply_category_limit(
            updated_results['model1_theoretical'].copy(),
            daily_mean,
            cap_days
        )
    
    if 'model2_empirical_actual' in updated_results:
        updated_results['model2_empirical_actual'] = apply_category_limit(
            updated_results['model2_empirical_actual'].copy(),
            daily_mean,
            cap_days
        )
    
    if 'model3_empirical_plan' in updated_results:
        updated_results['model3_empirical_plan'] = apply_category_limit(
            updated_results['model3_empirical_plan'].copy(),
            daily_mean,
            cap_days
        )
    
    return updated_results

