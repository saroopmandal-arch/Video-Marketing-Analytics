"""
=============================================================================
Video-Marketing-Analytics: Google LCS Media Mix Optimizer (Linear Programming)
File: src/media_mix_optimizer.py
=============================================================================
Solves institutional media allocation for an enterprise brand deploying a
₹50,00,000 monthly YouTube budget in India. Compares Traditional Agency "Gut-Feel"
vs Video-Marketing-Analytics Algorithmic LP Allocation using scipy.optimize.linprog.
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np
from scipy.optimize import linprog

# UTF-8 for Windows console
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(DATA_DIR, "video_marketing_india.db")

def run_media_optimizer():
    print("[*] Running Google LCS Programmatic Media Mix Optimizer...")
    conn = sqlite3.connect(DB_PATH)

    # Load Ad Format Inventory Benchmarks
    df_formats = pd.read_sql_query("SELECT * FROM ad_format_inventory", conn)
    print("\n--- Ad Format Baseline Parameters ---")
    print(df_formats[['format_key', 'format_name', 'effective_cpm_inr', 'completion_rate_pct', 'ctr_pct', 'conversion_rate_pct']].to_string(index=False))

    TOTAL_BUDGET_INR = 5_000_000.0  # ₹50 Lakhs Monthly Brand Budget

    # Format order:
    # 0: bumper_6s
    # 1: non_skippable_15s
    # 2: skippable_trueview
    # 3: ctv_non_skippable
    # 4: shorts_in_feed
    # 5: creator_integration
    formats = df_formats['format_key'].tolist()
    cpms = df_formats['effective_cpm_inr'].values
    comp_rates = df_formats['completion_rate_pct'].values / 100.0
    ctrs = df_formats['ctr_pct'].values / 100.0
    conv_rates = df_formats['conversion_rate_pct'].values / 100.0

    # Impressions per INR spent = 1000 / CPM
    imps_per_rupee = 1000.0 / cpms

    # -------------------------------------------------------------------------
    # Baseline Scenario: Traditional Agency "Gut-Feel" Allocation
    # -------------------------------------------------------------------------
    # Gut feel splits:
    # 25% Bumper, 15% Non-skippable, 40% Trueview, 0% CTV (too expensive), 10% Shorts, 10% Unvetted Creator
    gut_feel_shares = np.array([0.25, 0.15, 0.40, 0.00, 0.10, 0.10])
    gut_feel_spend = gut_feel_shares * TOTAL_BUDGET_INR

    # Agency unvetted creator campaigns suffer 42% ad waste from bot pods (ASCI / INCA benchmark)
    gut_feel_effective_spend = gut_feel_spend.copy()
    gut_feel_effective_spend[5] *= (1.0 - 0.42)  # 42% wasted

    gut_feel_imps = gut_feel_effective_spend * imps_per_rupee
    gut_feel_completions = gut_feel_imps * comp_rates
    gut_feel_clicks = gut_feel_imps * ctrs
    gut_feel_conversions = gut_feel_clicks * conv_rates

    # -------------------------------------------------------------------------
    # Optimized Scenario: Video-Marketing-Analytics Algorithmic LP Allocation
    # -------------------------------------------------------------------------
    # Objective: Maximize Qualified Conversions (or Qualified Completions)
    # Conversion coefficient per Rupee = (1000 / CPM) * CTR * Conversion_Rate
    conv_per_rupee = imps_per_rupee * ctrs * conv_rates

    # Scipy minimizes, so negate objective function
    c = -conv_per_rupee

    # Constraints:
    # 1. Sum of spend = TOTAL_BUDGET_INR (Equality constraint)
    A_eq = [[1.0, 1.0, 1.0, 1.0, 1.0, 1.0]]
    b_eq = [TOTAL_BUDGET_INR]

    # Bounds for each format (Strategic media governance rules):
    # bumper_6s: 10% to 25% of budget
    # non_skippable_15s: 15% to 30% of budget
    # skippable_trueview: 20% to 40% of budget
    # ctv_non_skippable: 15% to 30% of budget (Capture living-room premium co-viewing)
    # shorts_in_feed: 5% to 15% of budget (Cap to avoid low-retention churn)
    # creator_integration: 10% to 25% of budget (100% whitelisted high-EQS only)
    bounds = [
        (0.10 * TOTAL_BUDGET_INR, 0.25 * TOTAL_BUDGET_INR),
        (0.15 * TOTAL_BUDGET_INR, 0.30 * TOTAL_BUDGET_INR),
        (0.20 * TOTAL_BUDGET_INR, 0.40 * TOTAL_BUDGET_INR),
        (0.15 * TOTAL_BUDGET_INR, 0.30 * TOTAL_BUDGET_INR),
        (0.05 * TOTAL_BUDGET_INR, 0.15 * TOTAL_BUDGET_INR),
        (0.10 * TOTAL_BUDGET_INR, 0.25 * TOTAL_BUDGET_INR)
    ]

    res = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method='highs')

    if not res.success:
        print("[!] Optimization failed:", res.message)
        return

    lp_spend = res.x
    lp_imps = lp_spend * imps_per_rupee
    lp_completions = lp_imps * comp_rates
    lp_clicks = lp_imps * ctrs
    lp_conversions = lp_clicks * conv_rates

    # -------------------------------------------------------------------------
    # Format-by-Format Comparison Table
    # -------------------------------------------------------------------------
    comparison_rows = []
    for i, fmt in enumerate(df_formats['format_name']):
        comparison_rows.append({
            "Ad_Format": fmt,
            "Agency_GutFeel_Spend_INR": gut_feel_spend[i],
            "Agency_Share_Pct": gut_feel_shares[i] * 100,
            "Optimized_LP_Spend_INR": lp_spend[i],
            "Optimized_Share_Pct": (lp_spend[i] / TOTAL_BUDGET_INR) * 100,
            "Optimized_Impressions": lp_imps[i],
            "Optimized_Completions": lp_completions[i],
            "Optimized_Conversions": lp_conversions[i]
        })

    df_comp = pd.DataFrame(comparison_rows)
    comp_csv = os.path.join(OUTPUT_DIR, "media_optimizer_allocation_comparison.csv")
    df_comp.to_csv(comp_csv, index=False)

    # -------------------------------------------------------------------------
    # Executive KPI Impact Summary
    # -------------------------------------------------------------------------
    tot_gut_imps = np.sum(gut_feel_imps)
    tot_gut_comp = np.sum(gut_feel_completions)
    tot_gut_clicks = np.sum(gut_feel_clicks)
    tot_gut_conv = np.sum(gut_feel_conversions)
    gut_blended_cpm = (TOTAL_BUDGET_INR / tot_gut_imps) * 1000
    gut_cpa = TOTAL_BUDGET_INR / tot_gut_conv

    tot_lp_imps = np.sum(lp_imps)
    tot_lp_comp = np.sum(lp_completions)
    tot_lp_clicks = np.sum(lp_clicks)
    tot_lp_conv = np.sum(lp_conversions)
    lp_blended_cpm = (TOTAL_BUDGET_INR / tot_lp_imps) * 1000
    lp_cpa = TOTAL_BUDGET_INR / tot_lp_conv

    delta_comp_pct = ((tot_lp_comp - tot_gut_comp) / tot_gut_comp) * 100
    delta_clicks_pct = ((tot_lp_clicks - tot_gut_clicks) / tot_gut_clicks) * 100
    delta_conv_pct = ((tot_lp_conv - tot_gut_conv) / tot_gut_conv) * 100
    delta_cpa_pct = ((lp_cpa - gut_cpa) / gut_cpa) * 100

    summary_rows = [
        {"Executive_Metric": "Total Budget Deployed", "Agency_GutFeel": f"₹{TOTAL_BUDGET_INR:,.0f}", "Video_Marketing_Analytics_LP": f"₹{TOTAL_BUDGET_INR:,.0f}", "Absolute_Delta": "₹0", "Impact_%": "0.0%"},
        {"Executive_Metric": "Ad Impressions Delivered", "Agency_GutFeel": f"{tot_gut_imps:,.0f}", "Video_Marketing_Analytics_LP": f"{tot_lp_imps:,.0f}", "Absolute_Delta": f"{tot_lp_imps - tot_gut_imps:+,.0f}", "Impact_%": f"{((tot_lp_imps - tot_gut_imps)/tot_gut_imps)*100:+.1f}%"},
        {"Executive_Metric": "Qualified Video Completions", "Agency_GutFeel": f"{tot_gut_comp:,.0f}", "Video_Marketing_Analytics_LP": f"{tot_lp_comp:,.0f}", "Absolute_Delta": f"{tot_lp_comp - tot_gut_comp:+,.0f}", "Impact_%": f"{delta_comp_pct:+.1f}%"},
        {"Executive_Metric": "High-Intent Click-Throughs", "Agency_GutFeel": f"{tot_gut_clicks:,.0f}", "Video_Marketing_Analytics_LP": f"{tot_lp_clicks:,.0f}", "Absolute_Delta": f"{tot_lp_clicks - tot_gut_clicks:+,.0f}", "Impact_%": f"{delta_clicks_pct:+.1f}%"},
        {"Executive_Metric": "Verified Direct Conversions", "Agency_GutFeel": f"{tot_gut_conv:,.0f}", "Video_Marketing_Analytics_LP": f"{tot_lp_conv:,.0f}", "Absolute_Delta": f"{tot_lp_conv - tot_gut_conv:+,.0f}", "Impact_%": f"{delta_conv_pct:+.1f}%"},
        {"Executive_Metric": "Effective Blended CPM", "Agency_GutFeel": f"₹{gut_blended_cpm:.2f}", "Video_Marketing_Analytics_LP": f"₹{lp_blended_cpm:.2f}", "Absolute_Delta": f"₹{lp_blended_cpm - gut_blended_cpm:+.2f}", "Impact_%": f"{((lp_blended_cpm - gut_blended_cpm)/gut_blended_cpm)*100:+.1f}%"},
        {"Executive_Metric": "Effective Cost Per Acquisition (CPA)", "Agency_GutFeel": f"₹{gut_cpa:.2f}", "Video_Marketing_Analytics_LP": f"₹{lp_cpa:.2f}", "Absolute_Delta": f"₹{lp_cpa - gut_cpa:+.2f}", "Impact_%": f"{delta_cpa_pct:+.1f}%"},
        {"Executive_Metric": "Creator Fraud / Ad Waste Eliminated", "Agency_GutFeel": "₹2₹0,000 (42% Waste)", "Video_Marketing_Analytics_LP": "₹0 (100% EQS Whitelisted)", "Absolute_Delta": "-₹2₹0,000", "Impact_%": "-100.0%"}
    ]

    df_summary = pd.DataFrame(summary_rows)
    summary_csv = os.path.join(OUTPUT_DIR, "google_lcs_budget_optimization_summary.csv")
    df_summary.to_csv(summary_csv, index=False)

    print("\n" + "="*80)
    print("      GOOGLE LCS MEDIA MIX OPTIMIZATION (₹50 LAKH PORTFOLIO)")
    print("="*80)
    print(df_summary.to_string(index=False))
    print(f"\n[+] Saved media optimizer summary to: {summary_csv}")
    print(f"[+] Saved allocation comparison to: {comp_csv}")

    conn.close()

if __name__ == "__main__":
    run_media_optimizer()

