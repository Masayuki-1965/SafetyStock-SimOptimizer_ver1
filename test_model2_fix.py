"""
安全在庫②の修正をテストするスクリプト
商品コード: DD-162182-AWAA
"""
import pandas as pd
import numpy as np
from modules.data_loader import DataLoader
from modules.outlier_handler import OutlierHandler
from modules.safety_stock_models import SafetyStockCalculator

# データ読み込み
data_loader = DataLoader('data/日次計画データ.csv', 'data/日次実績データ.csv')
data_loader.load_data()

product_code = 'DD-162182-AWAA'
plan_data = data_loader.get_daily_plan(product_code)
actual_data = data_loader.get_daily_actual(product_code)
working_dates = data_loader.get_working_dates()

print("=" * 80)
print(f"商品コード: {product_code}")
print("=" * 80)

# 異常値処理のパラメータ
sigma_k = 3.0
top_limit_mode = 'count'
top_limit_n = 2

# 異常値処理
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

# Before: 異常値処理前の安全在庫②を計算
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
model2_before = results_before['model2_empirical_actual']

lead_time_days = int(np.ceil(calculator_before._get_lead_time_in_working_days()))
actual_sums_before = actual_data.rolling(window=lead_time_days).sum().dropna()
mean_before = actual_sums_before.mean()

print(f"\n安全在庫② Before: {model2_before['safety_stock']:.4f}")
print(f"リードタイム期間の実績合計の平均 Before: {mean_before:.4f}")

# After: 異常値処理後の安全在庫②を計算（修正後）
calculator_after = SafetyStockCalculator(
    plan_data=plan_data,
    actual_data=corrected_data,
    working_dates=working_dates,
    lead_time=lead_time,
    lead_time_type=lead_time_type,
    stockout_tolerance_pct=stockout_tolerance,
    std_calculation_method='population',
    category_cap_days={},
    original_actual_data=actual_data  # 異常値処理前のデータを渡す
)

results_after = calculator_after.calculate_all_models()
model2_after = results_after['model2_empirical_actual']

actual_sums_after = corrected_data.rolling(window=lead_time_days).sum().dropna()
original_actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
mean_after_calc = original_actual_sums.mean()

print(f"\n安全在庫② After:  {model2_after['safety_stock']:.4f}")
print(f"リードタイム期間の実績合計の平均 After (originalから計算): {mean_after_calc:.4f}")
print(f"変化: {model2_after['safety_stock'] - model2_before['safety_stock']:.4f}")
print(f"変化率: {(model2_after['safety_stock'] / model2_before['safety_stock'] - 1) * 100:.2f}%")

# 差分の最大値を確認
delta2_before = pd.Series(model2_before['delta_data'])
delta2_after = pd.Series(model2_after['delta_data'])
delta2_positive_before = delta2_before[delta2_before > 0]
delta2_positive_after = delta2_after[delta2_after > 0]

print(f"\n正の差分の最大値 Before: {delta2_positive_before.max():.4f}")
print(f"正の差分の最大値 After:  {delta2_positive_after.max():.4f}")

if model2_after['safety_stock'] < model2_before['safety_stock']:
    print("\n修正成功: 安全在庫②が減少しました")
else:
    print("\n修正失敗: 安全在庫②が増加または変化なし")

