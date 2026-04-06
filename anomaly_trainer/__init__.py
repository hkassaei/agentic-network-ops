"""Standalone anomaly model trainer for the VoNR network stack.

Generates realistic IMS traffic (SIP REGISTER, VoNR calls) on a healthy
network, collects metrics throughout, and trains a River HalfSpaceTrees
model that learns what "normal active traffic" looks like. The trained
model is persisted to disk and loaded by the chaos framework and v5 RCA
pipeline at runtime.

Usage:
    python -m anomaly_trainer --duration 300
"""
