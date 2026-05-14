import streamlit as st
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import os
from datetime import datetime

# 파일 저장 경로 설정
HISTORY_FILE = 'trade_history.csv'

# [추가] 한국 주식 종목 리스트 불러오기 (캐싱 처리해서 속도 높임)
@st.cache_data
def get_krx_list():
    # 주식 리스트와 ETF 리스트를 각각 가져와서 합치기
    df_stocks = fdr.StockListing('KRX') # 일반 주식 (KOSPI, KOSDAQ, KONEX)
    df_etfs = fdr.StockListing('ETF/KR') # 국내 상장 ETF
    
    # 필요한 컬럼만 선택해서 합치기
    df_stocks = df_stocks[['Name', 'Code', 'Market']]
    df_etfs['Market'] = 'ETF' # ETF는 마켓 구분을 'ETF'로 통일
    df_etfs = df_etfs[['Name', 'Symbol', 'Market']].rename(columns={'Symbol': 'Code'})
    
    df_total = pd.concat([df_stocks, df_etfs], ignore_index=True)
    
    # 검색용 이름 생성 (예: 삼성전자 | 005930)
    df_total['display_name'] = df_total['Name'] + " | " + df_total['Code']
    return df_total

# 데이터 불러오기 함수
def load_data():
    if os.path.exists(HISTORY_FILE):
        return pd.read_csv(HISTORY_FILE)
    else:
        return pd.DataFrame(columns=['날짜', '종목명', '구분', '수량', '단가', '종목코드'])

# 1. 페이지 설정
st.set_page_config(page_title="새봄의 StockView", layout="wide")
st.title("stockView : 자산 관리 마스터")

# 데이터 로드
df_history = load_data()
krx_list = get_krx_list()

# 2. 사이드바: 매매 기록 입력
st.sidebar.header("매매 기록 입력")
with st.sidebar.form("trade_form", clear_on_submit=True):
    date = st.date_input("매매 날짜", datetime.now())
    
    # 텍스트 입력 대신 검색 가능한 선택창으로 변경
    selected_stock = st.selectbox(
        "종목 선택 (이름으로 검색)",
        krx_list['display_name'].tolist(),
        help="삼성전자, 현대차 등 이름을 입력해 보세요! 데이터가 뜨지 않을 경우 코드로 검색해보세요 !"
    )
    
    trade_type = st.selectbox("매매 구분", ["매수", "매도"])
    quantity = st.number_input("수량", min_value=0.1, step=0.1)
    price = st.number_input("거래 단가", min_value=0.0, step=100.0)
    
    submitted = st.form_submit_button("기록 저장")
    
    if submitted:
        # 선택된 종목 이름에서 코드와 시장 정보를 추출
        stock_name = selected_stock.split(" | ")[0]
        stock_code = selected_stock.split(" | ")[1]
        
        # 여기서 market 변수를 정의함!
        market_data = krx_list[krx_list['Code'] == stock_code]
        if not market_data.empty:
            market = market_data['Market'].values[0]
        else:
            market = "KOSPI" # 기본값 설정

        if market in ['KOSPI', 'ETF']:
            yf_code = f"{stock_code}.KS"
        else:
            yf_code = f"{stock_code}.KQ"
            
        # 데이터프레임 생성 및 저장
        new_data = pd.DataFrame([[date, stock_name, trade_type, quantity, price, yf_code]], 
                                columns=['날짜', '종목명', '구분', '수량', '단가', '종목코드'])
        df_history = pd.concat([df_history, new_data], ignore_index=True)
        df_history.to_csv(HISTORY_FILE, index=False)
        st.sidebar.success(f"{stock_name} 저장 완료!")

# 3. 메인 화면: 포트폴리오 계산 로직
st.subheader("📊 나의 포트폴리오")

if not df_history.empty:
    portfolio = []
    # '종목코드' 기준으로 그룹화
    for ticker in df_history['종목코드'].unique():
        temp_df = df_history[df_history['종목코드'] == ticker]
        stock_name = temp_df['종목명'].iloc[0]
        
        total_qty = 0
        total_cost = 0
        
        for _, row in temp_df.iterrows():
            if row['구분'] == "매수":
                total_cost += (row['수량'] * row['단가'])
                total_qty += row['수량']
            else:
                total_qty -= row['수량']
        
        if total_qty > 0:
            avg_price = total_cost / (temp_df[temp_df['구분']=="매수"]['수량'].sum())
            
            try:
                # 실시간 주가 가져오기
                curr_price = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
            except:
                curr_price = 0
                
            portfolio.append({
                "종목": stock_name,
                "종목코드": ticker,
                "보유수량": total_qty,
                "평단가": round(avg_price, 2),
                "현재가": round(curr_price, 2),
                "수익률": round((curr_price - avg_price) / avg_price * 100, 2) if avg_price > 0 else 0,
                "평가금액": round(curr_price * total_qty, 2)
            })

    if portfolio:
        res_df = pd.DataFrame(portfolio)

        # 1. 합계 데이터 계산 (변수 선언)
        total_eval_amount = res_df['평가금액'].sum()  # 전체 평가 금액 합계
        total_purchase_amount = (res_df['보유수량'] * res_df['평단가']).sum() # 전체 매수 금액 합계
        
        # 수익률 계산 (분모가 0인 경우 방지)
        if total_purchase_amount > 0:
            total_profit_rate = round((total_eval_amount - total_purchase_amount) / total_purchase_amount * 100, 2)
            total_profit_won = int(total_eval_amount - total_purchase_amount)
        else:
            total_profit_rate = 0
            total_profit_won = 0

        # 2.모바일 최적화 요약 대시보드
        st.subheader("🚀 포트폴리오 요약")
        col1, col2 = st.columns(2)
        
        with col1:
            # 총 자산을 큰 글씨로 표시
            st.metric("총 자산", f"{int(total_eval_amount):,}원")
            
        with col2:
            # 전체 수익률을 표시 (수익 금액을 delta로 넣어서 화살표 표시)
            st.metric("전체 수익률", f"{total_profit_rate}%", f"{total_profit_won:,}원")
        
        st.divider() # 구분선 하나 그어주면 더 깔끔해!

        # 3. 상세 내역 표 및 다운로드 버튼
        st.subheader("📝 상세 내역")
        st.dataframe(res_df, use_container_width=True)

        csv = res_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("🔽 포트폴리오 엑셀(CSV) 다운로드", csv, 'my_portfolio.csv', 'text/csv')
    else:
        # [추가] 데이터가 하나도 없을 때 보여줄 안내 문구
        st.info("💡 아직 등록된 매매 기록이 없네! 왼쪽 사이드바에서 종목을 입력하고 '기록 저장'을 눌러줘.")
with st.expander("📜 전체 매매 이력 확인"):
    st.table(df_history)
