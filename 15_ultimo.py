import io
import datetime
import streamlit as st
import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# --- SEITEN-KONFIGURATION ---
st.set_page_config(
    page_title="Monatsultimo Strategie",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Monatsultimo Strategie-Planer")
st.markdown("""
Dieses Tool berechnet die Ein- und Ausstiegstermine basierend auf den **Börsenhandelstagen der NYSE** 
für das nächste Jahr ab dem aktuellen Datum.

### 📜 Reglement & Handelslogik:
1. **Trading-Tage & Ausführung:** Einstieg **5 Handelstage vor Monatsende zum Handelsende**, Ausstieg **5 Handelstage nach Monatsende zum Handelsende**.
2. **Sommerpause:** In den Monaten **August** und **September** wird nicht gehandelt.
3. **200-Tage-Linien-Filter (Trend-Filter):** Ein Trade wird nur ausgeführt, wenn sich **alle 3 großen Indizes** 
   *(S&P 500, Nasdaq 100 und DAX 40)* aktuell **über ihrer 200-Tage-Linie (SMA 200)** befinden.
""")

st.divider()

# --- FUNKTION ZUR ABRUFUNG DER 200-TAGE-LINIEN (SMA 200) ---
@st.cache_data(ttl=3600, show_spinner=False)
def check_sma200_status():
    tickers = {
        "S&P 500": "^GSPC",
        "Nasdaq100": "^NDX",
        "Dax 40": "^GDAXI"
    }
    
    results = {}
    try:
        data = yf.download(list(tickers.values()), period="1y", interval="1d", progress=False)['Close']
        
        for name, ticker in tickers.items():
            if ticker in data.columns:
                series = data[ticker].dropna()
                if len(series) >= 200:
                    current_price = series.iloc[-1]
                    sma200 = series.rolling(window=200).mean().iloc[-1]
                    is_above = current_price > sma200
                    results[name] = "✔️" if is_above else "❌"
                else:
                    results[name] = "❓"
            else:
                results[name] = "❓"
    except Exception:
        for name in tickers.keys():
            results[name] = "❓"
            
    return results

# --- FUNKTION ZUR BERECHNUNG DER TRADING-TAGE ---
@st.cache_data(show_spinner=False)
def calculate_ultimo_dates(start_date, sma_status):
    try:
        cal = mcal.get_calendar('NYSE')
    except Exception:
        cal = mcal.get_calendar('NYSE')

    start_ts = pd.Timestamp(start_date)
    end_ts = start_ts + pd.DateOffset(years=1)
    
    buffer_start = start_ts - pd.Timedelta(days=45)
    buffer_end = end_ts + pd.Timedelta(days=45)
    
    trading_days = cal.valid_days(start_date=buffer_start, end_date=buffer_end)
    trading_days_list = [d.date() for d in trading_days]
    
    results = []
    
    current_dt = datetime.date(start_ts.year, start_ts.month, 1)
    end_dt = datetime.date(end_ts.year, end_ts.month, 1)

    all_sma_passed = all(status == "✔️" for status in sma_status.values())

    while current_dt <= end_dt:
        year = current_dt.year
        month = current_dt.month
        month_name = current_dt.strftime("%B %Y")
        
        is_current_month = (year == start_ts.year and month == start_ts.month)
        
        if month in [8, 9]:
            status_text = "⏸️ Keine Handelsaktivität (August/September)"
            sp_val = "-"
            ndx_val = "-"
            dax_val = "-"
        elif is_current_month:
            sp_val = sma_status.get("S&P 500", "❓")
            ndx_val = sma_status.get("Nasdaq100", "❓")
            dax_val = sma_status.get("Dax 40", "❓")
            
            if all_sma_passed:
                status_text = "✅ Handel aktiv"
            else:
                status_text = "🚫 Kein Handel (SMA 200 nicht erfüllt)"
        else:
            sp_val = "–"
            ndx_val = "–"
            dax_val = "–"
            status_text = "⏳ Ausstehend (Monat noch nicht erreicht)"

        month_trading_days = [d for d in trading_days_list if d.year == year and d.month == month]
        
        if len(month_trading_days) >= 5 and month not in [8, 9]:
            ultimo_day = month_trading_days[-1]
            ultimo_idx = trading_days_list.index(ultimo_day)
            entry_idx = ultimo_idx - 5
            exit_idx = ultimo_idx + 5
            
            if entry_idx >= 0 and exit_idx < len(trading_days_list):
                entry_date = trading_days_list[entry_idx]
                exit_date = trading_days_list[exit_idx]
                
                results.append({
                    "Jahr": year,
                    "Monat": month_name,
                    "Status": status_text,
                    "S&P 500": sp_val,
                    "Nasdaq100": ndx_val,
                    "Dax 40": dax_val,
                    "Einstiegsdatum": entry_date.strftime("%d.%m.%Y (%a)"),
                    "Ausstiegsdatum": exit_date.strftime("%d.%m.%Y (%a)"),
                    "Haltedauer (Handelstage)": 10
                })
        else:
            results.append({
                "Jahr": year,
                "Monat": month_name,
                "Status": status_text,
                "S&P 500": sp_val,
                "Nasdaq100": ndx_val,
                "Dax 40": dax_val,
                "Einstiegsdatum": "-",
                "Ausstiegsdatum": "-",
                "Haltedauer (Handelstage)": 0
            })
        
        if month == 12:
            current_dt = datetime.date(year + 1, 1, 1)
        else:
            current_dt = datetime.date(year, month + 1, 1)
            
    return pd.DataFrame(results)

# --- FUNKTION ZUR ERSTELLUNG DER PDF ---
def generate_pdf(df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = styles['Title']
    title_style.fontSize = 16
    title_style.leading = 20
    elements.append(Paragraph("Monatsultimo Strategie-Planer (NYSE)", title_style))
    
    sub_style = styles['Normal']
    sub_style.fontSize = 9
    sub_style.textColor = colors.HexColor("#555555")
    elements.append(Paragraph(f"Erstellt am: {datetime.date.today().strftime('%d.%m.%Y')} | Filter: SMA 200 für S&P 500, Nasdaq 100, Dax 40 | Ausführung zum Handelsende", sub_style))
    elements.append(Spacer(1, 12))
    
    table_data = [list(df.columns)]
    for record in df.to_dict('records'):
        table_data.append([str(v) if v is not None else "-" for v in record.values()])
    
    t = Table(table_data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- BERECHNUNG AUSFÜHREN ---
today = datetime.date.today()

with st.spinner("Prüfe 200-Tage-Linien & berechne Kalender..."):
    sma_status = check_sma200_status()
    df_results = calculate_ultimo_dates(today, sma_status)

# --- BENUTZEROBERFLÄCHE ---
active_trades = len(df_results[df_results["Status"] == "✅ Handel aktiv"])
paused_months = len(df_results[df_results["Status"] == "⏸️ Keine Handelsaktivität (August/September)"])

col1, col2, col3 = st.columns(3)
col1.metric("Berechneter Zeitraum", f"{today.strftime('%d.%m.%Y')} – {today.replace(year=today.year + 1).strftime('%d.%m.%Y')}")
col2.metric("Aktive Handelsmonate", f"{active_trades} Monate")
col3.metric("Pausierte Monate (Aug/Sep)", f"{paused_months} Monate")

st.divider()

show_paused = st.checkbox("Zeige auch pausierte Monate (August & September)", value=True)

if not show_paused:
    df_display = df_results[df_results["Status"] != "⏸️ Keine Handelsaktivität (August/September)"]
else:
    df_display = df_results

st.subheader("📅 Übersicht der Ein- und Ausstiegsdaten inkl. Trend-Filter")

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Jahr": st.column_config.NumberColumn(format="%d"),
        "Haltedauer (Handelstage)": st.column_config.NumberColumn(format="%d Tage")
    }
)

# PDF Generierung und Download Button
pdf_data = generate_pdf(df_display)

st.download_button(
    label="📄 Tabelle als PDF herunterladen",
    data=pdf_data,
    file_name=f"monatsultimo_termine_{today}.pdf",
    mime="application/pdf"
)
