import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
import numpy as np

# Configure Streamlit
st.set_page_config(layout="wide")
st.title("📈 BTST Stock Scanner")
st.caption("Scan for Breakout Stocks with Momentum and Volume Criteria")

# Handle pandas_ta installation
try:
    import pandas_ta as ta
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas_ta"])
    import pandas_ta as ta

# Load stock list from Excel
try:
    stock_sheets = pd.ExcelFile('stocklist.xlsx').sheet_names
except FileNotFoundError:
    st.error("Error: stocklist.xlsx file not found. Please make sure it's in the same directory.")
    st.stop()

selected_sheet = st.selectbox("Select Sheet", stock_sheets)

# Read symbols from selected sheet
try:
    df_stocks = pd.read_excel('stocklist.xlsx', sheet_name=selected_sheet)
    if 'Symbol' not in df_stocks.columns:
        st.error("Column 'Symbol' not found in the sheet. Please ensure your Excel sheet has a 'Symbol' column.")
        st.stop()
        
    symbols = df_stocks['Symbol'].tolist()
    st.success(f"Loaded {len(symbols)} symbols from {selected_sheet}")
except Exception as e:
    st.error(f"Error reading Excel sheet: {str(e)}")
    st.stop()

# Date selection
today = datetime.date.today()
selected_date = st.date_input("Analysis Date", value=today - datetime.timedelta(days=1))
analysis_date = pd.Timestamp(selected_date)

# Download index data
@st.cache_data
def get_index_data(date):
    idx_symbol = "^NSEI"
    end_date = date + datetime.timedelta(days=1)
    idx_data = yf.download(idx_symbol, start=date, end=end_date, progress=False)
    return idx_data

index_data = get_index_data(selected_date)

if analysis_date not in index_data.index:
    st.warning(f"No index data available for {selected_date}. Please select a valid trading day.")
    st.stop()

# Calculate index metrics
idx_open = index_data.loc[analysis_date, 'Open']
idx_close = index_data.loc[analysis_date, 'Close']
idx_high = index_data.loc[analysis_date, 'High']
idx_low = index_data.loc[analysis_date, 'Low']
idx_pct_change = ((idx_close - idx_open) / idx_open) * 100

# Main analysis function
@st.cache_data
def analyze_stock(symbol, analysis_date):
    try:
        # Download data
        end_date = analysis_date + datetime.timedelta(days=1)
        start_date = analysis_date - datetime.timedelta(days=60)
        data = yf.download(symbol, start=start_date, end=end_date, progress=False)
        
        # Check if analysis date exists
        if analysis_date not in data.index:
            return None
        
        today = data.loc[analysis_date]
        prev_day = data[data.index < analysis_date].iloc[-1] if data.index[0] < analysis_date else None
        
        # Basic metrics
        pct_change = ((today['Close'] - today['Open']) / today['Open']) * 100
        pct_close_near_high = ((today['Close'] - today['Low']) / (today['High'] - today['Low'])) * 100 if today['High'] != today['Low'] else 0
        close_above_prev_high = today['Close'] > prev_day['High'] if prev_day is not None else False
        
        # Volume metrics
        avg_volume = data['Volume'].rolling(window=10).mean().iloc[-2]  # Previous day's 10D avg volume
        volume_spike = today['Volume'] / avg_volume if avg_volume > 0 else 0
        
        # Volatility
        intraday_range_pct = ((today['High'] - today['Low']) / today['Open']) * 100
        
        # Technical indicators
        # RSI (14 days)
        rsi = ta.rsi(data['Close'], length=14).iloc[-1]
        
        # MACD
        macd = ta.macd(data['Close']).iloc[-1]
        
        # Bollinger Bands
        bb = ta.bbands(data['Close'], length=20).iloc[-1]
        
        return {
            'Symbol': symbol,
            'Open': today['Open'],
            'High': today['High'],
            'Low': today['Low'],
            'Close': today['Close'],
            'Volume': today['Volume'],
            'Avg Volume (10D)': avg_volume,
            '% Price Change': pct_change,
            '% Close Near High': pct_close_near_high,
            'Close > Prev High': close_above_prev_high,
            'Volume Spike': volume_spike,
            'Intraday Range %': intraday_range_pct,
            'RSI (14)': rsi,
            'MACD': macd['MACD_12_26_9'],
            'MACD Signal': macd['MACDs_9'],
            'BB Upper': bb['BBU_20_2.0'],
            'BB Middle': bb['BBM_20_2.0'],
            'BB Lower': bb['BBL_20_2.0'],
            'Close > BB Upper': today['Close'] > bb['BBU_20_2.0']
        }
    except Exception as e:
        st.write(f"Error analyzing {symbol}: {str(e)}")
        return None

# Progress bar for analysis
progress_bar = st.progress(0)
results = []

for i, symbol in enumerate(symbols):
    progress_bar.progress((i + 1) / len(symbols), f"Analyzing {symbol}...")
    result = analyze_stock(symbol, analysis_date)
    if result:
        results.append(result)

# Create results DataFrame
if results:
    df = pd.DataFrame(results)
    
    # Apply BTST criteria
    btst_criteria = (
        (df['% Price Change'] >= 2) &
        (df['Volume Spike'] >= 2) &
        (df['% Close Near High'] >= 70) &
        (df['Close > Prev High'] == True) &
        (idx_pct_change >= 0)
    )
    
    btst_stocks = df[btst_criteria]
    
    # Display results
    st.divider()
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Market Summary")
        st.metric("NSE Index (^NSEI)", f"{idx_close:.2f}", f"{idx_pct_change:.2f}%")
        st.metric("Analysis Date", analysis_date.strftime("%Y-%m-%d"))
        st.metric("Total Stocks Analyzed", len(symbols))
        st.metric("BTST Candidates Found", len(btst_stocks))
        
        st.subheader("Scan Criteria")
        st.markdown("""
        - % Price Change ≥ 2%
        - Volume Spike ≥ 2x
        - % Close Near High ≥ 70%
        - Close > Previous Day High
        - Market Index Positive
        """)
    
    with col2:
        st.subheader("BTST Candidates")
        if not btst_stocks.empty:
            # Format columns
            format_dict = {
                'Open': '{:.2f}',
                'High': '{:.2f}',
                'Low': '{:.2f}',
                'Close': '{:.2f}',
                'Volume': '{:,.0f}',
                'Avg Volume (10D)': '{:,.0f}',
                '% Price Change': '{:.2f}%',
                '% Close Near High': '{:.2f}%',
                'Volume Spike': '{:.2f}x',
                'Intraday Range %': '{:.2f}%',
                'RSI (14)': '{:.2f}',
                'MACD': '{:.4f}',
                'MACD Signal': '{:.4f}',
                'BB Upper': '{:.2f}',
                'BB Middle': '{:.2f}',
                'BB Lower': '{:.2f}'
            }
            
            # Apply formatting
            for col, fmt in format_dict.items():
                if col in btst_stocks.columns:
                    btst_stocks[col] = btst_stocks[col].apply(lambda x: fmt.format(x) if not pd.isna(x) else '')
            
            st.dataframe(btst_stocks, height=500, use_container_width=True)
            
            # Export button
            csv = btst_stocks.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Export BTST Candidates",
                data=csv,
                file_name=f"btst_candidates_{selected_date}.csv",
                mime='text/csv'
            )
        else:
            st.info("No stocks matching BTST criteria found")
        
        st.subheader("All Stocks Analyzed")
        st.dataframe(df, height=300, use_container_width=True)
else:
    st.warning("No analysis results available. Check your stock symbols and date selection.")

# Add footer
st.divider()
st.caption("BTST Scanner v1.0 | Data from Yahoo Finance | Analysis as of " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
