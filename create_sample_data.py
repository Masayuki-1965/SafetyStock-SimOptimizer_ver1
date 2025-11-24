"""
サンプルデータファイル作成スクリプト
GitHubアップロード用のダミーデータを生成します
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# 乱数シードを固定
np.random.seed(42)

# データディレクトリの確認
os.makedirs('data', exist_ok=True)

# トライアル対象の3機種
products = ['TT-157092-AWAA', 'TT-157132-AWAA', 'KK-C14682-AWAA']

# 1. 日次実績データの作成（2024年6月の稼働日のみ）
dates = pd.date_range('2024-06-03', '2024-06-30', freq='B')  # 営業日のみ
daily_actual_df = pd.DataFrame(
    index=products,
    columns=[d.strftime('%Y%m%d') for d in dates]
)
for p in products:
    # ポアソン分布でランダムな実績値を生成
    daily_actual_df.loc[p] = np.random.poisson(lam=5, size=len(dates))

daily_actual_df.to_csv('data/日次実績データ.csv', encoding='utf-8-sig')
print('[OK] 日次実績データ作成完了')

# 2. 月次計画データの作成（2024年6月〜2025年5月）
months = ['202406', '202407', '202408', '202409', '202410', '202411', 
          '202412', '202501', '202502', '202503', '202504', '202505']
monthly_plan_df = pd.DataFrame(index=products, columns=months)
for p in products:
    # 100-200の範囲でランダムな月次計画値を生成
    monthly_plan_df.loc[p] = np.random.uniform(100, 200, len(months))

monthly_plan_df.to_csv('data/月次計画データ.csv', encoding='utf-8-sig')
print('[OK] 月次計画データ作成完了')

# 3. ABC区分データの作成
abc_df = pd.DataFrame({
    '商品コード': products,
    'ABC区分': ['A', 'A', 'B']
})
abc_df.to_csv('data/ABC区分データ.csv', index=False, encoding='utf-8-sig')
print('[OK] ABC区分データ作成完了')

# 4. 稼働日マスタの作成（2024年6月〜2025年5月）
all_dates = pd.date_range('2024-06-01', '2025-05-31', freq='D')
working_days_df = pd.DataFrame({
    '日付': all_dates.strftime('%Y%m%d'),
    '稼働日フラグ': [1 if d.weekday() < 5 else 0 for d in all_dates]
})
working_days_df.to_csv('data/稼働日マスタ.csv', index=False, encoding='utf-8-sig')
print('[OK] 稼働日マスタ作成完了')

# 5. 安全在庫データの作成
safety_stock_df = pd.DataFrame({
    '商品コード': products,
    '安全在庫': [50, 60, 40]
})
safety_stock_df.to_csv('data/安全在庫データ.csv', index=False, encoding='utf-8-sig')
print('[OK] 安全在庫データ作成完了')

print('\nすべてのサンプルデータファイルの作成が完了しました。')

