"""
KK-157202-AWAAの異常値処理前後の安全在庫③を分析するスクリプト
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

print("=" * 80)
print(f"商品コード: {product_code}")
print("=" * 80)

# 基本統計
print("\n【基本統計】")
print(f"実績データ件数: {len(actual_data)}")
print(f"実績データ最大値: {actual_data.max()}")
print(f"実績データ平均: {actual_data.mean():.2f}")
print(f"実績データ標準偏差: {actual_data.std():.2f}")
print(f"実績データ>0の平均: {actual_data[actual_data > 0].mean():.2f}")
print(f"実績データ>0の標準偏差: {actual_data[actual_data > 0].std():.2f}")

# 異常値処理のパラメータ（実際のUI設定を確認）
# σ係数6.0では検出されない可能性があるため、3.0でも試す
sigma_k = 3.0  # まず3.0で試す
top_limit_mode = 'count'
top_limit_n = 2
top_limit_p = 2.0

# 異常値処理
outlier_handler = OutlierHandler(
    actual_data=actual_data,
    working_dates=working_dates,
    sigma_k=sigma_k,
    top_limit_mode=top_limit_mode,
    top_limit_n=top_limit_n,
    top_limit_p=top_limit_p
)

processing_result = outlier_handler.detect_and_impute()
corrected_data = processing_result['corrected_data']
processing_info = processing_result['processing_info']

print("\n【異常値処理結果】")
print(f"異常候補数: {processing_info['candidate_count']}")
print(f"最終補正数: {processing_info['final_count']}")
threshold_global = processing_info.get('threshold_global')
if threshold_global is not None:
    print(f"threshold_global: {threshold_global:.2f}")
else:
    print(f"threshold_global: None")
if processing_info['final_count'] > 0:
    outlier_indices = outlier_handler.outlier_final_indices
    print(f"\n補正された日付と値:")
    for idx in outlier_indices:
        before_value = actual_data.iloc[idx]
        after_value = corrected_data.iloc[idx]
        date = actual_data.index[idx]
        print(f"  {date.strftime('%Y-%m-%d')}: {before_value} → {after_value}")

# リードタイム設定（UIのデフォルト値）
lead_time = 45
lead_time_type = 'working_days'
stockout_tolerance = 1.0

# Before: 異常値処理前の安全在庫③を計算
print("\n" + "=" * 80)
print("【Before: 異常値処理前の安全在庫③】")
print("=" * 80)

calculator_before = SafetyStockCalculator(
    plan_data=plan_data,
    actual_data=actual_data,
    working_dates=working_dates,
    lead_time=lead_time,
    lead_time_type=lead_time_type,
    stockout_tolerance_pct=stockout_tolerance,
    std_calculation_method='population',
    category_cap_days={}
)

results_before = calculator_before.calculate_all_models()
model3_before = results_before['model3_empirical_plan']

print(f"安全在庫③: {model3_before['safety_stock']:.2f}")
print(f"正の差分のサンプル数: {len([d for d in model3_before['delta_data'] if d > 0])}")
print(f"全差分のサンプル数: {len(model3_before['delta_data'])}")
print(f"平均差分: {model3_before['mean_delta']:.2f}")
print(f"標準偏差: {model3_before['std_delta']:.2f}")

# 正の差分の分布を確認
delta3_before = pd.Series(model3_before['delta_data'])
delta3_positive_before = delta3_before[delta3_before > 0]
if len(delta3_positive_before) > 0:
    print(f"\n正の差分の統計:")
    print(f"  最小値: {delta3_positive_before.min():.2f}")
    print(f"  最大値: {delta3_positive_before.max():.2f}")
    print(f"  平均: {delta3_positive_before.mean():.2f}")
    print(f"  中央値: {delta3_positive_before.median():.2f}")
    print(f"  P95: {np.percentile(delta3_positive_before, 95):.2f}")
    print(f"  P99: {np.percentile(delta3_positive_before, 99):.2f}")
    
    # P95の計算に使われるk番目の値を確認
    q = 1 - stockout_tolerance / 100.0  # 0.99
    N_pos_before = len(delta3_positive_before)
    k_before = max(1, int(np.ceil(q * N_pos_before)))
    delta3_positive_sorted_before = np.sort(delta3_positive_before.values)
    print(f"\nP95計算の詳細:")
    print(f"  N_pos: {N_pos_before}")
    print(f"  q: {q}")
    print(f"  k: {k_before}")
    print(f"  k番目の値: {delta3_positive_sorted_before[k_before - 1]:.2f}")

# After: 異常値処理後の安全在庫③を計算
print("\n" + "=" * 80)
print("【After: 異常値処理後の安全在庫③】")
print("=" * 80)

calculator_after = SafetyStockCalculator(
    plan_data=plan_data,
    actual_data=corrected_data,
    working_dates=working_dates,
    lead_time=lead_time,
    lead_time_type=lead_time_type,
    stockout_tolerance_pct=stockout_tolerance,
    std_calculation_method='population',
    category_cap_days={}
)

results_after = calculator_after.calculate_all_models()
model3_after = results_after['model3_empirical_plan']

print(f"安全在庫③: {model3_after['safety_stock']:.2f}")
print(f"正の差分のサンプル数: {len([d for d in model3_after['delta_data'] if d > 0])}")
print(f"全差分のサンプル数: {len(model3_after['delta_data'])}")
print(f"平均差分: {model3_after['mean_delta']:.2f}")
print(f"標準偏差: {model3_after['std_delta']:.2f}")

# 正の差分の分布を確認
delta3_after = pd.Series(model3_after['delta_data'])
delta3_positive_after = delta3_after[delta3_after > 0]
if len(delta3_positive_after) > 0:
    print(f"\n正の差分の統計:")
    print(f"  最小値: {delta3_positive_after.min():.2f}")
    print(f"  最大値: {delta3_positive_after.max():.2f}")
    print(f"  平均: {delta3_positive_after.mean():.2f}")
    print(f"  中央値: {delta3_positive_after.median():.2f}")
    print(f"  P95: {np.percentile(delta3_positive_after, 95):.2f}")
    print(f"  P99: {np.percentile(delta3_positive_after, 99):.2f}")
    
    # P95の計算に使われるk番目の値を確認
    q = 1 - stockout_tolerance / 100.0  # 0.99
    N_pos_after = len(delta3_positive_after)
    k_after = max(1, int(np.ceil(q * N_pos_after)))
    delta3_positive_sorted_after = np.sort(delta3_positive_after.values)
    print(f"\nP95計算の詳細:")
    print(f"  N_pos: {N_pos_after}")
    print(f"  q: {q}")
    print(f"  k: {k_after}")
    print(f"  k番目の値: {delta3_positive_sorted_after[k_after - 1]:.2f}")

# 比較
print("\n" + "=" * 80)
print("【比較結果】")
print("=" * 80)
print(f"安全在庫③ Before: {model3_before['safety_stock']:.2f}")
print(f"安全在庫③ After:  {model3_after['safety_stock']:.2f}")
print(f"変化: {model3_after['safety_stock'] - model3_before['safety_stock']:.2f}")
print(f"変化率: {(model3_after['safety_stock'] / model3_before['safety_stock'] - 1) * 100:.1f}%")

if len(delta3_positive_before) > 0 and len(delta3_positive_after) > 0:
    print(f"\n正の差分のサンプル数:")
    print(f"  Before: {N_pos_before}")
    print(f"  After:  {N_pos_after}")
    print(f"  変化: {N_pos_after - N_pos_before}")
    
    print(f"\nP95計算のk値:")
    print(f"  Before: k={k_before} (N_pos={N_pos_before})")
    print(f"  After:  k={k_after} (N_pos={N_pos_after})")
    
    # 差分の最大値を比較
    print(f"\n正の差分の最大値:")
    print(f"  Before: {delta3_positive_before.max():.2f}")
    print(f"  After:  {delta3_positive_after.max():.2f}")
    
    # 差分の分布を比較（上位10件）
    print(f"\n正の差分の上位10件 (Before):")
    top10_before = delta3_positive_sorted_before[-10:][::-1]
    for i, val in enumerate(top10_before, 1):
        print(f"  {i}. {val:.2f}")
    
    print(f"\n正の差分の上位10件 (After):")
    top10_after = delta3_positive_sorted_after[-10:][::-1]
    for i, val in enumerate(top10_after, 1):
        print(f"  {i}. {val:.2f}")

