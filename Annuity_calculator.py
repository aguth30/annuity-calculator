"""
🧮 Generational Annuity Calculator — Streamlit Edition
──────────────────────────────────────────────────────
Beautiful web-based UI for annuity pricing.
Always looks for data files in the same folder as this script.
"""

import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import os
import sys

# ─────────────────────────────────────────────────────────────────────
# ALWAYS work from the folder where this script lives
# This is the key line that makes it portable!
# ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)


def data_file(filename: str) -> str:
    """Return full path to a file in the same folder as this script."""
    return os.path.join(SCRIPT_DIR, filename)


# ════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Annuity Calculator",
    page_icon="🧮",
    layout="wide",
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #003399;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .result-box {
        background: linear-gradient(135deg, #003399 0%, #0066cc 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        margin: 0.5rem 0;
    }
    .result-number {
        font-size: 2rem;
        font-weight: 700;
    }
    .result-label {
        font-size: 0.85rem;
        opacity: 0.85;
    }
    .info-card {
        background: #f0f4ff;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #003399;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# CORE CALCULATOR
# ════════════════════════════════════════════════════════════════════
class AnnuityCalculator:

    def __init__(self, mortality_file, experience_file=None,
                 gender_col="Gender", age_col="Age"):
        path = Path(mortality_file)
        if path.suffix.lower() == ".csv":
            self.table = pd.read_csv(path)
        else:
            self.table = pd.read_excel(path, sheet_name=0)
        self.table.columns = [str(c).strip() for c in self.table.columns]
        self.gender_col = gender_col
        self.age_col = age_col
        self.year_cols = [c for c in self.table.columns if str(c).isdigit()]
        self.min_year = min(int(c) for c in self.year_cols)
        self.max_year = max(int(c) for c in self.year_cols)
        self.max_age = int(self.table[self.age_col].max())
        self.exp_table = None
        if experience_file and os.path.exists(experience_file):
            self.exp_table = pd.read_csv(experience_file)
            self.exp_table.columns = [str(c).strip() for c in self.exp_table.columns]

    @staticmethod
    def load_cma_curve(file_path, currency="EUR", rate_type="spot"):
        raw = pd.read_excel(file_path, sheet_name=0, header=None)
        section_row = raw.iloc[0].apply(
            lambda x: str(x).strip() if pd.notna(x) else "")
        label_row = raw.iloc[1].apply(
            lambda x: str(x).strip() if pd.notna(x) else "")

        last_seen = ""
        section_filled = []
        for v in section_row:
            if v and v.lower() not in ("nan", ""):
                last_seen = v
            section_filled.append(last_seen)

        section_map = {
            "spot": "annually compounded spot rates",
            "forward": "1 year forward rates",
        }
        target = section_map.get(rate_type.lower(),
                                  "annually compounded spot rates")

        target_col = None
        for col_idx in range(len(raw.columns)):
            sec = section_filled[col_idx]
            lbl = label_row.iloc[col_idx]
            if target in sec.lower() and lbl.upper() == currency.upper():
                target_col = col_idx
                break

        if target_col is None:
            available = sorted({
                lbl for sec, lbl in zip(section_filled, label_row)
                if target in sec.lower()
                and lbl not in ("", "nan", "Term (Years)", "Term", "-")
                and not lbl.startswith("Unnamed")
            })
            raise ValueError(
                f"Currency '{currency}' not found.\nAvailable: {available}")

        data = raw.iloc[3:, target_col].dropna()
        rates = data.astype(float).values
        if len(rates) > 0 and rates[0] == 0:
            rates = rates[1:]
        return rates

    @staticmethod
    def list_cma_currencies(file_path, rate_type="spot"):
        raw = pd.read_excel(file_path, sheet_name=0, header=None)
        section_row = raw.iloc[0].apply(
            lambda x: str(x).strip() if pd.notna(x) else "")
        label_row = raw.iloc[1].apply(
            lambda x: str(x).strip() if pd.notna(x) else "")

        last_seen = ""
        section_filled = []
        for v in section_row:
            if v and v.lower() not in ("nan", ""):
                last_seen = v
            section_filled.append(last_seen)

        section_map = {
            "spot": "annually compounded spot rates",
            "forward": "1 year forward rates",
        }
        target = section_map.get(rate_type.lower(),
                                  "annually compounded spot rates")

        currencies = []
        for col_idx in range(len(raw.columns)):
            sec = section_filled[col_idx]
            lbl = label_row.iloc[col_idx]
            if (target in sec.lower()
                    and lbl not in ("", "nan", "Term (Years)", "Term", "-")
                    and not lbl.startswith("Unnamed")):
                if lbl not in currencies:
                    currencies.append(lbl)
        return currencies

    def _get_qx(self, age, gender, calendar_year, experience_factor):
        if age > self.max_age:
            return 1.0
        cal_year = max(self.min_year, min(calendar_year, self.max_year))
        row = self.table[
            (self.table[self.age_col] == age) &
            (self.table[self.gender_col].str.lower() == gender.lower())
        ]
        if row.empty:
            return 1.0
        if self.exp_table is not None:
            exp_row = self.exp_table[self.exp_table['Age'] == age]
            if len(exp_row) > 0 and gender in exp_row.columns:
                exp_f = float(exp_row[gender].iloc[0])
            else:
                exp_f = experience_factor
        else:
            exp_f = experience_factor
        q = float(row[str(cal_year)].iloc[0]) * exp_f
        return min(max(q, 0.0), 1.0)

    def price_annuity(self, age, gender, valuation_year, assets=1.0,
                      fixed_rate=None, yield_curve=None,
                      discount_factors=None,
                      deferral_to_age=None, annuity_due=True,
                      payments_per_year=1, pricing_spread=0.0,
                      experience_factor=1.0, max_age=121):

        n_years = max_age - age
        deferral_years = (deferral_to_age - age) if deferral_to_age else 0
        is_deferred = deferral_years > 0

        qx = np.zeros(n_years)
        for i in range(n_years):
            qx[i] = self._get_qx(age + i, gender, valuation_year + i,
                                  experience_factor)
        sx = np.zeros(n_years)
        sx[0] = 1.0
        for i in range(1, n_years):
            sx[i] = sx[i - 1] * (1 - qx[i - 1])
        LE = sx.sum() - 0.5

        if discount_factors is not None:
            df_raw = np.asarray(discount_factors, dtype=float)
            if len(df_raw) < n_years + 1:
                df_raw = np.concatenate(
                    [df_raw, np.full(n_years + 1 - len(df_raw), df_raw[-1])])
            df = df_raw[:n_years + 1]
        elif fixed_rate is not None:
            df = np.array([(1 + fixed_rate) ** -t
                           for t in range(n_years + 1)])
        else:
            yc = np.asarray(yield_curve, dtype=float)
            if len(yc) < n_years + 1:
                yc = np.concatenate(
                    [yc, np.full(n_years + 1 - len(yc), yc[-1])])
            df = np.zeros(n_years + 1)
            df[0] = 1.0
            for t in range(1, n_years + 1):
                r = yc[t - 1] if t - 1 < len(yc) else yc[-1]
                df[t] = (1 + r) ** -t

        spread_adj = np.array([(1 + pricing_spread) ** t
                               for t in range(n_years + 1)])
        price_df = df * spread_adj

        Dx = price_df[:n_years] * sx
        Nx = np.flipud(np.flipud(Dx).cumsum())
        ax = Nx[deferral_years] / Dx[0] if is_deferred else Nx[0] / Dx[0]
        if not annuity_due:
            ax -= 1.0

        m = payments_per_year
        if m > 1:
            adj = (m - 1) / (2 * m)
            ax_m = ax - adj if annuity_due else ax + adj
        else:
            ax_m = ax

        annual_income = assets / ax_m if ax_m > 0 else 0.0
        periodic_payment = annual_income / m

        if discount_factors is not None:
            discount_mode = f"Discount factor CSV ({len(df)} pts)"
        elif fixed_rate is not None:
            discount_mode = f"Single rate {fixed_rate:.4%}"
        else:
            yc_arr = np.asarray(yield_curve)
            discount_mode = (f"Yield curve ({len(yc_arr)} pts, "
                             f"avg {yc_arr.mean():.3%})")

        return {
            "ax": ax_m,
            "annual_income": annual_income,
            "periodic_payment": periodic_payment,
            "life_expectancy": LE,
            "annuity_type": "deferred" if is_deferred else "immediate",
            "deferral_years": deferral_years,
            "discount_mode": discount_mode,
            "sx": sx,
            "qx": qx,
        }


# ════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ════════════════════════════════════════════════════════════════════

# Header
st.markdown(
    '<div class="main-header">🧮 Generational Annuity Calculator</div>',
    unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Price annuities using generational mortality '
    'tables and market yield curves</div>',
    unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    st.subheader("📋 Mortality Table")
    mort_default = data_file("AG2024.csv")
    if os.path.exists(mort_default):
        st.success("✅ Found: AG2024.csv")
        mort_path = mort_default
    else:
        mort_upload = st.file_uploader(
            "Upload mortality table (CSV/Excel)",
            type=["csv", "xlsx", "xls"], key="mort")
        if mort_upload:
            mort_path = os.path.join(SCRIPT_DIR, mort_upload.name)
            with open(mort_path, "wb") as f:
                f.write(mort_upload.getbuffer())
            st.success(f"✅ Loaded: {mort_upload.name}")
        else:
            st.warning("⚠️ Place AG2024.csv in the same folder as this script")
            mort_path = None

    st.divider()

    st.subheader("📊 Experience Factors")
    exp_default = data_file("ExperienceFactorsByAge.csv")
    if os.path.exists(exp_default):
        st.success("✅ Found: ExperienceFactorsByAge.csv")
        exp_path = exp_default
    else:
        exp_upload = st.file_uploader(
            "Upload experience factors (CSV)",
            type=["csv"], key="exp")
        if exp_upload:
            exp_path = os.path.join(SCRIPT_DIR, exp_upload.name)
            with open(exp_path, "wb") as f:
                f.write(exp_upload.getbuffer())
            st.success(f"✅ Loaded: {exp_upload.name}")
        else:
            exp_path = None
    st.caption("Select 'From CSV (by age)' in Pricing Assumptions to use these factors")

    st.divider()

    st.subheader("📈 Yield Curve (CMA)")
    cma_default = data_file("CMA_Yields.xlsx")
    if os.path.exists(cma_default):
        st.success("✅ Found: CMA_Yields.xlsx")
        cma_path = cma_default
    else:
        cma_upload = st.file_uploader(
            "Upload CMA yields (Excel)",
            type=["xlsx", "xls"], key="cma")
        if cma_upload:
            cma_path = os.path.join(SCRIPT_DIR, cma_upload.name)
            with open(cma_path, "wb") as f:
                f.write(cma_upload.getbuffer())
            st.success(f"✅ Loaded: {cma_upload.name}")
        else:
            cma_path = None

    st.divider()
    st.caption(f"📂 Data folder:\n`{SCRIPT_DIR}`")

# ── Main content ──────────────────────────────────────────────────
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("👤 Client Details")
    c1a, c1b = st.columns(2)
    with c1a:
        age = st.number_input("Age", min_value=0, max_value=120, value=65)
        valuation_year = st.number_input("Valuation year", min_value=2000,
                                          max_value=2100, value=2026)
    with c1b:
        gender = st.selectbox("Gender", ["Male", "Female"])
        assets = st.number_input("Lump sum (€)", min_value=0.0,
                                  value=500_000.0, step=10_000.0,
                                  format="%.0f")

    st.subheader("📄 Annuity Structure")
    c2a, c2b = st.columns(2)
    with c2a:
        annuity_type = st.radio("Type", ["Immediate", "Deferred"],
                                 horizontal=True)
        if annuity_type == "Deferred":
            deferral_to_age = st.number_input(
                "Payments start at age",
                min_value=age + 1, max_value=120,
                value=min(age + 5, 120))
        else:
            deferral_to_age = None
    with c2b:
        payments_per_year = st.selectbox(
            "Payment frequency", [1, 2, 4, 12],
            format_func=lambda x: {
                1: "Annual", 2: "Semi-annual",
                4: "Quarterly", 12: "Monthly"}[x])
        timing = st.selectbox(
            "Payment timing",
            ["Start of period (due)", "End of period (immediate)"])
        annuity_due = timing.startswith("Start")

with col2:
    st.subheader("💰 Discounting")
    discount_mode = st.radio(
        "Discount mode",
        ["Single rate", "CMA yield curve", "Discount factor CSV", "Manual curve"],
        horizontal=True)

    fixed_rate, yield_curve = None, None

    if discount_mode == "Single rate":
        fixed_rate = st.number_input(
            "Discount rate", min_value=-0.05, max_value=0.20,
            value=0.025, step=0.001, format="%.4f")
        st.caption(f"= {fixed_rate * 100:.2f}%")

    elif discount_mode == "CMA yield curve":
        if cma_path:
            c3a, c3b = st.columns(2)
            with c3a:
                rate_type = st.selectbox(
                    "Rate type", ["spot", "forward"],
                    format_func=lambda x: {
                        "spot": "Spot (annually compounded)",
                        "forward": "1Y Forward"}[x])
            with c3b:
                try:
                    available = AnnuityCalculator.list_cma_currencies(
                        cma_path, rate_type)
                    currency = st.selectbox("Currency", available)
                except Exception as e:
                    st.error(f"Error reading CMA file: {e}")
                    currency = "EUR"
        else:
            st.warning("⚠️ No CMA file found. Place CMA_Yields.xlsx "
                       "in the same folder as this script.")

    elif discount_mode == "Discount factor CSV":
        df_csv_default = data_file("DiscountFactor.csv")
        if os.path.exists(df_csv_default):
            st.success("✅ Found: DiscountFactor.csv")
            df_csv_path = df_csv_default
        else:
            df_csv_upload = st.file_uploader(
                "Upload DiscountFactor.csv", type=["csv"], key="dfcsv")
            if df_csv_upload:
                df_csv_path = os.path.join(SCRIPT_DIR, df_csv_upload.name)
                with open(df_csv_path, "wb") as f:
                    f.write(df_csv_upload.getbuffer())
                st.success(f"✅ Loaded: {df_csv_upload.name}")
            else:
                df_csv_path = None
        st.caption("Uses pre-computed discount factors (e.g. from Smith-Wilson) "
                   "— matches MAIN.py exactly")

    else:  # Manual curve
        curve_input = st.text_area(
            "Enter rates (comma-separated)",
            value="0.005, 0.01, 0.015, 0.02, 0.025, 0.027, 0.028, 0.029, 0.03",
            height=80)

    st.subheader("🔧 Pricing Assumptions")
    c4a, c4b = st.columns(2)
    with c4a:
        pricing_spread = st.number_input(
            "Pricing spread (bps)", min_value=-100,
            max_value=500, value=0, step=1)
        pricing_spread_dec = pricing_spread / 10_000
    with c4b:
        exp_mode = st.radio(
            "Experience factors",
            ["Manual", "From CSV (by age)"],
            horizontal=True,
            disabled=exp_path is None,
            help="Use age-specific factors from ExperienceFactorsByAge.csv"
        )
        if exp_mode == "Manual" or exp_path is None:
            experience_factor = st.number_input(
                "Experience factor", min_value=0.1,
                max_value=3.0, value=1.0, step=0.05)
            use_exp_file = False
        else:
            use_exp_file = True
            experience_factor = 1.0
            if exp_path:
                exp_preview = pd.read_csv(exp_path)
                exp_preview.columns = [str(c).strip() for c in exp_preview.columns]
                age_row = exp_preview[exp_preview['Age'] == age]
                if not age_row.empty and gender in age_row.columns:
                    factor_val = float(age_row[gender].iloc[0])
                    st.info(f"Factor for age {age} ({gender}): **{factor_val:.3f}**")

# ── Calculate ─────────────────────────────────────────────────────
st.divider()

if st.button("🚀  Calculate Annuity", type="primary",
             use_container_width=True):

    if mort_path is None:
        st.error("❌ Please provide a mortality table (AG2024.csv).")
    else:
        try:
            calc = AnnuityCalculator(
                mort_path,
                experience_file=exp_path if use_exp_file else None)

            discount_factors_input = None
            if discount_mode == "Single rate":
                pass
            elif discount_mode == "CMA yield curve":
                yield_curve = list(AnnuityCalculator.load_cma_curve(
                    cma_path, currency, rate_type))
            elif discount_mode == "Discount factor CSV":
                if df_csv_path is None:
                    st.error("❌ Please provide a DiscountFactor.csv file.")
                    st.stop()
                df_data = pd.read_csv(df_csv_path)
                discount_factors_input = df_data.iloc[:, 0].values
            else:
                yield_curve = [float(r.strip())
                               for r in curve_input.split(",")
                               if r.strip()]

            res = calc.price_annuity(
                age=age, gender=gender,
                valuation_year=valuation_year,
                assets=assets,
                fixed_rate=fixed_rate,
                yield_curve=yield_curve,
                discount_factors=discount_factors_input,
                deferral_to_age=deferral_to_age,
                annuity_due=annuity_due,
                payments_per_year=payments_per_year,
                pricing_spread=pricing_spread_dec,
                experience_factor=experience_factor,
            )

            # Results
            st.markdown("---")
            st.subheader("📊 Results")

            r1, r2, r3, r4 = st.columns(4)
            with r1:
                st.metric("💰 Annual Income",
                          f"€ {res['annual_income']:,.0f}")
            with r2:
                if payments_per_year > 1:
                    pname = {2: "Semi-annual", 4: "Quarterly",
                             12: "Monthly"}[payments_per_year]
                    st.metric(f"💰 {pname} Payment",
                              f"€ {res['periodic_payment']:,.0f}")
                else:
                    st.metric("💰 Payment per year",
                              f"€ {res['annual_income']:,.0f}")
            with r3:
                st.metric("📐 Annuity Factor", f"{res['ax']:.4f}")
            with r4:
                st.metric("🕐 Life Expectancy",
                          f"{res['life_expectancy']:.1f} yrs")

            # Details
            with st.expander("📋 Full calculation details",
                             expanded=False):
                d1, d2 = st.columns(2)
                with d1:
                    st.markdown("**Inputs**")
                    st.write(f"- Client: {age}y {gender}")
                    st.write(f"- Valuation year: {valuation_year}")
                    st.write(f"- Lump sum: € {assets:,.0f}")
                    st.write(f"- Annuity type: {res['annuity_type']}")
                    if deferral_to_age:
                        st.write(f"- Deferral to age: {deferral_to_age}")
                    st.write(f"- Frequency: {payments_per_year}x/year")
                    st.write(f"- Timing: "
                             f"{'due' if annuity_due else 'immediate'}")
                with d2:
                    st.markdown("**Discounting**")
                    st.write(f"- Mode: {res['discount_mode']}")
                    st.write(f"- Pricing spread: {pricing_spread} bps")
                    st.write(f"- Experience factor: "
                             f"{experience_factor:.3f}")

            # Survival curve
            with st.expander("📈 Survival probability curve",
                             expanded=False):
                import plotly.graph_objects as go
                ages = list(range(age, age + len(res['sx'])))
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ages, y=res['sx'] * 100,
                    mode='lines', name='Survival %',
                    line=dict(color='#003399', width=2.5),
                    fill='tozeroy',
                    fillcolor='rgba(0, 51, 153, 0.1)'
                ))
                fig.update_layout(
                    title="Survival Probability",
                    xaxis_title="Age",
                    yaxis_title="Probability (%)",
                    yaxis_range=[0, 105],
                    template="plotly_white", height=350)
                st.plotly_chart(fig, use_container_width=True)

            # Yield curve
            if yield_curve is not None:
                with st.expander("📈 Yield curve used",
                                 expanded=False):
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scatter(
                        x=list(range(1, len(yield_curve) + 1)),
                        y=[r * 100 for r in yield_curve],
                        mode='lines+markers', name='Rate',
                        line=dict(color='#0066cc', width=2),
                        marker=dict(size=4)))
                    fig2.update_layout(
                        title=f"Yield Curve ({discount_mode})",
                        xaxis_title="Maturity (years)",
                        yaxis_title="Rate (%)",
                        template="plotly_white", height=350)
                    st.plotly_chart(fig2, use_container_width=True)

        except Exception as e:
            st.error(f"❌ Calculation error:\n\n{e}")

# Footer
st.markdown("---")
st.caption("🧮 Generational Annuity Calculator | Built for actuarial pricing "
           "| Uses generational mortality tables with market yield curves")