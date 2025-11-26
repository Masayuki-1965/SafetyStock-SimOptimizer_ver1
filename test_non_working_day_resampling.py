"""
非稼働日実績の翌稼働日への合算処理の詳細検証

確認項目：
- 非稼働日実績が単独で存在するとき
- 非稼働日実績が連続して存在するとき
- 最終稼働日以降に実績が存在するとき（破棄されていること）
"""

import pandas as pd
import numpy as np
from modules.data_loader import DataLoader

print("=" * 80)
print("非稼働日実績の翌稼働日への合算処理の詳細検証")
print("=" * 80)

# テスト用のデータを作成
# 計画データ（稼働日のみ）
working_dates = pd.date_range('2024-06-03', '2024-06-14', freq='B')  # 月〜金のみ
plan_df = pd.DataFrame(
    index=['TEST-PRODUCT'],
    columns=working_dates,
    data=np.random.uniform(10, 20, (1, len(working_dates)))
)

# 実績データ（非稼働日を含む）
# 2024-06-03(月), 2024-06-04(火), 2024-06-05(水), 2024-06-06(木), 2024-06-07(金)
# 2024-06-08(土) <- 非稼働日
# 2024-06-09(日) <- 非稼働日
# 2024-06-10(月), 2024-06-11(火), 2024-06-12(水), 2024-06-13(木), 2024-06-14(金)

actual_dates = pd.date_range('2024-06-03', '2024-06-14', freq='D')  # 全日付
actual_df = pd.DataFrame(
    index=['TEST-PRODUCT'],
    columns=actual_dates,
    data=0.0
)

# テストケース1: 非稼働日実績が単独で存在する
actual_df.loc['TEST-PRODUCT', '2024-06-08'] = 100.0  # 土曜日（非稼働日）

# テストケース2: 非稼働日実績が連続して存在する
actual_df.loc['TEST-PRODUCT', '2024-06-09'] = 200.0  # 日曜日（非稼働日）

# テストケース3: 最終稼働日以降に実績が存在する
actual_df.loc['TEST-PRODUCT', '2024-06-15'] = 300.0  # 最終稼働日以降

# 稼働日の実績も設定
actual_df.loc['TEST-PRODUCT', '2024-06-03'] = 50.0  # 月曜日（稼働日）
actual_df.loc['TEST-PRODUCT', '2024-06-10'] = 75.0  # 月曜日（稼働日）

print("\n【テストデータ】")
print(f"計画データの日付（稼働日）: {len(plan_df.columns)}件")
print(f"  開始: {plan_df.columns[0]}")
print(f"  終了: {plan_df.columns[-1]}")

print(f"\n実績データの日付（全日付）: {len(actual_df.columns)}件")
print(f"  開始: {actual_df.columns[0]}")
print(f"  終了: {actual_df.columns[-1]}")

print(f"\n実績データの値:")
for date in actual_df.columns:
    value = actual_df.loc['TEST-PRODUCT', date]
    if value != 0:
        is_working = date in plan_df.columns
        print(f"  {date.strftime('%Y-%m-%d')} ({date.strftime('%a')}): {value:.1f} {'[稼働日]' if is_working else '[非稼働日]'}")

# DataLoaderを使用して再サンプリング
data_loader = DataLoader('data/日次計画データ.csv', 'data/日次実績データ.csv')
data_loader.plan_df = plan_df
data_loader.actual_df = actual_df
data_loader.working_dates = plan_df.columns

# 稼働日マスタを作成（テスト用）
working_days_master = pd.DataFrame({
    '日時': working_dates,
    '曜日': [d.strftime('%a') for d in working_dates],
    '年月': [d.strftime('%Y%m') for d in working_dates],
    '稼働日区分': [1] * len(working_dates)
})
data_loader.working_days_master_df = working_days_master

# 再サンプリング実行
data_loader._resample_actual_to_working_days()

# 結果確認
resampled_actual = data_loader.actual_df_resampled.loc['TEST-PRODUCT']

print("\n" + "=" * 80)
print("【再サンプリング結果】")
print("=" * 80)

print(f"\n再サンプリング後の実績データ: {len(resampled_actual)}件")
print(f"  開始: {resampled_actual.index[0]}")
print(f"  終了: {resampled_actual.index[-1]}")

print(f"\n再サンプリング後の実績データの値:")
for date in resampled_actual.index:
    value = resampled_actual.loc[date]
    if value != 0:
        print(f"  {date.strftime('%Y-%m-%d')} ({date.strftime('%a')}): {value:.1f}")

# 検証
print("\n" + "=" * 80)
print("【検証結果】")
print("=" * 80)

# テストケース1: 非稼働日実績（2024-06-08土曜日）が翌稼働日（2024-06-10月曜日）に合算されているか
test1_original = actual_df.loc['TEST-PRODUCT', '2024-06-08']
test1_resampled = resampled_actual.loc['2024-06-10']
test1_expected = 50.0 + 100.0  # 元の月曜日の値 + 土曜日の値

print(f"\nテストケース1: 非稼働日実績が単独で存在するとき")
print(f"  元の実績（2024-06-08土曜日）: {test1_original:.1f}")
print(f"  再サンプリング後（2024-06-10月曜日）: {test1_resampled:.1f}")
print(f"  期待値（50.0 + 100.0）: {test1_expected:.1f}")
if abs(test1_resampled - test1_expected) < 0.01:
    print(f"  OK: 正しく翌稼働日に合算されています")
else:
    print(f"  ERROR: 合算が正しくありません")

# テストケース2: 非稼働日実績が連続して存在するとき
test2_original_sat = actual_df.loc['TEST-PRODUCT', '2024-06-08']
test2_original_sun = actual_df.loc['TEST-PRODUCT', '2024-06-09']
test2_resampled = resampled_actual.loc['2024-06-10']
test2_expected = 50.0 + 100.0 + 200.0  # 元の月曜日の値 + 土曜日の値 + 日曜日の値

print(f"\nテストケース2: 非稼働日実績が連続して存在するとき")
print(f"  元の実績（2024-06-08土曜日）: {test2_original_sat:.1f}")
print(f"  元の実績（2024-06-09日曜日）: {test2_original_sun:.1f}")
print(f"  再サンプリング後（2024-06-10月曜日）: {test2_resampled:.1f}")
print(f"  期待値（50.0 + 100.0 + 200.0）: {test2_expected:.1f}")
if abs(test2_resampled - test2_expected) < 0.01:
    print(f"  OK: 連続する非稼働日実績が正しく翌稼働日に合算されています")
else:
    print(f"  ERROR: 合算が正しくありません")

# テストケース3: 最終稼働日以降に実績が存在するとき（破棄されていること）
test3_original = actual_df.loc['TEST-PRODUCT', '2024-06-15']
test3_in_resampled = '2024-06-15' in resampled_actual.index

print(f"\nテストケース3: 最終稼働日以降に実績が存在するとき")
print(f"  元の実績（2024-06-15）: {test3_original:.1f}")
print(f"  再サンプリング後のインデックスに含まれる: {test3_in_resampled}")
if not test3_in_resampled:
    print(f"  OK: 最終稼働日以降の実績は破棄されています")
else:
    print(f"  ERROR: 最終稼働日以降の実績が含まれています")

# 最終稼働日の値が変更されていないことを確認
final_working_day_value = resampled_actual.loc['2024-06-14']
print(f"  最終稼働日（2024-06-14）の値: {final_working_day_value:.1f}")
if final_working_day_value == 0.0:
    print(f"  OK: 最終稼働日の値は変更されていません（破棄されている）")
else:
    print(f"  WARNING: 最終稼働日の値が変更されています")

print("\n" + "=" * 80)
print("検証完了")
print("=" * 80)

