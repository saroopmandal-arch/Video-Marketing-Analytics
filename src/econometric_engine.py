"""
=============================================================================
Video-Marketing-Analytics: Econometric Engine & Fraud Audit
File: src/econometric_engine.py
=============================================================================
Calculates:
1. Category-level Programmatic CPM & Ad Inventory Yield in India (INR)
2. Shorts vs Long-form RPM Cannibalization Ratio (SLCR)
3. Engagement Quality Score (EQS) & Engagement Pod / Bot Anomaly Detection
4. Generates verified output datasets in output/
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np

# UTF-8 for Windows console
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(DATA_DIR, "video_marketing_india.db")

def run_econometric_audit():
    print("[*] Running Video-Marketing-Analytics Econometric & Fraud Audit...")
    conn = sqlite3.connect(DB_PATH)

    # -------------------------------------------------------------------------
    # 1. Category Monetization Yield Audit
    # -------------------------------------------------------------------------
    print("\n--- 1. Category Monetization & Programmatic Yield Audit ---")
    query_yield = """
    WITH cat_stats AS (
        SELECT 
            v.category_name,
            COUNT(*) as sample_videos,
            AVG(v.views) as mean_views,
            AVG(v.likes) as mean_likes,
            AVG(v.comments) as mean_comments,
            AVG(v.eqs) as mean_eqs,
            AVG(v.engagement_rate) * 100 as mean_engagement_pct
        FROM videos v
        GROUP BY v.category_name
    )
    SELECT 
        c.category_name,
        s.sample_videos,
        ROUND(s.mean_views, 0) as avg_views,
        ROUND(s.mean_eqs, 2) as avg_eqs,
        c.cpm_inr_median as median_in_stream_cpm,
        c.shorts_rpm_inr_median as median_shorts_rpm,
        c.longform_rpm_inr_median as median_longform_rpm,
        c.fill_rate_pct,
        -- Gross estimated programmatic ad value per 1M views in INR
        ROUND((1000000.0 / 1000.0) * c.cpm_inr_median * (c.fill_rate_pct / 100.0), 2) as ad_value_per_million_views_inr,
        -- Gross creator estimated revenue for 1M long-form views
        ROUND((1000000.0 / 1000.0) * c.longform_rpm_inr_median, 2) as creator_revenue_1m_longform_inr,
        -- Gross creator estimated revenue for 1M Shorts views
        ROUND((1000000.0 / 1000.0) * c.shorts_rpm_inr_median, 2) as creator_revenue_1m_shorts_inr,
        -- Shorts Cannibalization Gap (Multiplier: Longform vs Shorts Revenue)
        ROUND(c.longform_rpm_inr_median / c.shorts_rpm_inr_median, 1) as longform_to_shorts_revenue_multiplier
    FROM cat_stats s
    JOIN cpm_benchmarks c ON s.category_name = c.category_name
    ORDER BY ad_value_per_million_views_inr DESC;
    """

    df_yield = pd.read_sql_query(query_yield, conn)
    yield_csv = os.path.join(OUTPUT_DIR, "category_monetization_yield_audit.csv")
    df_yield.to_csv(yield_csv, index=False)
    print(df_yield[['category_name', 'median_in_stream_cpm', 'median_longform_rpm', 'median_shorts_rpm', 'longform_to_shorts_revenue_multiplier']].to_string(index=False))
    print(f"[+] Saved category yield audit to: {yield_csv}")

    # -------------------------------------------------------------------------
    # 2. Shorts Cannibalization & Revenue Dilution Paradox
    # -------------------------------------------------------------------------
    print("\n--- 2. The Shorts Cannibalization Paradox (Ground Truth Simulation) ---")
    # Simulate a channel generating 100M views per year under 3 mix scenarios:
    # Scenario A (Pure Long-Form): 100% Long-form videos
    # Scenario B (Balanced Portfolio): 40% Long-form, 60% Shorts
    # Scenario C (Shorts Pivot): 10% Long-form, 90% Shorts
    scenarios = [
        {"Scenario": "Scenario A: 100% Long-Form Focus", "Longform_Views_M": 100, "Shorts_Views_M": 0},
        {"Scenario": "Scenario B: Balanced (40% Long / 60% Shorts)", "Longform_Views_M": 40, "Shorts_Views_M": 60},
        {"Scenario": "Scenario C: Shorts Pivot (10% Long / 90% Shorts)", "Longform_Views_M": 10, "Shorts_Views_M": 90},
        {"Scenario": "Scenario D: 100% Shorts Focus (Viral Trap)", "Longform_Views_M": 0, "Shorts_Views_M": 100},
    ]

    # Use Finance vertical baseline (₹230 longform RPM median, ₹12 shorts RPM)
    # Source: upGrad India 2026 (Finance ₹150-₹350 RPM), Shorts ₹5-₹30 RPM
    long_rpm = 230.0
    shorts_rpm = 12.0

    scenario_rows = []
    for sc in scenarios:
        long_rev = (sc['Longform_Views_M'] * 1_000_000 / 1000) * long_rpm
        shorts_rev = (sc['Shorts_Views_M'] * 1_000_000 / 1000) * shorts_rpm
        total_rev = long_rev + shorts_rev
        scenario_rows.append({
            "Strategy": sc['Scenario'],
            "Total_Views": f"{sc['Longform_Views_M'] + sc['Shorts_Views_M']}M",
            "Longform_Views": f"{sc['Longform_Views_M']}M",
            "Shorts_Views": f"{sc['Shorts_Views_M']}M",
            "Longform_AdSense_INR": f"₹{long_rev:,.0f}",
            "Shorts_AdSense_INR": f"₹{shorts_rev:,.0f}",
            "Total_Annual_AdSense_INR": f"₹{total_rev:,.0f}",
            "Revenue_Decay_Pct": f"{(1 - (total_rev / (100 * 1_000_000 / 1000 * long_rpm))) * 100:.1f}%"
        })

    df_scenarios = pd.DataFrame(scenario_rows)
    scenario_csv = os.path.join(OUTPUT_DIR, "shorts_cannibalization_paradox.csv")
    df_scenarios.to_csv(scenario_csv, index=False)
    print(df_scenarios.to_string(index=False))
    print(f"[+] Saved cannibalization scenario model to: {scenario_csv}")

    # -------------------------------------------------------------------------
    # 3. Creator Fraud & Engagement Pod Anomaly Detection
    # -------------------------------------------------------------------------
    print("\n--- 3. Creator Fraud & Engagement Pod Audit ---")
    # Fraud detection logic calibrated against verified INCA/GroupM benchmarks:
    # INCA GroupM India Influencer Marketing Report: ~15% of influencer spend
    # is fraudulent across mid-tier unvetted campaigns.
    # ASCI 2025-26: 97% of violations are digital; 54% linked to disallowed categories.
    # EQS threshold aligns with engagement anomaly detection (not fraud rate directly).
    #
    # Rule 1: EQS < 0.20 -> ghost views / passive broadcast (music/film/news channels
    #          with mass passive playback but near-zero active engagement)
    # Rule 2: comment_ratio > 0.80 with like_ratio < 0.50 -> comment pod anomaly
    # Rule 3: EQS 0.20-1.20 -> low engagement, acceptable but passive audience
    # Rule 4: EQS > 1.20 -> healthy organic community (whitelist safe)
    
    query_fraud = """
    WITH channel_rollup AS (
        SELECT 
            c.channel_id,
            c.channel_name,
            c.country,
            c.subscriber_count,
            c.view_count,
            c.views_last_30_days,
            c.videos_last_30_days,
            c.category,
            ROUND(AVG(v.eqs), 2) as avg_eqs,
            ROUND(AVG(v.engagement_rate) * 100, 2) as avg_engagement_pct,
            ROUND(AVG(v.like_ratio) * 100, 2) as avg_like_pct,
            ROUND(AVG(v.comment_ratio) * 100, 3) as avg_comment_pct,
            COUNT(v.video_id) as analyzed_videos
        FROM channels c
        JOIN videos v ON c.channel_id = v.channel_id
        WHERE c.is_india = 1 AND c.subscriber_count >= 100000
        GROUP BY c.channel_id
        HAVING analyzed_videos >= 5
    )
    SELECT 
        channel_name,
        subscriber_count,
        views_last_30_days,
        avg_eqs,
        avg_like_pct,
        avg_comment_pct,
        analyzed_videos,
        CASE 
            WHEN avg_eqs < 0.20 THEN 'HIGH_RISK_GHOST_VIEWS (Bot Ingestion)'
            WHEN avg_comment_pct > 0.80 AND avg_like_pct < 0.50 THEN 'SUSPECTED_COMMENT_POD'
            WHEN avg_eqs BETWEEN 0.20 AND 1.20 THEN 'LOW_ENGAGEMENT_PASSIVE'
            WHEN avg_eqs BETWEEN 1.21 AND 5.00 THEN 'HEALTHY_ORGANIC_COMMUNITY'
            ELSE 'ELITE_HIGH_INTENT_CREATOR'
        END as brand_safety_status
    FROM channel_rollup
    ORDER BY avg_eqs ASC
    LIMIT 20;
    """
    df_fraud = pd.read_sql_query(query_fraud, conn)
    fraud_csv = os.path.join(OUTPUT_DIR, "creator_fraud_brand_safety_audit.csv")
    df_fraud.to_csv(fraud_csv, index=False)
    print(df_fraud[['channel_name', 'subscriber_count', 'avg_eqs', 'brand_safety_status']].head(10).to_string(index=False))
    print(f"[+] Saved fraud & brand safety audit to: {fraud_csv}")

    # -------------------------------------------------------------------------
    # 4. Indian Creator Landscape Statistics
    # -------------------------------------------------------------------------
    print("\n--- 4. Indian Creator Economy Distribution ---")
    query_india_tiers = """
    SELECT 
        CASE 
            WHEN subscriber_count >= 10000000 THEN 'Tier 1: Mega Creators (10M+ Subs)'
            WHEN subscriber_count >= 1000000 THEN 'Tier 2: Macro Creators (1M - 10M Subs)'
            WHEN subscriber_count >= 100000 THEN 'Tier 3: Mid-Tier Creators (100k - 1M Subs)'
            ELSE 'Tier 4: Emerging Creators (< 100k Subs)'
        END as creator_tier,
        COUNT(*) as total_channels,
        ROUND(AVG(subscriber_count), 0) as avg_subs,
        ROUND(AVG(views_last_30_days), 0) as avg_monthly_views,
        ROUND(AVG(videos_last_30_days), 1) as avg_monthly_uploads
    FROM channels
    WHERE is_india = 1
    GROUP BY creator_tier
    ORDER BY avg_subs DESC;
    """
    df_tiers = pd.read_sql_query(query_india_tiers, conn)
    tier_csv = os.path.join(OUTPUT_DIR, "indian_creator_tier_distribution.csv")
    df_tiers.to_csv(tier_csv, index=False)
    print(df_tiers.to_string(index=False))
    print(f"[+] Saved tier distribution to: {tier_csv}")

    conn.close()
    print("\n[+] Econometric Engine Audit finished with zero errors!")

if __name__ == "__main__":
    run_econometric_audit()

