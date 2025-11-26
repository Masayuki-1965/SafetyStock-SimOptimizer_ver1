"""
実績データの稼働日ベース再サンプリングの検証スクリプト

確認項目：
1. _resample_actual_to_working_days()の実装が実際に使用されているか
2. 非稼働日実績の翌稼働日への合算が正しく動作しているか
3. rolling計算と総件数が稼働日ベースで正しく計算されているか
4. 差分計算が正しく動作しているか
5. データ型・インデックスの整合性
"""

import pandas as pd
import numpy as np
from modules.data_loader import DataLoader
from modules.safety_stock_models import SafetyStockCalculator

print("=" * 80)
print("実績データの稼働日ベース再サンプリング検証")
print("=" * 80)

# データ読み込み
data_loader = DataLoader('data/日次計画データ.csv', 'data/日次実績データ.csv')
data_loader.load_data()

# サンプル商品コードを取得
product_list = data_loader.get_product_list()
if len(product_list) == 0:
    print("❌ 商品コードが見つかりません")
    exit(1)

sample_product = product_list[0]
print(f"\n【サンプル商品コード】: {sample_product}")

# ========================================
# 1️⃣ _resample_actual_to_working_days()の実装が実際に使用されているか確認
# ========================================
print("\n" + "=" * 80)
print("1. _resample_actual_to_working_days()の実装が実際に使用されているか確認")
print("=" * 80)

plan_data = data_loader.get_daily_plan(sample_product)
actual_data = data_loader.get_daily_actual(sample_product)
working_dates = data_loader.get_working_dates()

print(f"\n計画データのインデックス（稼働日）:")
print(f"  件数: {len(plan_data)}")
print(f"  開始日: {plan_data.index[0]}")
print(f"  終了日: {plan_data.index[-1]}")
print(f"  型: {type(plan_data.index)}")

print(f"\n実績データのインデックス（get_daily_actual()の戻り値）:")
print(f"  件数: {len(actual_data)}")
print(f"  開始日: {actual_data.index[0]}")
print(f"  終了日: {actual_data.index[-1]}")
print(f"  型: {type(actual_data.index)}")

# 計画データと実績データのインデックスが一致しているか確認
if len(plan_data) == len(actual_data):
    index_match = (plan_data.index == actual_data.index).all()
    print(f"\nOK: 計画データと実績データのインデックスが一致: {index_match}")
    if index_match:
        print("   -> 実績データは稼働日ベースに再サンプリングされています")
    else:
        print("   WARNING: インデックスが一致していません")
else:
    print(f"\nWARNING: 計画データと実績データの件数が異なります")
    print(f"   計画: {len(plan_data)}, 実績: {len(actual_data)}")

# 再サンプリング済みデータが存在するか確認
if data_loader.actual_df_resampled is not None:
    print(f"\nOK: actual_df_resampledが存在します")
    print(f"   形状: {data_loader.actual_df_resampled.shape}")
else:
    print(f"\nWARNING: actual_df_resampledが存在しません")

# ========================================
# 2️⃣ 非稼働日実績の翌稼働日への合算が正しく動作しているか確認
# ========================================
print("\n" + "=" * 80)
print("2. 非稼働日実績の翌稼働日への合算が正しく動作しているか確認")
print("=" * 80)

# 元の実績データを確認
original_actual = data_loader.actual_df.loc[sample_product]
resampled_actual = data_loader.actual_df_resampled.loc[sample_product]

print(f"\n元の実績データ:")
print(f"  件数: {len(original_actual)}")
print(f"  非ゼロ値の件数: {(original_actual != 0).sum()}")

print(f"\n再サンプリング後の実績データ:")
print(f"  件数: {len(resampled_actual)}")
print(f"  非ゼロ値の件数: {(resampled_actual != 0).sum()}")

# 稼働日マスタを確認
if data_loader.working_days_master_df is not None and not data_loader.working_days_master_df.empty:
    working_days_master = data_loader.working_days_master_df[
        data_loader.working_days_master_df['稼働日区分'] == 1
    ]
    print(f"\n稼働日マスタ:")
    print(f"  稼働日数: {len(working_days_master)}")
    
    # 元の実績データに非稼働日が含まれているか確認
    original_dates = set(original_actual.index.normalize())
    working_dates_set = set(working_days_master['日時'].dt.normalize())
    non_working_dates_in_actual = original_dates - working_dates_set
    
    if len(non_working_dates_in_actual) > 0:
        print(f"\nWARNING: 元の実績データに非稼働日が含まれています: {len(non_working_dates_in_actual)}件")
        print(f"   非稼働日の例: {sorted(list(non_working_dates_in_actual))[:5]}")
        
        # 非稼働日の実績が翌稼働日に合算されているか確認
        print(f"\n非稼働日実績の合算確認:")
        for non_wd in sorted(list(non_working_dates_in_actual))[:3]:
            non_wd_value = original_actual.loc[original_actual.index.normalize() == non_wd]
            if len(non_wd_value) > 0 and non_wd_value.iloc[0] != 0:
                # 翌稼働日を探す
                next_wd = None
                for wd in working_days_master['日時'].dt.normalize():
                    if wd > non_wd:
                        next_wd = wd
                        break
                
                if next_wd is not None:
                    next_wd_value = resampled_actual.loc[resampled_actual.index.normalize() == next_wd]
                    if len(next_wd_value) > 0:
                        print(f"   {non_wd} ({non_wd_value.iloc[0]:.2f}) → {next_wd} ({next_wd_value.iloc[0]:.2f})")
    else:
        print(f"\nOK: 元の実績データに非稼働日は含まれていません")
else:
    print(f"\nWARNING: 稼働日マスタが読み込まれていません")

# ========================================
# 3️⃣ rolling計算と総件数が稼働日ベースで正しく計算されているか確認
# ========================================
print("\n" + "=" * 80)
print("3. rolling計算と総件数が稼働日ベースで正しく計算されているか確認")
print("=" * 80)

lead_time = 5
lead_time_type = 'working_days'
stockout_tolerance = 1.0

calculator = SafetyStockCalculator(
    plan_data=plan_data,
    actual_data=actual_data,
    working_dates=working_dates,
    lead_time=lead_time,
    lead_time_type=lead_time_type,
    stockout_tolerance_pct=stockout_tolerance,
    std_calculation_method='population'
)

lead_time_working_days = calculator._get_lead_time_in_working_days()
lead_time_days = int(np.ceil(lead_time_working_days))

print(f"\nリードタイム設定:")
print(f"  リードタイム: {lead_time} ({lead_time_type})")
print(f"  稼働日数: {lead_time_working_days:.2f}")
print(f"  計算用日数: {lead_time_days}")

# rolling計算
actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
plan_sums = plan_data.rolling(window=lead_time_days).sum().dropna()

print(f"\nrolling計算結果:")
print(f"  実績合計の件数: {len(actual_sums)}")
print(f"  計画合計の件数: {len(plan_sums)}")
print(f"  実績合計のインデックス型: {type(actual_sums.index)}")
print(f"  計画合計のインデックス型: {type(plan_sums.index)}")

# 総件数の計算
total_days = len(actual_data)
total_count = total_days - lead_time_days + 1
expected_count = len(actual_sums)

print(f"\n総件数の計算:")
print(f"  稼働日数: {total_days}")
print(f"  計算式: {total_days} - {lead_time_days} + 1 = {total_count}")
print(f"  実際のrolling結果件数: {expected_count}")
print(f"  一致: {total_count == expected_count}")

if total_count == expected_count:
    print("  OK: 総件数が正しく計算されています")
else:
    print(f"  WARNING: 総件数が一致しません（差: {abs(total_count - expected_count)}）")

# ========================================
# 4️⃣ 差分計算（安全在庫②・③）が正しく動作しているか確認
# ========================================
print("\n" + "=" * 80)
print("4. 差分計算（安全在庫②・③）が正しく動作しているか確認")
print("=" * 80)

results = calculator.calculate_all_models()

# 安全在庫②の差分計算
delta2_data = results['model2_empirical_actual']['delta_data']
print(f"\n安全在庫②（実績−平均）:")
print(f"  差分データ件数: {len(delta2_data)}")
print(f"  差分データの平均: {np.mean(delta2_data):.2f}")
print(f"  差分データの標準偏差: {np.std(delta2_data):.2f}")

# 安全在庫③の差分計算
delta3_data = results['model3_empirical_plan']['delta_data']
print(f"\n安全在庫③（実績−計画）:")
print(f"  差分データ件数: {len(delta3_data)}")
print(f"  差分データの平均: {np.mean(delta3_data):.2f}")
print(f"  差分データの標準偏差: {np.std(delta3_data):.2f}")

# 共通インデックスの確認
common_idx = actual_sums.index.intersection(plan_sums.index)
print(f"\n共通インデックス:")
print(f"  件数: {len(common_idx)}")
print(f"  型: {type(common_idx)}")
print(f"  実績合計と計画合計のインデックスが一致: {len(common_idx) == len(actual_sums) == len(plan_sums)}")

if len(common_idx) == len(actual_sums) == len(plan_sums):
    print("  OK: 計画データと実績データが日付キーで正しく統合されています")
else:
    print(f"  WARNING: インデックスが一致していません")

# ========================================
# 5️⃣ データ型・インデックスの整合性確認
# ========================================
print("\n" + "=" * 80)
print("5. データ型・インデックスの整合性確認")
print("=" * 80)

print(f"\n計画データ:")
print(f"  インデックス型: {type(plan_data.index)}")
print(f"  値の型: {plan_data.dtype}")
print(f"  タイムゾーン: {plan_data.index.tz}")

print(f"\n実績データ:")
print(f"  インデックス型: {type(actual_data.index)}")
print(f"  値の型: {actual_data.dtype}")
print(f"  タイムゾーン: {actual_data.index.tz}")

print(f"\n稼働日インデックス:")
print(f"  型: {type(working_dates)}")
print(f"  タイムゾーン: {working_dates.tz if hasattr(working_dates, 'tz') else None}")

# 型の整合性確認
if isinstance(plan_data.index, pd.DatetimeIndex) and isinstance(actual_data.index, pd.DatetimeIndex):
    print("\nOK: 計画データと実績データのインデックスはDatetimeIndexです")
else:
    print("\nWARNING: インデックスがDatetimeIndexではありません")

if plan_data.index.tz == actual_data.index.tz:
    print("OK: タイムゾーンが一致しています")
else:
    print(f"WARNING: タイムゾーンが一致していません（計画: {plan_data.index.tz}, 実績: {actual_data.index.tz}）")

# ========================================
# 6️⃣ 回帰テスト
# ========================================
print("\n" + "=" * 80)
print("6. 回帰テスト")
print("=" * 80)

print(f"\n全商品コードで安全在庫計算を実行...")
error_count = 0
extreme_value_count = 0

for product_code in product_list[:5]:  # 最初の5商品でテスト
    try:
        plan_data_test = data_loader.get_daily_plan(product_code)
        actual_data_test = data_loader.get_daily_actual(product_code)
        
        calculator_test = SafetyStockCalculator(
            plan_data=plan_data_test,
            actual_data=actual_data_test,
            working_dates=working_dates,
            lead_time=lead_time,
            lead_time_type=lead_time_type,
            stockout_tolerance_pct=stockout_tolerance,
            std_calculation_method='population'
        )
        
        results_test = calculator_test.calculate_all_models()
        
        # 極端な値のチェック
        ss2 = results_test['model2_empirical_actual']['safety_stock']
        ss3 = results_test['model3_empirical_plan']['safety_stock']
        
        if ss2 is not None and (ss2 < 0 or ss2 > 1000000):
            extreme_value_count += 1
            print(f"  WARNING: {product_code}: 安全在庫②が極端な値 ({ss2:.2f})")
        
        if ss3 is not None and (ss3 < 0 or ss3 > 1000000):
            extreme_value_count += 1
            print(f"  WARNING: {product_code}: 安全在庫③が極端な値 ({ss3:.2f})")
        
    except Exception as e:
        error_count += 1
        print(f"  ERROR: {product_code}: エラー発生 - {str(e)}")

if error_count == 0:
    print(f"\nOK: エラーは発生しませんでした")
else:
    print(f"\nWARNING: {error_count}件のエラーが発生しました")

if extreme_value_count == 0:
    print(f"OK: 極端な値は検出されませんでした")
else:
    print(f"WARNING: {extreme_value_count}件の極端な値が検出されました")

print("\n" + "=" * 80)
print("検証完了")
print("=" * 80)

