"""
=============================================================================
Video-Marketing-Analytics: Machine Learning & Creator Quadrant Clustering
File: src/ml_creator_clustering.py
=============================================================================
Implements:
1. Unsupervised K-Means Clustering on 2,320 Indian Creator Channels
2. Creator Quadrant Segmentation (Velocity vs Volume vs Monetization)
3. Supervised Random Forest Classifier for Top-Decile Video Virality Prediction
4. Generates model metrics & audit CSVs in output/
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score, silhouette_score

# UTF-8 for Windows console
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(DATA_DIR, "video_marketing_india.db")

def run_ml_pipeline():
    print("[*] Running Video-Marketing-Analytics Machine Learning & Clustering Pipeline...")
    conn = sqlite3.connect(DB_PATH)

    # -------------------------------------------------------------------------
    # 1. Unsupervised Creator Quadrant Clustering (Indian Channels)
    # -------------------------------------------------------------------------
    print("\n--- 1. Clustering Indian Channels into Commercial Quadrants ---")
    query_channels = """
    SELECT 
        channel_id,
        channel_name,
        category,
        subscriber_count,
        view_count,
        views_last_30_days,
        videos_last_30_days,
        monthly_velocity_views_per_video
    FROM channels
    WHERE is_india = 1 AND subscriber_count > 1000 AND views_last_30_days > 0;
    """
    df_ch = pd.read_sql_query(query_channels, conn)
    print(f"[*] Analyzing {len(df_ch):,} qualified Indian channels...")

    # Log transformations for heavily skewed YouTube metrics
    df_ch['log_subs'] = np.log10(np.maximum(df_ch['subscriber_count'], 1))
    df_ch['log_views_30d'] = np.log10(np.maximum(df_ch['views_last_30_days'], 1))
    df_ch['log_velocity'] = np.log10(np.maximum(df_ch['monthly_velocity_views_per_video'], 1))
    df_ch['log_uploads_30d'] = np.log10(np.maximum(df_ch['videos_last_30_days'], 1))

    features = ['log_subs', 'log_views_30d', 'log_velocity', 'log_uploads_30d']
    X_ch = df_ch[features].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_ch)

    # K-Means with k=4
    k = 4
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    df_ch['cluster'] = kmeans.fit_predict(X_scaled)

    sil_score = silhouette_score(X_scaled, df_ch['cluster'])
    print(f"[+] K-Means Clustering converged. Silhouette Score: {sil_score:.4f}")

    # Analyze Cluster Profiles
    cluster_profiles = df_ch.groupby('cluster').agg(
        channel_count=('channel_id', 'count'),
        median_subs=('subscriber_count', 'median'),
        median_views_30d=('views_last_30_days', 'median'),
        median_uploads_30d=('videos_last_30_days', 'median'),
        median_velocity=('monthly_velocity_views_per_video', 'median')
    ).reset_index()

    # Assign Institutional Commercial Names
    # Order clusters by median velocity & subscriber profile
    def name_cluster(row):
        if row['median_subs'] > 5_000_000 and row['median_uploads_30d'] > 100:
            return "Mass Broadcast Networks"
        elif row['median_velocity'] > 200_000 and row['median_uploads_30d'] < 40:
            return "High-Intent Velocity Authorities"
        elif row['median_uploads_30d'] > 80:
            return "High-Frequency Shorts Churners"
        else:
            return "Emerging / Saturated Niche"

    cluster_profiles['commercial_segment'] = cluster_profiles.apply(name_cluster, axis=1)
    cluster_name_map = dict(zip(cluster_profiles['cluster'], cluster_profiles['commercial_segment']))
    df_ch['commercial_segment'] = df_ch['cluster'].map(cluster_name_map)

    print("\n--- Indian Creator Commercial Segments ---")
    print(cluster_profiles[['cluster', 'commercial_segment', 'channel_count', 'median_subs', 'median_views_30d', 'median_velocity']].to_string(index=False))

    ch_cluster_csv = os.path.join(OUTPUT_DIR, "indian_creator_cluster_segmentation.csv")
    df_ch.to_csv(ch_cluster_csv, index=False)
    print(f"[+] Saved channel cluster dataset to: {ch_cluster_csv}")

    # -------------------------------------------------------------------------
    # 2. Supervised Machine Learning: Predicting Top-Decile Viral Yield
    # -------------------------------------------------------------------------
    print("\n--- 2. Supervised ML: Predicting Top-Decile Commercial Video Velocity ---")
    # Sample 100k videos from SQLite for fast, robust training
    query_videos = """
    SELECT 
        category_id,
        category_name,
        views,
        likes,
        comments,
        dislikes,
        channel_subscribers,
        video_elapsed_hours,
        engagement_rate,
        like_ratio,
        comment_ratio,
        views_per_subscriber,
        views_per_hour,
        eqs
    FROM videos
    WHERE views > 100 AND video_elapsed_hours > 0
    LIMIT 100000;
    """
    df_v = pd.read_sql_query(query_videos, conn)
    print(f"[*] Training on {len(df_v):,} video observations...")

    # Define Target: Top 10% Virality Velocity (views_per_hour >= 90th percentile)
    threshold_velocity = df_v['views_per_hour'].quantile(0.90)
    df_v['is_high_velocity'] = (df_v['views_per_hour'] >= threshold_velocity).astype(int)
    print(f"[+] Top-decile velocity threshold: {threshold_velocity:.2f} views/hour (Target Class Prevalence: 10.0%)")

    # Features: Pre-velocity signals (category, subscriber scale, engagement ratios)
    # One-hot encode category
    cat_dummies = pd.get_dummies(df_v['category_name'], prefix='cat', drop_first=True)
    
    feature_cols = [
        'channel_subscribers', 'engagement_rate', 'like_ratio',
        'comment_ratio', 'views_per_subscriber', 'eqs'
    ]
    
    # Scale continuous features with log1p
    X_cont = np.log1p(np.maximum(df_v[feature_cols].values, 0))
    X_all = np.hstack([X_cont, cat_dummies.values])
    y_all = df_v['is_high_velocity'].values

    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=0.25, random_state=42, stratify=y_all
    )

    # Train Random Forest Classifier
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        min_samples_split=20,
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train, y_train)

    y_pred_proba = rf.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)
    auc_roc = roc_auc_score(y_test, y_pred_proba)

    print(f"[+] Random Forest Model Evaluated!")
    print(f"    * ROC-AUC Score: {auc_roc:.4f}")
    
    report_dict = classification_report(y_test, y_pred, output_dict=True)
    print(f"    * Precision (High Velocity): {report_dict['1']['precision']:.4f}")
    print(f"    * Recall (High Velocity):    {report_dict['1']['recall']:.4f}")
    print(f"    * F1-Score:                  {report_dict['1']['f1-score']:.4f}")

    # Feature Importances
    all_feature_names = feature_cols + list(cat_dummies.columns)
    importances = pd.DataFrame({
        'feature': all_feature_names,
        'importance': rf.feature_importances_
    }).sort_values(by='importance', ascending=False)

    print("\n--- Top 8 Feature Importances ---")
    print(importances.head(8).to_string(index=False))

    rf_csv = os.path.join(OUTPUT_DIR, "video_velocity_rf_feature_importances.csv")
    importances.to_csv(rf_csv, index=False)
    print(f"[+] Saved feature importances to: {rf_csv}")

    conn.close()
    print("\n[+] Machine Learning Pipeline completed successfully!")

if __name__ == "__main__":
    run_ml_pipeline()

