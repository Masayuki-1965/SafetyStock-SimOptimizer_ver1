"""
データ読み込み・統合・前処理モジュール
"""

import pandas as pd
import numpy as np
from typing import Tuple, List, Dict
import os
from modules.utils import get_base_path


class DataLoader:
    """データ読み込みと前処理を行うクラス"""
    
    def __init__(self, plan_file: str, actual_file: str):
        """
        初期化
        
        Args:
            plan_file: 計画データのファイルパス
            actual_file: 実績データのファイルパス
        """
        self.plan_file = plan_file
        self.actual_file = actual_file
        self.plan_df = None
        self.actual_df = None
        self.merged_df = None
        self.working_dates = None
        self.safety_stock_monthly_df = None
        self.working_days_master_df = None
        
    def load_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        計画と実績のCSVファイルを読み込む
        
        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (計画データ, 実績データ)
        """
        base_path = get_base_path()
        
        # 計画データ読み込み（エンコーディングを自動判定）
        plan_path = os.path.join(base_path, self.plan_file)
        plan_source = None
        if not os.path.exists(plan_path):
            # フォールバック: 月次計画データが存在する場合は日次計画へ変換
            fallback_path = os.path.join(base_path, "data/月次計画データ.csv")
            if os.path.exists(fallback_path):
                plan_path = fallback_path
                plan_source = "monthly"
            else:
                raise FileNotFoundError(f"計画データファイルが見つかりません: {self.plan_file}")
        else:
            plan_source = "daily"
        try:
            plan_df_raw = pd.read_csv(plan_path, index_col=0, encoding='utf-8-sig')
        except UnicodeDecodeError:
            plan_df_raw = pd.read_csv(plan_path, index_col=0, encoding='shift_jis')
        
        # 列形式から日次/月次を判定し、必要に応じて日次へ変換
        use_daily_direct = False
        if plan_source == "daily":
            try:
                pd.to_datetime(plan_df_raw.columns, format='%Y%m%d')
                use_daily_direct = True
            except (ValueError, TypeError):
                use_daily_direct = False
        if plan_source == "monthly":
            use_daily_direct = False
        
        if use_daily_direct:
            self.plan_df = plan_df_raw.copy()
            self.plan_df.columns = pd.to_datetime(self.plan_df.columns, format='%Y%m%d')
            self.working_dates = self.plan_df.columns
        else:
            # 月次データとして処理し日次へ変換
            self.load_monthly_plan_from_dataframe(plan_df_raw)
            self.convert_monthly_to_daily_plan(self.monthly_plan_df)
        
        # 実績データ読み込み（エンコーディングを自動判定）
        actual_path = os.path.join(base_path, self.actual_file)
        try:
            self.actual_df = pd.read_csv(actual_path, index_col=0, encoding='utf-8-sig')
        except UnicodeDecodeError:
            self.actual_df = pd.read_csv(actual_path, index_col=0, encoding='shift_jis')
        
        # カラム名を日付型に変換
        self.plan_df.columns = pd.to_datetime(self.plan_df.columns, format='%Y%m%d')
        self.actual_df.columns = pd.to_datetime(self.actual_df.columns, format='%Y%m%d')
        
        # 稼働日のインデックスを保存
        self.working_dates = self.plan_df.columns
        
        return self.plan_df, self.actual_df
    
    def merge_data(self) -> pd.DataFrame:
        """
        計画と実績データを統合
        
        Returns:
            pd.DataFrame: 統合されたデータ
        """
        if self.plan_df is None or self.actual_df is None:
            self.load_data()
        
        # 長形式に変換
        plan_long = self.plan_df.T.reset_index()
        plan_long = plan_long.rename(columns={'index': 'date'})
        plan_long = plan_long.melt(id_vars=['date'], var_name='product_code', value_name='plan')
        
        actual_long = self.actual_df.T.reset_index()
        actual_long = actual_long.rename(columns={'index': 'date'})
        actual_long = actual_long.melt(id_vars=['date'], var_name='product_code', value_name='actual')
        
        # マージ
        self.merged_df = pd.merge(
            plan_long, 
            actual_long, 
            on=['date', 'product_code'],
            how='inner'
        )
        
        # 差分を計算（計画 - 実績）
        self.merged_df['difference'] = self.merged_df['plan'] - self.merged_df['actual']
        
        return self.merged_df
    
    def get_product_data(self, product_code: str) -> pd.DataFrame:
        """
        特定商品のデータを取得
        
        Args:
            product_code: 商品コード
        
        Returns:
            pd.DataFrame: 商品データ
        """
        if self.merged_df is None:
            self.merge_data()
        
        product_data = self.merged_df[
            self.merged_df['product_code'] == product_code
        ].copy()
        
        product_data = product_data.sort_values('date').reset_index(drop=True)
        
        return product_data
    
    def get_product_list(self) -> List[str]:
        """
        利用可能な商品コードのリストを取得
        
        Returns:
            List[str]: 商品コードのリスト
        """
        if self.plan_df is None:
            self.load_data()
        
        return list(self.plan_df.index)
    
    def get_working_dates(self) -> pd.DatetimeIndex:
        """
        稼働日のインデックスを取得
        
        Returns:
            pd.DatetimeIndex: 稼働日のインデックス
        """
        if self.working_dates is None:
            self.load_data()
        
        return self.working_dates
    
    def get_date_range(self) -> Tuple[pd.Timestamp, pd.Timestamp]:
        """
        データの期間を取得
        
        Returns:
            Tuple[pd.Timestamp, pd.Timestamp]: (開始日, 終了日)
        """
        if self.working_dates is None:
            self.load_data()
        
        return self.working_dates[0], self.working_dates[-1]
    
    def get_daily_actual(self, product_code: str) -> pd.Series:
        """
        特定商品の日次実績データを取得
        
        Args:
            product_code: 商品コード
        
        Returns:
            pd.Series: 日次実績データ（インデックス=日付）
        """
        if self.actual_df is None:
            self.load_data()
        
        return self.actual_df.loc[product_code]
    
    def get_daily_plan(self, product_code: str) -> pd.Series:
        """
        特定商品の日次計画データを取得
        
        Args:
            product_code: 商品コード
        
        Returns:
            pd.Series: 日次計画データ（インデックス=日付）
        """
        if self.plan_df is None:
            self.load_data()
        
        return self.plan_df.loc[product_code]
    
    def validate_product_code(self, product_code: str) -> bool:
        """
        商品コードが存在するか検証
        
        Args:
            product_code: 商品コード
        
        Returns:
            bool: 存在すればTrue
        """
        product_list = self.get_product_list()
        return product_code in product_list
    
    def load_safety_stock_monthly(self) -> pd.DataFrame:
        """
        安全在庫月数CSVファイルを読み込む
        
        Returns:
            pd.DataFrame: 安全在庫月数データ
        """
        base_path = get_base_path()
        file_path = os.path.join(base_path, "data/安全在庫データ.csv")
        
        try:
            # CSVファイルを読み込み（エンコーディングを指定）
            # まずutf-8-sigで試行、失敗した場合はshift_jisで試行
            try:
                self.safety_stock_monthly_df = pd.read_csv(file_path, encoding='utf-8-sig')
            except UnicodeDecodeError:
                self.safety_stock_monthly_df = pd.read_csv(file_path, encoding='shift_jis')
            
            # カラム名を設定
            self.safety_stock_monthly_df.columns = ['商品コード', '安全在庫月数']
            
            return self.safety_stock_monthly_df
        except FileNotFoundError:
            # ファイルが存在しない場合は空のDataFrameを返す
            self.safety_stock_monthly_df = pd.DataFrame(columns=['商品コード', '安全在庫月数'])
            return self.safety_stock_monthly_df
        except Exception as e:
            # その他のエラーの場合も空のDataFrameを返す
            print(f"安全在庫月数CSVの読み込みエラー: {e}")
            self.safety_stock_monthly_df = pd.DataFrame(columns=['商品コード', '安全在庫月数'])
            return self.safety_stock_monthly_df
    
    def load_working_days_master(self) -> pd.DataFrame:
        """
        稼働日マスタCSVファイルを読み込む
        
        Returns:
            pd.DataFrame: 稼働日マスタデータ
        """
        base_path = get_base_path()
        file_path = os.path.join(base_path, "data/稼働日マスタ.csv")
        
        try:
            # CSVファイルを読み込み（エンコーディングを指定）
            # まずutf-8-sigで試行、失敗した場合はshift_jisで試行
            try:
                self.working_days_master_df = pd.read_csv(file_path, encoding='utf-8-sig')
            except UnicodeDecodeError:
                self.working_days_master_df = pd.read_csv(file_path, encoding='shift_jis')
            
            # カラム名を設定
            self.working_days_master_df.columns = ['日時', '曜日', '年月', '稼働日区分']
            
            # 日時を日付型に変換
            self.working_days_master_df['日時'] = pd.to_datetime(self.working_days_master_df['日時'], format='%Y%m%d')
            
            return self.working_days_master_df
        except FileNotFoundError:
            # ファイルが存在しない場合は空のDataFrameを返す
            self.working_days_master_df = pd.DataFrame(columns=['日時', '曜日', '年月', '稼働日区分'])
            return self.working_days_master_df
        except Exception as e:
            # その他のエラーの場合も空のDataFrameを返す
            print(f"稼働日マスタCSVの読み込みエラー: {e}")
            self.working_days_master_df = pd.DataFrame(columns=['日時', '曜日', '年月', '稼働日区分'])
            return self.working_days_master_df
    
    def get_common_date_range(self) -> Tuple[pd.Timestamp, pd.Timestamp]:
        """
        計画データと実績データの共通期間を取得
        
        Returns:
            Tuple[pd.Timestamp, pd.Timestamp]: (開始日, 終了日)
        """
        if self.plan_df is None or self.actual_df is None:
            self.load_data()
        
        # 計画データの期間
        plan_start = self.plan_df.columns[0]
        plan_end = self.plan_df.columns[-1]
        
        # 実績データの期間
        actual_start = self.actual_df.columns[0]
        actual_end = self.actual_df.columns[-1]
        
        # 共通期間を計算
        common_start = max(plan_start, actual_start)
        common_end = min(plan_end, actual_end)
        
        return common_start, common_end
    
    def calculate_monthly_working_days(self) -> float:
        """
        稼働日マスタから月平均稼働日数を算出
        
        Returns:
            float: 月平均稼働日数
        """
        if self.working_days_master_df is None:
            self.load_working_days_master()
        
        # 稼働日マスタが空の場合はデフォルト値（21日）を返す
        if self.working_days_master_df.empty:
            return 21.0
        
        # 共通期間を取得
        common_start, common_end = self.get_common_date_range()
        
        # 共通期間内の稼働日マスタを抽出
        mask = (self.working_days_master_df['日時'] >= common_start) & \
               (self.working_days_master_df['日時'] <= common_end)
        period_data = self.working_days_master_df[mask].copy()
        
        # 期間データが空の場合はデフォルト値を返す
        if period_data.empty:
            return 21.0
        
        # 年月ごとの稼働日数を計算
        monthly_working_days = period_data[period_data['稼働日区分'] == 1].groupby('年月').size()
        
        # 稼働日データが空の場合はデフォルト値を返す
        if monthly_working_days.empty:
            return 21.0
        
        # 完全な月を判定
        # 各月の開始日と終了日を計算
        complete_months = []
        for year_month in monthly_working_days.index:
            year = int(str(year_month)[:4])
            month = int(str(year_month)[4:])
            
            # 月の開始日と終了日
            month_start = pd.Timestamp(year, month, 1)
            if month == 12:
                month_end = pd.Timestamp(year + 1, 1, 1) - pd.Timedelta(days=1)
            else:
                month_end = pd.Timestamp(year, month + 1, 1) - pd.Timedelta(days=1)
            
            # 完全な月かどうかを判定
            if month_start >= common_start and month_end <= common_end:
                complete_months.append(year_month)
        
        # 完全な月が1つ以上ある場合
        if len(complete_months) > 0:
            avg_working_days = monthly_working_days[complete_months].mean()
        else:
            # 完全な月がない場合は全期間の平均を使用
            avg_working_days = monthly_working_days.mean()
        
        # 計算結果が無効な場合はデフォルト値を返す
        if pd.isna(avg_working_days) or avg_working_days <= 0:
            return 21.0
        
        return round(avg_working_days, 1)
    
    def get_safety_stock_monthly(self, product_code: str) -> float:
        """
        特定商品の安全在庫月数を取得
        
        Args:
            product_code: 商品コード
        
        Returns:
            float: 安全在庫月数（該当しない場合は0.0）
        """
        if self.safety_stock_monthly_df is None:
            self.load_safety_stock_monthly()
        
        # 商品コードで検索
        matching_rows = self.safety_stock_monthly_df[self.safety_stock_monthly_df['商品コード'] == product_code]
        
        if len(matching_rows) > 0:
            return float(matching_rows.iloc[0]['安全在庫月数'])
        else:
            return 0.0
    
    def load_monthly_plan_from_dataframe(self, monthly_plan_df: pd.DataFrame) -> pd.DataFrame:
        """
        月次計画データをDataFrameから読み込む
        
        Args:
            monthly_plan_df: 月次計画データ（行=商品コード、列=YYYYMM、セル=数量）
        
        Returns:
            pd.DataFrame: 月次計画データ
        """
        self.monthly_plan_df = monthly_plan_df.copy()
        # カラム名をYYYYMMからパース
        # カラム名が既に文字列の場合はそのまま使用、数値の場合は文字列に変換
        if self.monthly_plan_df.columns.dtype == 'object':
            # カラム名をYYYYMM形式の文字列として扱う
            pass
        else:
            # カラム名を文字列に変換（YYYYMM形式）
            self.monthly_plan_df.columns = self.monthly_plan_df.columns.astype(str)
        
        return self.monthly_plan_df
    
    def convert_monthly_to_daily_plan(self, monthly_plan_df: pd.DataFrame) -> pd.DataFrame:
        """
        月次計画データを日次計画データに変換（稼働日マスタを使用）
        
        Args:
            monthly_plan_df: 月次計画データ（行=商品コード、列=YYYYMM、セル=数量）
        
        Returns:
            pd.DataFrame: 日次計画データ（行=商品コード、列=YYYYMMDD、セル=数量）
        
        Raises:
            ValueError: 稼働日マスタが不足している場合
        """
        # 稼働日マスタを読み込む
        if self.working_days_master_df is None:
            self.load_working_days_master()
        
        if self.working_days_master_df.empty:
            raise ValueError("営業稼働日データが不足しています。稼働日マスタを読み込めませんでした。")
        
        # 月次計画データの期間を取得
        monthly_columns = monthly_plan_df.columns.astype(str)
        
        # 期間の開始月と終了月を取得
        try:
            start_year_month = int(monthly_columns[0])
            end_year_month = int(monthly_columns[-1])
        except (ValueError, IndexError):
            raise ValueError(f"月次計画データの列名が不正です。YYYYMM形式である必要があります。")
        
        # 日次計画データの作成用データ構造
        # {日付文字列: {商品コード: 日割り値}}
        daily_plan_dict = {}
        
        # 商品コードを取得
        product_codes = monthly_plan_df.index.tolist()
        
        for year_month_str in monthly_columns:
            try:
                year_month = int(year_month_str)
                
                # 該当月の稼働日を抽出（稼働日区分==1のみ）
                month_mask = (
                    (self.working_days_master_df['年月'] == year_month) &
                    (self.working_days_master_df['稼働日区分'] == 1)
                )
                month_working_days = self.working_days_master_df[month_mask]['日時'].tolist()
                
                if len(month_working_days) == 0:
                    raise ValueError(
                        f"営業稼働日データが不足して日割りできません。"
                        f"年月 {year_month_str} の稼働日データが見つかりません。稼働日データを追加してください。"
                    )
                
                # 各商品について、月次計画値を日割り
                for product_code in product_codes:
                    monthly_value = monthly_plan_df.loc[product_code, year_month_str]
                    daily_value_per_working_day = monthly_value / len(month_working_days)
                    
                    # 各稼働日に値を設定
                    for working_date in month_working_days:
                        date_str = working_date.strftime('%Y%m%d')
                        if date_str not in daily_plan_dict:
                            daily_plan_dict[date_str] = {}
                        daily_plan_dict[date_str][product_code] = daily_value_per_working_day
                    
            except Exception as e:
                raise ValueError(f"年月 {year_month_str} の処理中にエラーが発生しました: {str(e)}")
        
        # 稼働日が1つも見つからない場合はエラー
        if not daily_plan_dict:
            raise ValueError("営業稼働日データが不足して日割りできません。")
        
        # 日次計画データのDataFrameを作成
        # 全ての日付をソート（YYYYMMDD形式でソート）
        all_dates = sorted(daily_plan_dict.keys())
        
        # 各日付について、各商品の値を取得してDataFrameを作成
        daily_plan_data = {}
        for date_str in all_dates:
            daily_values = [daily_plan_dict[date_str].get(product_code, 0.0) for product_code in product_codes]
            daily_plan_data[date_str] = daily_values
        
        # DataFrameを作成
        daily_plan_df = pd.DataFrame(daily_plan_data, index=product_codes)
        
        # カラム名を日付型に変換
        daily_plan_df.columns = pd.to_datetime(daily_plan_df.columns, format='%Y%m%d')
        
        # 稼働日のインデックスを保存
        self.working_dates = daily_plan_df.columns
        
        # 計画データとして設定
        self.plan_df = daily_plan_df
        
        return daily_plan_df
    
    def load_actual_from_dataframe(self, actual_df: pd.DataFrame) -> pd.DataFrame:
        """
        日次実績データをDataFrameから読み込む
        
        Args:
            actual_df: 日次実績データ（行=商品コード、列=YYYYMMDD、セル=数量）
        
        Returns:
            pd.DataFrame: 日次実績データ
        """
        self.actual_df = actual_df.copy()
        
        # カラム名を日付型に変換
        if isinstance(self.actual_df.columns[0], str):
            # YYYYMMDD形式の文字列の場合
            self.actual_df.columns = pd.to_datetime(self.actual_df.columns, format='%Y%m%d')
        else:
            # 既に日付型の場合
            self.actual_df.columns = pd.to_datetime(self.actual_df.columns)
        
        return self.actual_df
    
    def load_safety_stock_from_dataframe(self, safety_stock_df: pd.DataFrame) -> pd.DataFrame:
        """
        安全在庫月数データをDataFrameから読み込む
        
        Args:
            safety_stock_df: 安全在庫月数データ（A列=商品コード、B列=安全在庫月数）
        
        Returns:
            pd.DataFrame: 安全在庫月数データ
        """
        self.safety_stock_monthly_df = safety_stock_df.copy()
        
        # カラム名を設定（既に設定されている場合はそのまま）
        if len(self.safety_stock_monthly_df.columns) >= 2:
            self.safety_stock_monthly_df.columns = ['商品コード', '安全在庫月数']
        
        return self.safety_stock_monthly_df


