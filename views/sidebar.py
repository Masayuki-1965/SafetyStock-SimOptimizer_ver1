"""
サイドバーUI
STEPナビゲーションを表示
"""

import streamlit as st


def display_sidebar():
    """STEPナビゲーションをサイドバーに表示"""
    with st.sidebar:
        st.markdown('<div class="sidebar-analysis-flow-title">分析フロー</div>', unsafe_allow_html=True)
        st.markdown('<div class="step-description">本分析は以下の3つのステップで行います。</div>', unsafe_allow_html=True)
        
        # STEPボタンのスタイル定義
        step_styles = {
            1: {"main": "STEP 1：データ取り込みと前処理", "sub": None},
            2: {"main": "STEP 2：安全在庫算出ロジック体感", "sub": "　　　　（選定機種）"},
            3: {"main": "STEP 3：安全在庫算出と登録値作成", "sub": "　　　　（全機種）"}
        }
        
        # 各STEPの表示とクリック処理
        for step_num in [1, 2, 3]:
            is_active = st.session_state.current_step == step_num
            button_label = step_styles[step_num]["main"]
            if step_styles[step_num]["sub"]:
                # 改行してインデントを入れる（「安全在庫算出」の「安」の位置に合わせる）
                # 「STEP 2：」は7文字、「安全在庫算出」の「安」は8文字目なので、全角スペース8個を追加
                button_label = f"{button_label}\n        {step_styles[step_num]['sub']}"

            if is_active:
                # アクティブなステップはprimaryスタイル（濃い青＋白字）
                if st.button(button_label, key=f"step_{step_num}", use_container_width=True, type="primary"):
                    pass  # 既にアクティブなステップは何もしない
            else:
                # 非アクティブなステップはsecondaryスタイル（薄い青＋青字）
                if st.button(button_label, key=f"step_{step_num}", use_container_width=True, type="secondary"):
                    st.session_state.current_step = step_num
                    # ページ最上部にスクロールするためのマーカーを設定
                    st.session_state.scroll_to_top = True
                    st.rerun()
        
        # 最初からやり直す場合の説明
        st.markdown("---")
        st.markdown('<div class="step-sub-section">最初からやり直す場合:</div>', unsafe_allow_html=True)
        st.markdown('<div class="step-description">画面左上の更新ボタン (⟳) をクリックするか、Ctrl+Rを押して、STEP 1のデータ取り込みから再実行してください。</div>', unsafe_allow_html=True)
        
        # Plotlyインタラクティブグラフの使い方ガイド
        st.markdown("---")
        with st.expander("Plotlyインタラクティブグラフの使い方", expanded=False):
            st.markdown("""
            - **データ確認**: グラフ上の線やポイントにマウスを置くと、詳細値がポップアップ表示されます
            - **拡大表示**: グラフ内で見たい期間をドラッグして範囲選択すると拡大表示されます
            - **レンジ(範囲)スライダー**: グラフ下部のスライダーバーで表示期間を調整できます(ハンドルをドラッグして範囲を変更)
            - **表示移動**: 拡大後、右クリックドラッグで表示位置を調整できます
            - **初期表示**: ダブルクリックすると全期間表示に戻ります
            - **系列表示切替**: グラフ上部の凡例をクリックすると系列の表示/非表示を切り替えできます
            """)

