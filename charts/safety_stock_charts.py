"""
安全在庫関連のPlotlyグラフ生成モジュール
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, Optional, Tuple
from modules.safety_stock_models import SafetyStockCalculator
from utils.common import format_abc_category_for_display


def create_time_series_chart(product_code: str, calculator: SafetyStockCalculator) -> go.Figure:
    """
    計画と実績の時系列推移グラフを生成
    
    Args:
        product_code: 商品コード
        calculator: SafetyStockCalculatorインスタンス
    
    Returns:
        Plotly Figureオブジェクト
    """
    # データ取得
    plan_data = calculator.plan_data
    actual_data = calculator.actual_data
    working_dates = calculator.working_dates
    
    # 日付とデータを整理
    dates = pd.to_datetime(working_dates)
    plan_values = plan_data.values
    actual_values = actual_data.values
    
    # Plotlyグラフを作成（共通のY軸を使用）
    fig = go.Figure()
    
    # 日次計画（共通Y軸）- 薄めの緑系（LT間差分の棒グラフと同系統、やや太線）
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=plan_values,
            name="日次計画",
            mode='lines+markers',
            marker=dict(size=4),
            line=dict(color='rgb(100, 200, 150)', width=2.5)  # 薄めの緑系（LT間差分と同系統、やや太線）
        )
    )
    
    # 日次実績（共通Y軸）- 薄めの黒系（やや太線）
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=actual_values,
            name="日次実績",
            mode='lines+markers',
            marker=dict(size=4),
            line=dict(color='#808080', width=2.0)  # 薄めの黒系（やや太線）
        )
    )
    
    # レイアウト設定
    fig.update_layout(
        title=f"{product_code} - 計画と実績の時系列推移",
        xaxis=dict(
            title="日付",
            type="date",
            tickformat="%Y-%m",
            rangeslider=dict(
                visible=True,
                thickness=0.05,
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0
            )
        ),
        yaxis=dict(
            title="数量",
            side="left",
            showgrid=True
        ),
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        height=500,
        margin=dict(l=80, r=80, t=80, b=100)
    )
    
    return fig


def create_time_series_delta_bar_chart(product_code: str, results: Optional[dict], calculator: SafetyStockCalculator, show_safety_stock_lines: bool = True) -> go.Figure:
    """
    LT間差分の時系列棒グラフを生成（上下分割表示）
    
    Args:
        product_code: 商品コード
        results: 安全在庫計算結果の辞書（Noneの場合は安全在庫ラインを表示しない）
        calculator: SafetyStockCalculatorインスタンス
        show_safety_stock_lines: 安全在庫ラインを表示するかどうか（デフォルト: True）
    
    Returns:
        Plotly Figureオブジェクト
    """
    # リードタイム日数を取得（resultsがNoneの場合はcalculatorから取得）
    if results is not None:
        lead_time_days = int(np.ceil(results['common_params']['lead_time_days']))
    else:
        # calculatorからリードタイム日数を計算
        lead_time_working_days = calculator._get_lead_time_in_working_days()
        lead_time_days = int(np.ceil(lead_time_working_days))
    
    # データ取得
    plan_data = calculator.plan_data
    actual_data = calculator.actual_data
    
    # モデル②：実績−平均の差分を計算（日付付き）
    actual_sums = actual_data.rolling(window=lead_time_days).sum().dropna()
    delta2 = actual_sums - actual_sums.mean()
    dates_model2 = delta2.index
    
    # モデル③：実績−計画の差分を計算（日付付き）
    actual_sums_model3 = actual_data.rolling(window=lead_time_days).sum().dropna()
    plan_sums_model3 = plan_data.rolling(window=lead_time_days).sum().dropna()
    common_idx = actual_sums_model3.index.intersection(plan_sums_model3.index)
    delta3 = actual_sums_model3.loc[common_idx] - plan_sums_model3.loc[common_idx]
    dates_model3 = delta3.index
    
    # 横軸・縦軸のレンジを統一するために両方のデータの範囲を計算
    all_delta_values = list(delta2.values) + list(delta3.values)
    min_val = min(all_delta_values)
    max_val = max(all_delta_values)
    range_margin = (max_val - min_val) * 0.15  # 15%のマージンを追加して変動幅を明確に表示
    y_range = [min_val - range_margin, max_val + range_margin]
    
    # 横軸の範囲を統一（両方の日付範囲を考慮）
    all_dates = list(dates_model2) + list(dates_model3)
    x_min = min(all_dates)
    x_max = max(all_dates)
    
    # サブプロット作成（2行1列：上段と下段）
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "リードタイム間差分（実績 − 平均）※実績バラつき",
            "リードタイム間差分（実績 − 計画）※計画誤差"
        ],
        vertical_spacing=0.02
    )
    
    # 上段：LT間差分（実績−平均）の棒グラフ - 薄めの黒系
    fig.add_trace(
        go.Bar(
            x=dates_model2,
            y=delta2.values,
            name='実績バラつき',
            marker_color='rgba(128, 128, 128, 0.8)',  # 薄めの黒系
            hovertemplate="差分=%{y}<extra></extra>",
            showlegend=True,
            legendgroup='bars'
        ),
        row=1, col=1
    )
    
    # 下段：LT間差分（実績−計画）の棒グラフ - 薄めの緑系（現状維持）
    fig.add_trace(
        go.Bar(
            x=dates_model3,
            y=delta3.values,
            name='計画誤差',
            marker_color='rgba(100, 200, 150, 0.8)',  # 薄めの緑系（現状維持）
            hovertemplate="差分=%{y}<extra></extra>",
            showlegend=True,
            legendgroup='bars'
        ),
        row=2, col=1
    )
    
    # 各サブプロットにゼロラインを追加
    fig.add_hline(
        y=0,
        line_dash="solid",
        line_color="gray",
        line_width=1,
        opacity=0.5,
        row=1, col=1
    )
    fig.add_hline(
        y=0,
        line_dash="solid",
        line_color="gray",
        line_width=1,
        opacity=0.5,
        row=2, col=1
    )
    
    # 安全在庫ラインを表示する場合のみ処理
    if show_safety_stock_lines and results is not None:
        # リードタイム日数を取得
        lead_time_days = int(np.ceil(results['common_params']['lead_time_days']))
        
        # 安全在庫値を取得（resultsから直接取得）
        safety_stock_1 = results['model1_theoretical']['safety_stock']
        is_model1_undefined = results['model1_theoretical'].get('is_undefined', False) or safety_stock_1 is None
        safety_stock_2 = results['model2_empirical_actual']['safety_stock']
        safety_stock_3 = results['model3_empirical_plan']['safety_stock']
        stockout_tolerance_pct = results['common_params']['stockout_tolerance_pct']
        is_p_zero = stockout_tolerance_pct <= 0
        
        # 上段：安全在庫①（赤色破線）と安全在庫②（濃い黒系破線）を追加
        # p=0%の時は①を非表示
        if safety_stock_1 is not None and not is_model1_undefined and not is_p_zero:
            fig.add_hline(
                y=safety_stock_1,
                line_dash="dash",
                line_color="red",  # 赤色
                line_width=2,
                annotation_text="安全在庫①",
                annotation_position="top right",
                row=1, col=1
            )
        if safety_stock_2 is not None:
            fig.add_hline(
                y=safety_stock_2,
                line_dash="dash",
                line_color="#333333",  # 濃い黒系
                line_width=2,
                annotation_text="安全在庫②",
                annotation_position="top right",
                row=1, col=1
            )
        
        # 下段：安全在庫③（濃い緑系破線）を追加
        if safety_stock_3 is not None:
            fig.add_hline(
                y=safety_stock_3,
                line_dash="dash",
                line_color="#228B22",  # 濃い緑系
                line_width=2,
                annotation_text="安全在庫③",
                annotation_position="top right",
                row=2, col=1
            )
        
        # 凡例用のダミートレースを追加（破線の凡例を表示するため）
        # 安全在庫①（赤色破線）- p=0%の時はdisabled（グレーアウト）
        if is_model1_undefined or is_p_zero:
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode='lines',
                    name='安全在庫①',
                    line=dict(color='gray', dash='dash', width=2),
                    showlegend=True,
                    legendgroup='safety_stock',
                    opacity=0.5,
                    hovertemplate='p=0%では理論値は計算不可（p=0→Z=∞）<extra></extra>'
                )
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode='lines',
                    name='安全在庫①',
                    line=dict(color='red', dash='dash', width=2),  # 赤色
                    showlegend=True,
                    legendgroup='safety_stock'
                )
            )
        # 安全在庫②（濃い黒系破線）
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode='lines',
                name='安全在庫②',
                line=dict(color='#333333', dash='dash', width=2),  # 濃い黒系
                showlegend=True,
                legendgroup='safety_stock'
            )
        )
        # 安全在庫③（濃い緑系破線）
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode='lines',
                name='安全在庫③',
                line=dict(color='#228B22', dash='dash', width=2),  # 濃い緑系
                showlegend=True,
                legendgroup='safety_stock'
            )
        )
    
    # レイアウト設定
    fig.update_layout(
        title=f"{product_code} - リードタイム間差分の時系列推移",
        height=900,
        hovermode='x unified',
        margin=dict(l=60, r=60, t=120, b=40),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.06,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(size=12)
        ),
        legend_traceorder="normal"
    )
    
    # 横軸を統一（両方のサブプロットで同じ範囲）
    # 上段のX軸：目盛りラベルを非表示にしてガチャガチャ感を解消、rangesliderは非表示
    fig.update_xaxes(
        showticklabels=False,
        matches="x",
        rangeslider=dict(visible=False),
        row=1, col=1
    )
    # 下段のX軸：rangesliderを設定（単一レンジスライダーで連動表示・目立たない設定）
    fig.update_xaxes(
        title="日付",
        type="date",
        tickformat="%Y-%m",
        range=[x_min, x_max],
        rangeslider=dict(
            visible=True,
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            thickness=0.05
        ),
        row=2, col=1
    )
    # X軸の連動を確実にするため、xaxis2.matches="x"を明示的に設定
    fig.layout.xaxis2.matches = "x"
    
    # 上下のグラフの隙間を極力なくすため、yaxis.domainを調整
    if "yaxis" in fig.layout and "yaxis2" in fig.layout:
        fig.layout.yaxis.domain = [0.52, 1.00]  # 上段
        fig.layout.yaxis2.domain = [0.00, 0.48]  # 下段（rangesliderのスペースを確保）
    
    # 縦軸を統一（両方のサブプロットで同じ範囲）
    fig.update_yaxes(
        title="差分",
        zeroline=True,
        zerolinecolor="gray",
        zerolinewidth=1,
        range=y_range,
        row=1, col=1
    )
    fig.update_yaxes(
        title="差分",
        zeroline=True,
        zerolinecolor="gray",
        zerolinewidth=1,
        range=y_range,
        row=2, col=1
    )
    
    # 細かい見た目調整
    fig.update_layout(bargap=0.05)
    
    return fig


def create_histogram_with_unified_range(product_code: str, results: dict, calculator: SafetyStockCalculator) -> go.Figure:
    """
    横軸・縦軸レンジを統一したヒストグラムを生成
    
    Args:
        product_code: 商品コード
        results: 安全在庫計算結果の辞書
        calculator: SafetyStockCalculatorインスタンス
    
    Returns:
        Plotly Figureオブジェクト
    """
    # ヒストグラムデータ取得
    hist_data = calculator.get_histogram_data()
    
    # 横軸レンジを統一（両方のデータの範囲を考慮）
    all_delta_values = hist_data['model2_delta'] + hist_data['model3_delta']
    min_val = min(all_delta_values)
    max_val = max(all_delta_values)
    range_margin = (max_val - min_val) * 0.1  # 10%のマージンを追加
    x_range = [min_val - range_margin, max_val + range_margin]
    
    # 統一したビン数を設定（両方のヒストグラムで同じビン数を使用）
    nbins = 30
    
    # 共通のビン境界を明示的に計算
    bin_edges = np.linspace(min_val - range_margin, max_val + range_margin, nbins + 1)
    
    # 縦軸レンジを統一（両方のヒストグラムの最大頻度を考慮）
    # モデル②の頻度分布を計算（共通のビン境界を使用）
    model2_counts, model2_bins = np.histogram(hist_data['model2_delta'], bins=bin_edges)
    model2_max_freq = np.max(model2_counts)
    
    # モデル③の頻度分布を計算（共通のビン境界を使用）
    model3_counts, model3_bins = np.histogram(hist_data['model3_delta'], bins=bin_edges)
    model3_max_freq = np.max(model3_counts)
    
    # 両方の最大頻度を取得し、統一した縦軸レンジを設定
    max_freq = max(model2_max_freq, model3_max_freq)
    y_range = [0, max_freq * 1.1]  # 10%のマージンを追加
    
    # サブプロット作成
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[
            "リードタイム間差分（実績 − 平均）※実績バラつき",
            "リードタイム間差分（実績 − 計画）※計画誤差"
        ],
        specs=[[{"secondary_y": False}, {"secondary_y": False}]],
        vertical_spacing=0.15
    )
    
    # モデル②のヒストグラム（統一したビン境界を使用）- 薄めの黒系
    fig.add_trace(
        go.Histogram(
            x=hist_data['model2_delta'],
            name='実績バラつき',
            opacity=0.8,
            xbins=dict(start=bin_edges[0], end=bin_edges[-1], size=bin_edges[1] - bin_edges[0]),
            marker_color='rgba(128, 128, 128, 0.8)'  # 薄めの黒系
        ),
        row=1, col=1
    )
    
    # 安全在庫①（理論値）をモデル②に重ね表示（赤色破線）
    # p=0%の時は①を非表示
    is_p_zero = hist_data.get('is_p_zero', False)
    if hist_data['model1_theoretical_line'] is not None and not is_p_zero:
        fig.add_vline(
            x=hist_data['model1_theoretical_line'],
            line_dash="dash",
            line_color="red",  # 赤色
            annotation_text="",  # 安全在庫①は線だけ表示（ラベルなし）
            annotation_position="top right",
            row=1, col=1,
            line_width=2
        )
    
    # 安全在庫②（実績−平均）をモデル②に表示（濃い黒系破線）
    fig.add_vline(
        x=hist_data['model2_p95_line'],
        line_dash="dash",
        line_color="#333333",  # 濃い黒系
        annotation_text="安全在庫②",  # ラベルを表示
        annotation_position="top right",
        row=1, col=1,
        line_width=2
    )
    
    # モデル③のヒストグラム（統一したビン境界を使用）- 薄めの緑系（現状維持）
    fig.add_trace(
        go.Histogram(
            x=hist_data['model3_delta'],
            name='計画誤差',
            opacity=0.8,
            xbins=dict(start=bin_edges[0], end=bin_edges[-1], size=bin_edges[1] - bin_edges[0]),
            marker_color='rgba(100, 200, 150, 0.8)'  # 薄めの緑系（現状維持）
        ),
        row=1, col=2
    )
    
    # 安全在庫③（実績−計画）をモデル③に表示（濃い緑系破線）
    fig.add_vline(
        x=hist_data['model3_p95_line'],
        line_dash="dash",
        line_color="#228B22",  # 濃い緑系
        annotation_text="安全在庫③",  # ラベルを表示
        annotation_position="top right",
        row=1, col=2,
        line_width=2
    )
    
    # 凡例用のダミートレースを追加（破線の凡例を表示するため）
    # 安全在庫①（緑色破線）- p=0%の時はdisabled（グレーアウト）
    if is_p_zero:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode='lines',
                name='安全在庫①',
                line=dict(color='gray', dash='dash', width=2),
                showlegend=True,
                legendgroup='safety_stock',
                opacity=0.5,
                hovertemplate='p=0%では理論値は計算不可（p=0→Z=∞）<extra></extra>'
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode='lines',
                name='安全在庫①',
                line=dict(color='red', dash='dash', width=2),  # 赤色
                showlegend=True,
                legendgroup='safety_stock'
            )
        )
    # 安全在庫②（濃い黒系破線）
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode='lines',
            name='安全在庫②',
            line=dict(color='#333333', dash='dash', width=2),  # 濃い黒系
            showlegend=True,
            legendgroup='safety_stock'
        )
    )
    # 安全在庫③（濃い緑系破線）
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode='lines',
            name='安全在庫③',
            line=dict(color='#228B22', dash='dash', width=2),  # 濃い緑系
            showlegend=True,
            legendgroup='safety_stock'
        )
    )
    
    # レイアウト設定
    fig.update_layout(
        height=500,
        showlegend=True,
        title_text=f"{product_code} - リードタイム間差分の分布",
        margin=dict(t=170, b=100, r=80),  # 右側の余白を追加して「安全在庫③」の切れを防止
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.12,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(size=12)
        ),
        legend_traceorder="normal"
    )
    
    # 横軸・縦軸レンジを統一
    fig.update_xaxes(range=x_range, title_text="差分", row=1, col=1)
    fig.update_xaxes(range=x_range, title_text="差分", row=1, col=2)
    fig.update_yaxes(range=y_range, title_text="件数", row=1, col=1)
    fig.update_yaxes(range=y_range, title_text="件数", row=1, col=2)
    
    return fig


def create_order_volume_comparison_chart_before(results_df: pd.DataFrame, safety_stock_type: str = "ss3", y1_max: Optional[float] = None, y2_max: Optional[float] = None) -> go.Figure:
    """
    受注量別 安全在庫比較グラフを生成（異常値処理前のみ）
    
    Args:
        results_df: 異常値処理前の全機種の安全在庫算出結果DataFrame
        safety_stock_type: 安全在庫タイプ ("current", "ss1", "ss2", "ss3")
        y1_max: 左Y軸（数量）の最大値（Noneの場合は自動計算）
        y2_max: 右Y軸（日数）の最大値（Noneの場合は自動計算）
    
    Returns:
        Plotly Figureオブジェクト
    """
    # 安全在庫タイプに応じた列名を決定
    type_mapping = {
        "current": ("現行設定_数量", "現行設定_日数", "現行設定"),
        "ss1": ("安全在庫①_数量", "安全在庫①_日数", "安全在庫①"),
        "ss2": ("安全在庫②_数量", "安全在庫②_日数", "安全在庫②"),
        "ss3": ("安全在庫③_数量", "安全在庫③_日数", "安全在庫③")
    }
    
    quantity_col, days_col, type_name = type_mapping.get(safety_stock_type, type_mapping["ss3"])
    
    # 選択された安全在庫タイプのデータを取得
    # 日当たり実績が0または欠損の機種は除外
    valid_mask = (
        (results_df['日当たり実績'].notna()) &
        (results_df['日当たり実績'] > 0) &
        (results_df[quantity_col].notna()) &
        (results_df[days_col].notna())
    )
    
    chart_df = results_df[valid_mask].copy()
    
    if len(chart_df) == 0:
        # 空のグラフを返す
        fig = go.Figure()
        fig.update_layout(title=f'受注量別 {type_name} 比較グラフ（異常値処理前）')
        return fig
    
    # 受注量（日当たり実績）で降順ソート
    chart_df = chart_df.sort_values('日当たり実績', ascending=False).reset_index(drop=True)
    
    # 横軸：インデックス順（受注量降順）
    x_values = chart_df.index.tolist()
    
    # 左縦軸：選択された安全在庫タイプの数量（棒グラフ）
    ss_quantity = chart_df[quantity_col].values
    
    # 右縦軸：選択された安全在庫タイプの日数（折れ線グラフ）
    ss_days = chart_df[days_col].values
    
    # 商品コード（ホバー表示用）
    product_codes = chart_df['商品コード'].values
    
    # Y軸範囲の計算（統一スケール用の最大値が指定されている場合はそれを使用）
    if y1_max is None:
        y1_max = ss_quantity.max() * 1.1 if len(ss_quantity) > 0 else 100
    if y2_max is None:
        y2_max = ss_days.max() * 1.1 if len(ss_days) > 0 else 50
    # 縦軸の最大値を四捨五入
    y1_max = round(y1_max)
    y2_max = round(y2_max)
    y1_range = [0, y1_max]
    y2_range = [0, y2_max]
    
    # Plotlyでサブプロットを作成（左Y軸と右Y軸）
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 棒グラフ：選択された安全在庫タイプの数量（左Y軸）
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=ss_quantity,
            name=f'{type_name}_数量',
            marker_color='rgb(100, 150, 200)',
            hovertemplate='<b>%{text}</b><br>' +
                          '受注量: %{customdata[0]:.2f}<br>' +
                          f'{type_name}_数量: %{{y:,.0f}}<br>' +
                          f'{type_name}_日数: %{{customdata[1]:.2f}}日<extra></extra>',
            text=[f'{code}' for code in product_codes],
            customdata=np.column_stack([chart_df['日当たり実績'].values, ss_days]),
            yaxis='y'
        ),
        secondary_y=False
    )
    
    # 折れ線グラフ：選択された安全在庫タイプの日数（右Y軸）
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=ss_days,
            name=f'{type_name}_日数',
            mode='lines+markers',
            marker=dict(size=4, color='rgb(200, 50, 50)'),
            line=dict(color='rgb(200, 50, 50)', width=2),
            hovertemplate='<b>%{text}</b><br>' +
                          '受注量: %{customdata[0]:.2f}<br>' +
                          f'{type_name}_数量: %{{customdata[1]:,.0f}}<br>' +
                          f'{type_name}_日数: %{{y:.2f}}日<extra></extra>',
            text=[f'{code}' for code in product_codes],
            customdata=np.column_stack([chart_df['日当たり実績'].values, ss_quantity]),
            yaxis='y2'
        ),
        secondary_y=True
    )
    
    # ABC区分の境界線を追加（修正前の位置に戻す）
    if 'ABC区分' in chart_df.columns:
        abc_categories = chart_df['ABC区分'].values
        
        # STEP1で作成された区分リストの順序を保持（重複を排除した順序リストを作成）
        unique_categories_ordered = []
        seen = set()
        for cat in abc_categories:
            if pd.notna(cat):
                display_cat = format_abc_category_for_display(cat)
                if display_cat and display_cat != "未分類" and display_cat not in seen:
                    unique_categories_ordered.append(display_cat)
                    seen.add(display_cat)
        
        # 各区分の開始位置（最初の商品コードのX位置）を特定
        boundaries = []  # [(区分名, 開始インデックス), ...]
        
        for category in unique_categories_ordered:
            # この区分が最初に出現する位置を検索
            first_index = None
            for i in range(len(abc_categories)):
                if pd.notna(abc_categories[i]):
                    display_cat = format_abc_category_for_display(abc_categories[i])
                    if display_cat == category:
                        first_index = i
                        break
            
            if first_index is not None:
                boundaries.append((category, first_index))
        
        # Y軸の最大値を取得（ラベルのY座標計算用）
        y_max = y1_max if y1_max is not None else (ss_quantity.max() * 1.1 if len(ss_quantity) > 0 else 100)
        # ラベルのY座標はグラフのy軸上限値の95%に固定（すべて同じ高さ）
        label_y = y_max * 0.95
        
        # 各境界位置に縦線とラベルを追加（区分の種類数と同じ本数の線を描画）
        for category, boundary_pos in boundaries:
            # 縦線を追加（細かい破線スタイル）
            fig.add_vline(
                x=boundary_pos,
                line_dash="dot",
                line_color="gray",
                line_width=1,
                opacity=0.7
            )
            
            # ラベルを縦線の右側に追加（x方向にオフセット、y方向は同じ高さ）
            fig.add_annotation(
                x=boundary_pos + 0.3,  # 線の右側にオフセット（約5-10px相当）
                y=label_y,
                text=f"{category}区分",
                showarrow=False,
                xref="x",
                yref="y",
                font=dict(size=12, color="#555555"),
                xanchor="left",  # 左揃えで右側に配置
                bgcolor="rgba(255,255,255,0)",
                bordercolor="rgba(255,255,255,0)"
            )
    
    # レイアウト設定
    fig.update_layout(
        title=f'受注量別 {type_name} 比較グラフ（異常値処理前）',
        xaxis_title='商品コード（数量・降順）',
        yaxis_title='数量',
        yaxis2_title='日数',
        height=500,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.08,  # 凡例の位置を上に移動してABC区分線との間隔を確保
            xanchor="right",
            x=1
        )
    )
    
    # Y軸の範囲を設定
    fig.update_yaxes(range=y1_range, secondary_y=False)
    fig.update_yaxes(
        title_text="日数",
        secondary_y=True,
        range=y2_range
    )
    
    # 横軸の設定（商品コードを表示するため、適度な間隔でラベルを表示）
    # データが多い場合は間引きして表示
    n_ticks = min(20, len(x_values))
    tick_indices = np.linspace(0, len(x_values) - 1, n_ticks, dtype=int)
    fig.update_xaxes(
        tickvals=tick_indices,
        ticktext=[f'{product_codes[i]}' for i in tick_indices],
        tickangle=45
    )
    
    return fig


def create_order_volume_comparison_chart_after(after_results_df: pd.DataFrame, before_results_df: Optional[pd.DataFrame] = None, safety_stock_type: str = "ss3", y1_max: Optional[float] = None, y2_max: Optional[float] = None) -> go.Figure:
    """
    受注量別 安全在庫比較グラフを生成（異常値処理前後の比較を1つのグラフに統合）
    
    Args:
        after_results_df: 異常値処理後の全機種の安全在庫算出結果DataFrame
        before_results_df: 異常値処理前のDataFrame（比較用、Noneの場合はAfterのみ表示）
        safety_stock_type: 安全在庫タイプ ("current", "ss1", "ss2", "ss3")
        y1_max: 左Y軸（数量）の最大値（Noneの場合は自動計算）
        y2_max: 右Y軸（日数）の最大値（Noneの場合は自動計算）
    
    Returns:
        Plotly Figureオブジェクト
    """
    # 安全在庫タイプに応じた列名を決定
    type_mapping = {
        "current": ("現行設定_数量", "現行設定_日数", "現行設定"),
        "ss1": ("安全在庫①_数量", "安全在庫①_日数", "安全在庫①"),
        "ss2": ("安全在庫②_数量", "安全在庫②_日数", "安全在庫②"),
        "ss3": ("安全在庫③_数量", "安全在庫③_日数", "安全在庫③")
    }
    
    # 異常値処理後の列名（最終安全在庫の場合は「最終」プレフィックスを付ける）
    if safety_stock_type == "current":
        after_quantity_col = "現行設定_数量"
        after_days_col = "現行設定_日数"
    else:
        # 安全在庫①、②、③の場合の列名を生成
        ss_num = type_mapping[safety_stock_type][2].replace('安全在庫', '').replace('①', '1').replace('②', '2').replace('③', '3')
        after_quantity_col = f"最終安全在庫{ss_num}_数量"
        after_days_col = f"最終安全在庫{ss_num}_日数"
        # 最終安全在庫の列が存在しない場合は、通常の安全在庫列を使用
        if after_quantity_col not in after_results_df.columns:
            after_quantity_col = type_mapping[safety_stock_type][0]
            after_days_col = type_mapping[safety_stock_type][1]
    
    before_quantity_col, before_days_col, type_name = type_mapping.get(safety_stock_type, type_mapping["ss3"])
    
    # 異常値処理後のデータを取得
    # 日当たり実績が0または欠損の機種は除外
    after_valid_mask = (
        (after_results_df['日当たり実績'].notna()) &
        (after_results_df['日当たり実績'] > 0) &
        (after_results_df[after_quantity_col].notna()) &
        (after_results_df[after_days_col].notna())
    )
    
    after_chart_df = after_results_df[after_valid_mask].copy()
    
    if len(after_chart_df) == 0:
        # 空のグラフを返す
        fig = go.Figure()
        fig.update_layout(title=f'受注量別 {type_name} 比較グラフ（異常値処理後）')
        return fig
    
    # 受注量（日当たり実績）で降順ソート
    after_chart_df = after_chart_df.sort_values('日当たり実績', ascending=False).reset_index(drop=True)
    
    # 横軸：インデックス順（受注量降順）
    x_values = after_chart_df.index.tolist()
    
    # 異常値処理後のデータ
    after_ss_quantity = after_chart_df[after_quantity_col].values
    after_ss_days = after_chart_df[after_days_col].values
    product_codes = after_chart_df['商品コード'].values
    
    # 異常値処理前のデータ（存在する場合）
    before_ss_quantity = None
    before_ss_days = None
    before_daily_actual = None
    if before_results_df is not None:
        # 異常値処理前のデータを取得
        before_valid_mask = (
            (before_results_df['日当たり実績'].notna()) &
            (before_results_df['日当たり実績'] > 0) &
            (before_results_df[before_quantity_col].notna()) &
            (before_results_df[before_days_col].notna())
        )
        before_chart_df = before_results_df[before_valid_mask].copy()
        if len(before_chart_df) > 0:
            # 商品コードでマッチングして順序を揃える（after_chart_dfの順序に合わせる）
            before_dict = dict(zip(
                before_chart_df['商品コード'],
                zip(
                    before_chart_df[before_quantity_col],
                    before_chart_df[before_days_col],
                    before_chart_df['日当たり実績']
                )
            ))
            before_ss_quantity = np.array([before_dict.get(code, (np.nan, np.nan, np.nan))[0] for code in product_codes])
            before_ss_days = np.array([before_dict.get(code, (np.nan, np.nan, np.nan))[1] for code in product_codes])
            before_daily_actual = np.array([before_dict.get(code, (np.nan, np.nan, np.nan))[2] for code in product_codes])
    
    # Y軸範囲の計算（統一スケール用の最大値が指定されている場合はそれを使用）
    if y1_max is None:
        all_quantities = [after_ss_quantity]
        all_days = [after_ss_days]
        if before_ss_quantity is not None:
            all_quantities.append(before_ss_quantity[~np.isnan(before_ss_quantity)])
            all_days.append(before_ss_days[~np.isnan(before_ss_days)])
        y1_max = max([arr.max() for arr in all_quantities if len(arr) > 0]) * 1.1 if any(len(arr) > 0 for arr in all_quantities) else 100
        y2_max = max([arr.max() for arr in all_days if len(arr) > 0]) * 1.1 if any(len(arr) > 0 for arr in all_days) else 50
    # 縦軸の最大値を四捨五入
    y1_max = round(y1_max)
    y2_max = round(y2_max)
    y1_range = [0, y1_max]
    y2_range = [0, y2_max]
    
    # Plotlyでサブプロットを作成（左Y軸と右Y軸）
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 異常値処理前のデータを先に追加（重ね表示用 - 薄い色で透過）
    if before_ss_quantity is not None and before_ss_days is not None:
        # 棒グラフ：選択された安全在庫タイプの数量（異常値処理前、透過0.35で重ね表示）
        fig.add_trace(
            go.Bar(
                x=x_values,
                y=before_ss_quantity,
                name=f'{type_name}_数量（異常値処理前）',
                marker_color='rgba(100, 150, 255, 0.35)',  # 薄い青色、透明度35%（重ね表示用）
                offsetgroup=None,  # グループ化を無効化して重ね表示
                hovertemplate='<b>%{text}</b><br>' +
                              '受注量: %{customdata[0]:.2f}<br>' +
                              f'{type_name}_数量（異常値処理前）: %{{y:,.0f}}<br>' +
                              f'{type_name}_日数（異常値処理前）: %{{customdata[1]:.2f}}日<extra></extra>',
                text=[f'{code}' for code in product_codes],
                customdata=np.column_stack([
                    before_daily_actual if before_daily_actual is not None and len(before_daily_actual) > 0 else after_chart_df['日当たり実績'].values,
                    before_ss_days
                ]),
                yaxis='y'
            ),
            secondary_y=False
        )
        
        # 折れ線グラフ：選択された安全在庫タイプの日数（異常値処理前、見やすく調整）
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=before_ss_days,
                name=f'{type_name}_日数（異常値処理前）',
                mode='lines+markers',
                marker=dict(size=4, color='rgba(200, 100, 100, 0.5)'),  # 薄い赤色、透明度50%（見やすく調整）
                line=dict(color='rgba(200, 100, 100, 0.5)', width=1.5),  # 薄い赤色、透明度50%、少し太め
                hovertemplate='<b>%{text}</b><br>' +
                              '受注量: %{customdata[0]:.2f}<br>' +
                              f'{type_name}_数量（異常値処理前）: %{{customdata[1]:,.0f}}<br>' +
                              f'{type_name}_日数（異常値処理前）: %{{y:.2f}}日<extra></extra>',
                text=[f'{code}' for code in product_codes],
                customdata=np.column_stack([
                    before_daily_actual if before_daily_actual is not None and len(before_daily_actual) > 0 else after_chart_df['日当たり実績'].values,
                    before_ss_quantity
                ]),
                yaxis='y2'
            ),
            secondary_y=True
        )
    
    # 異常値処理後のデータを追加（濃い色で重ね表示 - 主役）
    # 棒グラフ：選択された安全在庫タイプの数量（異常値処理後）
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=after_ss_quantity,
            name=f'{type_name}_数量（異常値処理後）',
            marker_color='rgb(60, 120, 220)',  # 青色（異常値処理前より濃いが、適度な濃さ）
            offsetgroup=None,  # グループ化を無効化して重ね表示
            hovertemplate='<b>%{text}</b><br>' +
                          '受注量: %{customdata[0]:.2f}<br>' +
                          f'{type_name}_数量（異常値処理後）: %{{y:,.0f}}<br>' +
                          f'{type_name}_日数（異常値処理後）: %{{customdata[1]:.2f}}日<extra></extra>',
            text=[f'{code}' for code in product_codes],
            customdata=np.column_stack([after_chart_df['日当たり実績'].values, after_ss_days]),
            yaxis='y'
        ),
        secondary_y=False
    )
    
    # 折れ線グラフ：選択された安全在庫タイプの日数（異常値処理後）
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=after_ss_days,
            name=f'{type_name}_日数（異常値処理後）',
            mode='lines+markers',
            marker=dict(size=6, color='rgb(220, 20, 20)'),  # 濃い赤色、大きめ
            line=dict(color='rgb(220, 20, 20)', width=2),  # 濃い赤色、適度な太さ
            hovertemplate='<b>%{text}</b><br>' +
                          '受注量: %{customdata[0]:.2f}<br>' +
                          f'{type_name}_数量（異常値処理後）: %{{customdata[1]:,.0f}}<br>' +
                          f'{type_name}_日数（異常値処理後）: %{{y:.2f}}日<extra></extra>',
            text=[f'{code}' for code in product_codes],
            customdata=np.column_stack([after_chart_df['日当たり実績'].values, after_ss_quantity]),
            yaxis='y2'
        ),
        secondary_y=True
    )
    
    # ABC区分の境界線を追加（修正前の位置に戻す）
    if 'ABC区分' in after_chart_df.columns:
        abc_categories = after_chart_df['ABC区分'].values
        
        # STEP1で作成された区分リストの順序を保持（重複を排除した順序リストを作成）
        unique_categories_ordered = []
        seen = set()
        for cat in abc_categories:
            if pd.notna(cat):
                display_cat = format_abc_category_for_display(cat)
                if display_cat and display_cat != "未分類" and display_cat not in seen:
                    unique_categories_ordered.append(display_cat)
                    seen.add(display_cat)
        
        # 各区分の開始位置（最初の商品コードのX位置）を特定
        boundaries = []  # [(区分名, 開始インデックス), ...]
        
        for category in unique_categories_ordered:
            # この区分が最初に出現する位置を検索
            first_index = None
            for i in range(len(abc_categories)):
                if pd.notna(abc_categories[i]):
                    display_cat = format_abc_category_for_display(abc_categories[i])
                    if display_cat == category:
                        first_index = i
                        break
            
            if first_index is not None:
                boundaries.append((category, first_index))
        
        # Y軸の最大値を取得（ラベルのY座標計算用）
        y_max = y1_max if y1_max is not None else (after_ss_quantity.max() * 1.1 if len(after_ss_quantity) > 0 else 100)
        # ラベルのY座標はグラフのy軸上限値の95%に固定（すべて同じ高さ）
        label_y = y_max * 0.95
        
        # 各境界位置に縦線とラベルを追加（区分の種類数と同じ本数の線を描画）
        for category, boundary_pos in boundaries:
            # 縦線を追加（細かい破線スタイル）
            fig.add_vline(
                x=boundary_pos,
                line_dash="dot",
                line_color="gray",
                line_width=1,
                opacity=0.7
            )
            
            # ラベルを縦線の右側に追加（x方向にオフセット、y方向は同じ高さ）
            fig.add_annotation(
                x=boundary_pos + 0.3,  # 線の右側にオフセット（約5-10px相当）
                y=label_y,
                text=f"{category}区分",
                showarrow=False,
                xref="x",
                yref="y",
                font=dict(size=12, color="#555555"),
                xanchor="left",  # 左揃えで右側に配置
                bgcolor="rgba(255,255,255,0)",
                bordercolor="rgba(255,255,255,0)"
            )
    
    # レイアウト設定
    fig.update_layout(
        title=f'受注量別 {type_name} 比較グラフ（異常値処理後）',
        xaxis_title='商品コード（受注数・降順）',
        yaxis_title='数量',
        yaxis2_title='日数',
        height=500,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.08,  # 凡例の位置を上に移動してABC区分線との間隔を確保
            xanchor="right",
            x=1
        ),
        barmode='overlay'  # 棒グラフを完全に重ねて表示
    )
    
    # Y軸の範囲を設定（Before/Afterの最大値を基準に固定）
    fig.update_yaxes(range=y1_range, secondary_y=False)
    fig.update_yaxes(
        title_text="日数",
        secondary_y=True,
        range=y2_range
    )
    
    # 横軸の設定（商品コードを表示するため、適度な間隔でラベルを表示）
    # データが多い場合は間引きして表示
    n_ticks = min(20, len(x_values))
    tick_indices = np.linspace(0, len(x_values) - 1, n_ticks, dtype=int)
    fig.update_xaxes(
        tickvals=tick_indices,
        ticktext=[f'{product_codes[i]}' for i in tick_indices],
        tickangle=45
    )
    
    return fig


def create_outlier_processing_results_chart(product_code: str,
                                            before_data: pd.Series,
                                            after_data: pd.Series,
                                            outlier_indices: list) -> go.Figure:
    """
    異常値処理結果のBefore/After比較グラフを生成
    
    Args:
        product_code: 商品コード
        before_data: 異常値処理前の実績データ
        after_data: 異常値処理後の実績データ
        outlier_indices: 異常値のインデックスリスト
    
    Returns:
        Plotly Figureオブジェクト
    """
    dates = pd.to_datetime(before_data.index)
    
    fig = go.Figure()
    
    # Before実績 - 赤色
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=before_data.values,
            name="Before（処理前）",
            mode='lines+markers',
            marker=dict(size=4),
            line=dict(color='red', width=1.5)  # 赤色
        )
    )
    
    # After実績 - 薄めの黒系（やや太線）
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=after_data.values,
            name="After（処理後）",
            mode='lines+markers',
            marker=dict(size=4),
            line=dict(color='#808080', width=2.5)  # 薄めの黒系（やや太線）
        )
    )
    
    # 異常値マーキング（●）
    if outlier_indices:
        outlier_dates = [dates[i] for i in outlier_indices]
        outlier_values = [before_data.iloc[i] for i in outlier_indices]
        fig.add_trace(
            go.Scatter(
                x=outlier_dates,
                y=outlier_values,
                name="異常値",
                mode='markers',
                marker=dict(size=10, symbol='circle', color='red', line=dict(width=2, color='darkred')),
                showlegend=True
            )
        )
    
    fig.update_layout(
        title=f"{product_code} - 異常値処理結果（Before/After）",
        xaxis=dict(title="日付", type="date", tickformat="%Y-%m"),
        yaxis=dict(title="数量"),
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        height=500,
        margin=dict(l=80, r=80, t=80, b=100)
    )
    
    return fig


def create_outlier_lt_delta_comparison_chart(product_code: str,
                                             before_delta2: pd.Series,
                                             before_delta3: pd.Series,
                                             after_delta2: pd.Series,
                                             after_delta3: pd.Series,
                                             before_ss1: Optional[float],
                                             before_ss2: float,
                                             before_ss3: float,
                                             after_ss1: Optional[float],
                                             after_ss2: float,
                                             after_ss3: float,
                                             is_p_zero: bool,
                                             is_before_ss1_undefined: bool,
                                             is_after_ss1_undefined: bool) -> go.Figure:
    """
    LT間差分の分布（Before/After）のヒストグラムを生成
    
    Args:
        product_code: 商品コード
        before_delta2: Beforeの実績−平均の差分
        before_delta3: Beforeの実績−計画の差分
        after_delta2: Afterの実績−平均の差分
        after_delta3: Afterの実績−計画の差分
        before_ss1: Beforeの安全在庫①
        before_ss2: Beforeの安全在庫②
        before_ss3: Beforeの安全在庫③
        after_ss1: Afterの安全在庫①
        after_ss2: Afterの安全在庫②
        after_ss3: Afterの安全在庫③
        is_p_zero: 欠品許容率が0%かどうか
        is_before_ss1_undefined: Beforeの安全在庫①が未定義かどうか
        is_after_ss1_undefined: Afterの安全在庫①が未定義かどうか
    
    Returns:
        Plotly Figureオブジェクト
    """
    # 横軸レンジを統一（Before/Afterの全データと安全在庫の値を考慮）
    all_delta_values = list(before_delta2.values) + list(before_delta3.values) + list(after_delta2.values) + list(after_delta3.values)
    
    # 安全在庫の値も範囲計算に含める（Noneでない値のみ）
    safety_stock_values = []
    if before_ss1 is not None:
        safety_stock_values.append(before_ss1)
    if before_ss2 is not None:
        safety_stock_values.append(before_ss2)
    if before_ss3 is not None:
        safety_stock_values.append(before_ss3)
    if after_ss1 is not None:
        safety_stock_values.append(after_ss1)
    if after_ss2 is not None:
        safety_stock_values.append(after_ss2)
    if after_ss3 is not None:
        safety_stock_values.append(after_ss3)
    
    # データと安全在庫の値を合わせて範囲を計算
    all_values = all_delta_values + safety_stock_values
    min_val = min(all_values)
    max_val = max(all_values)
    range_margin = (max_val - min_val) * 0.1  # 10%のマージンを追加
    x_range = [min_val - range_margin, max_val + range_margin]
    
    # 統一したビン数を設定
    nbins = 30
    
    # 共通のビン境界を明示的に計算
    bin_edges = np.linspace(min_val - range_margin, max_val + range_margin, nbins + 1)
    
    # 縦軸レンジを統一（Before/Afterの全ヒストグラムの最大頻度を考慮）
    before_delta2_counts, _ = np.histogram(before_delta2.values, bins=bin_edges)
    before_delta3_counts, _ = np.histogram(before_delta3.values, bins=bin_edges)
    after_delta2_counts, _ = np.histogram(after_delta2.values, bins=bin_edges)
    after_delta3_counts, _ = np.histogram(after_delta3.values, bins=bin_edges)
    
    max_freq = max(
        np.max(before_delta2_counts),
        np.max(before_delta3_counts),
        np.max(after_delta2_counts),
        np.max(after_delta3_counts)
    )
    y_range = [0, max_freq * 1.1]  # 10%のマージンを追加
    
    # サブプロット作成（2行2列）
    # 左側：実績−平均、右側：実績−計画
    # 上段：Before、下段：After
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "Before: リードタイム間差分（実績 − 平均）※実績バラつき",
            "Before: リードタイム間差分（実績 − 計画）※計画誤差",
            "After: リードタイム間差分（実績 − 平均）※実績バラつき",
            "After: リードタイム間差分（実績 − 計画）※計画誤差"
        ],
        vertical_spacing=0.08,
        horizontal_spacing=0.1,
        specs=[[{"secondary_y": False}, {"secondary_y": False}],
               [{"secondary_y": False}, {"secondary_y": False}]]
    )
    
    # Before: 実績−平均 - 薄めの黒系（左側、上段）
    fig.add_trace(
        go.Histogram(
            x=before_delta2.values,
            name='実績−平均',
            opacity=0.8,
            xbins=dict(start=bin_edges[0], end=bin_edges[-1], size=bin_edges[1] - bin_edges[0]),
            marker_color='rgba(128, 128, 128, 0.8)',  # 薄めの黒系
            showlegend=False
        ),
        row=1, col=1
    )
    
    # Before: 安全在庫①（理論値）をモデル②に重ね表示（赤色破線）
    # before_ss1が存在する場合は表示（is_before_ss1_undefinedとis_p_zeroの条件を緩和）
    if before_ss1 is not None:
        fig.add_vline(
            x=before_ss1,
            line_dash="dash",
            line_color="red",  # 赤色
            annotation_text="",  # 安全在庫①は線だけ表示（ラベルなし）
            annotation_position="top right",
            row=1, col=1,
            line_width=2
        )
    
    # Before: 安全在庫②（実績−平均）を表示（濃い黒系破線）
    fig.add_vline(
        x=before_ss2,
        line_dash="dash",
        line_color="#333333",  # 濃い黒系
        annotation_text="安全在庫②",  # ラベルを表示
        annotation_position="top right",
        row=1, col=1,
        line_width=2
    )
    
    # Before: 実績−計画 - 薄めの緑系（右側、上段）
    fig.add_trace(
        go.Histogram(
            x=before_delta3.values,
            name='実績−計画',
            opacity=0.8,
            xbins=dict(start=bin_edges[0], end=bin_edges[-1], size=bin_edges[1] - bin_edges[0]),
            marker_color='rgba(100, 200, 150, 0.8)',  # 薄めの緑系（現状維持）
            showlegend=False
        ),
        row=1, col=2
    )
    
    # Before: 安全在庫③（実績−計画）を表示（濃い緑系破線）
    fig.add_vline(
        x=before_ss3,
        line_dash="dash",
        line_color="#228B22",  # 濃い緑系
        annotation_text="安全在庫③",  # ラベルを表示
        annotation_position="top right",
        row=1, col=2,
        line_width=2
    )
    
    # After: 実績−平均 - 薄めの黒系（左側、下段）
    fig.add_trace(
        go.Histogram(
            x=after_delta2.values,
            name='実績−平均',
            opacity=0.8,
            xbins=dict(start=bin_edges[0], end=bin_edges[-1], size=bin_edges[1] - bin_edges[0]),
            marker_color='rgba(128, 128, 128, 0.8)',  # 薄めの黒系
            showlegend=False
        ),
        row=2, col=1
    )
    
    # After: 安全在庫①（理論値）をモデル②に重ね表示（赤色破線）
    # p=0%の時は①を非表示
    if after_ss1 is not None and not is_after_ss1_undefined and not is_p_zero:
        fig.add_vline(
            x=after_ss1,
            line_dash="dash",
            line_color="red",  # 赤色
            annotation_text="",  # 安全在庫①は線だけ表示（ラベルなし）
            annotation_position="top right",
            row=2, col=1,
            line_width=2
        )
    
    # After: 安全在庫②（実績−平均）を表示（濃い黒系破線）
    fig.add_vline(
        x=after_ss2,
        line_dash="dash",
        line_color="#333333",  # 濃い黒系
        annotation_text="安全在庫②",  # ラベルを表示
        annotation_position="top right",
        row=2, col=1,
        line_width=2
    )
    
    # After: 実績−計画 - 薄めの緑系（右側、下段）
    fig.add_trace(
        go.Histogram(
            x=after_delta3.values,
            name='実績−計画',
            opacity=0.8,
            xbins=dict(start=bin_edges[0], end=bin_edges[-1], size=bin_edges[1] - bin_edges[0]),
            marker_color='rgba(100, 200, 150, 0.8)',  # 薄めの緑系（現状維持）
            showlegend=False
        ),
        row=2, col=2
    )
    
    # After: 安全在庫③（実績−計画）を表示（濃い緑系破線）
    fig.add_vline(
        x=after_ss3,
        line_dash="dash",
        line_color="#228B22",  # 濃い緑系
        annotation_text="安全在庫③",  # ラベルを表示
        annotation_position="top right",
        row=2, col=2,
        line_width=2
    )
    
    # 凡例用のダミートレースを追加（破線の凡例を表示するため）
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode='lines',
            name='安全在庫①',
            line=dict(color='red', dash='dash', width=2),  # 赤色
            showlegend=True,
            legendgroup='safety_stock'
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode='lines',
            name='安全在庫②',
            line=dict(color='#333333', dash='dash', width=2),  # 濃い黒系
            showlegend=True,
            legendgroup='safety_stock'
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode='lines',
            name='安全在庫③',
            line=dict(color='#228B22', dash='dash', width=2),  # 濃い緑系
            showlegend=True,
            legendgroup='safety_stock'
        )
    )
    
    # レイアウト設定（処理前と同じスタイル）
    fig.update_layout(
        height=800,
        showlegend=True,
        title_text=f"{product_code} - リードタイム間差分の分布（Before/After 比較）",
        margin=dict(t=170, b=100, r=80),  # 右側の余白を追加して「安全在庫③」の切れを防止
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.12,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(size=12)
        ),
        legend_traceorder="normal"
    )
    
    # 横軸・縦軸レンジを統一
    # 上段（row=1）：x軸タイトルと目盛りを非表示
    fig.update_xaxes(range=x_range, title_text="", showticklabels=False, row=1, col=1)
    fig.update_xaxes(range=x_range, title_text="", showticklabels=False, row=1, col=2)
    # 下段（row=2）：x軸タイトルと目盛りを表示
    fig.update_xaxes(range=x_range, title_text="差分", row=2, col=1)
    fig.update_xaxes(range=x_range, title_text="差分", row=2, col=2)
    fig.update_yaxes(range=y_range, title_text="件数", row=1, col=1)
    fig.update_yaxes(range=y_range, title_text="件数", row=1, col=2)
    fig.update_yaxes(range=y_range, title_text="件数", row=2, col=1)
    fig.update_yaxes(range=y_range, title_text="件数", row=2, col=2)
    
    return fig


def create_after_processing_comparison_chart(product_code: str,
                                             before_values: list,
                                             after_values: list) -> go.Figure:
    """
    処理後の安全在庫再算出結果のBefore/After比較グラフを生成
    
    Args:
        product_code: 商品コード
        before_values: Beforeの安全在庫日数リスト [ss1, ss2, ss3]
        after_values: Afterの安全在庫日数リスト [ss1, ss2, ss3]
    
    Returns:
        Plotly Figureオブジェクト
    """
    models = ['安全在庫①', '安全在庫②', '安全在庫③']
    
    fig = go.Figure()
    
    # Before
    fig.add_trace(
        go.Bar(
            x=models,
            y=before_values,
            name="Before（処理前）",
            marker_color='rgba(214, 39, 40, 0.7)'
        )
    )
    
    # After
    fig.add_trace(
        go.Bar(
            x=models,
            y=after_values,
            name="After（処理後）",
            marker_color='rgba(44, 160, 44, 0.7)'
        )
    )
    
    fig.update_layout(
        title=f"{product_code} - 安全在庫 Before/After 比較",
        xaxis=dict(title="モデル"),
        yaxis=dict(title="安全在庫日数"),
        barmode='group',
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    
    return fig

