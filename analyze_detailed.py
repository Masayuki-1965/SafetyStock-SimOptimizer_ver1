"""
詳細分析: なぜ安全在庫③が増加するのか
"""
import pandas as pd
import numpy as np
from modules.data_loader import DataLoader
from modules.outlier_handler import OutlierHandler
from modules.safety_stock_models import SafetyStockCalculator

# データ読み込み
data_loader = DataLoader('data/日次計画データ.csv', 'data/日次実績データ.csv')
data_loader.load_data()

product_code = 'KK-157202-AWAA'
plan_data = data_loader.get_daily_plan(product_code)
actual_data = data_loader.get_daily_actual(product_code)
working_dates = data_loader.get_working_dates()

# 異常値処理（σ係数3.0）
sigma_k = 3.0
top_limit_mode = 'count'
top_limit_n = 2

outlier_handler = OutlierHandler(
    actual_data=actual_data,
    working_dates=working_dates,
    sigma_k=sigma_k,
    top_limit_mode=top_limit_mode,
    top_limit_n=top_limit_n
)

processing_result = outlier_handler.detect_and_impute()
corrected_data = processing_result['corrected_data']

# リードタイム設定
lead_time = 45
lead_time_type = 'working_days'
stockout_tolerance = 1.0

# Before/Afterの差分を計算
def calculate_delta3(actual_data, plan_data, lead_time_days):
    actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
    plan_sums = plan_data.rolling(window=lead_time_days).sum().dropna()
    common_idx = actual_sums.index.intersection(plan_sums.index)
    delta3 = actual_sums.loc[common_idx] - plan_sums.loc[common_idx]
    return delta3

delta3_before = calculate_delta3(actual_data, plan_data, lead_time)
delta3_after = calculate_delta3(corrected_data, plan_data, lead_time)

print("=" * 80)
print("【問題の原因分析】")
print("=" * 80)

print("\n1. 異常値がクリップされた日付:")
outlier_indices = outlier_handler.outlier_final_indices
for idx in outlier_indices:
    date = actual_data.index[idx]
    before_value = actual_data.iloc[idx]
    after_value = corrected_data.iloc[idx]
    print(f"  {date.strftime('%Y-%m-%d')}: {before_value} → {after_value}")

print("\n2. リードタイム期間のrolling sumへの影響:")
print(f"  リードタイム: {lead_time}日")
print(f"  異常値を含むrolling sum期間数: 各異常値について{lead_time}個の期間に影響")

# 異常値がクリップされた日付を含むrolling sum期間を特定
print("\n3. 異常値がクリップされた日付を含むrolling sum期間の差分変化:")
for idx in outlier_indices:
    date = actual_data.index[idx]
    date_pos = actual_data.index.get_loc(date)
    
    # この日付を含むrolling sum期間を特定
    affected_periods = []
    for i in range(max(0, date_pos - lead_time + 1), min(len(actual_data), date_pos + 1)):
        if i + lead_time <= len(actual_data):
            period_start = actual_data.index[i]
            period_end = actual_data.index[i + lead_time - 1]
            
            # Before/Afterの差分を計算
            before_sum_actual = actual_data.iloc[i:i+lead_time].sum()
            after_sum_actual = corrected_data.iloc[i:i+lead_time].sum()
            sum_plan = plan_data.iloc[i:i+lead_time].sum()
            
            before_delta = before_sum_actual - sum_plan
            after_delta = after_sum_actual - sum_plan
            
            if before_delta != after_delta:
                affected_periods.append({
                    'start': period_start,
                    'end': period_end,
                    'before_delta': before_delta,
                    'after_delta': after_delta,
                    'change': after_delta - before_delta
                })
    
    if affected_periods:
        print(f"\n  異常値日付: {date.strftime('%Y-%m-%d')}")
        print(f"  影響を受けた期間数: {len(affected_periods)}")
        # 最初の5件を表示
        for i, period in enumerate(affected_periods[:5]):
            print(f"    {period['start'].strftime('%Y-%m-%d')}～{period['end'].strftime('%Y-%m-%d')}: "
                  f"{period['before_delta']:.2f} → {period['after_delta']:.2f} "
                  f"(変化: {period['change']:.2f})")
        
        # 正の差分から負の差分に変わった期間を確認
        positive_to_negative = [p for p in affected_periods if p['before_delta'] > 0 and p['after_delta'] <= 0]
        if positive_to_negative:
            print(f"\n  正の差分から負の差分に変わった期間数: {len(positive_to_negative)}")
            for period in positive_to_negative[:3]:
                print(f"    {period['start'].strftime('%Y-%m-%d')}～{period['end'].strftime('%Y-%m-%d')}: "
                      f"{period['before_delta']:.2f} → {period['after_delta']:.2f}")

print("\n4. 正の差分のサンプル数の変化:")
delta3_positive_before = delta3_before[delta3_before > 0]
delta3_positive_after = delta3_after[delta3_after > 0]
print(f"  Before: {len(delta3_positive_before)}件")
print(f"  After:  {len(delta3_positive_after)}件")
print(f"  減少: {len(delta3_positive_before) - len(delta3_positive_after)}件")

print("\n5. P95の計算に使われるk番目の値の変化:")
q = 1 - stockout_tolerance / 100.0  # 0.99
N_pos_before = len(delta3_positive_before)
N_pos_after = len(delta3_positive_after)
k_before = max(1, int(np.ceil(q * N_pos_before)))
k_after = max(1, int(np.ceil(q * N_pos_after)))

delta3_positive_sorted_before = np.sort(delta3_positive_before.values)
delta3_positive_sorted_after = np.sort(delta3_positive_after.values)

print(f"  Before: N_pos={N_pos_before}, k={k_before}, k番目の値={delta3_positive_sorted_before[k_before-1]:.2f}")
print(f"  After:  N_pos={N_pos_after}, k={k_after}, k番目の値={delta3_positive_sorted_after[k_after-1]:.2f}")

print("\n6. 問題の原因:")
print("  異常値をクリップすることで、リードタイム期間のrolling sumが小さくなり、")
print("  「実績合計 - 計画合計」が正から負に変わる期間が増えました。")
print("  その結果、正の差分のサンプル数が減り、P95の計算に使われるk番目の値が")
print("  変わってしまい、最大値（17.32）が選ばれてしまいました。")

print("\n7. 解決策:")
print("  P95の計算方法を変更し、正の差分のサンプル数が減っても、")
print("  同じパーセンタイル位置（例：上位1%）を使うようにする必要があります。")

