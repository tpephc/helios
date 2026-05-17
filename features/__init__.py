# features/__init__.py
"""Helios features layer — 從 raw data 計算各種特徵 (indicators / signals 的輸入).

v0.1.10 起步：dividend_adjustment.py (還原權息).
未來 (Step 3):
  - technical.py: MA / EMA / RSI / ATR / MACD / BB
  - regime.py:    bull / bear / neutral / crisis regime 偵測
  - flow.py:      法人籌碼 indicator
  - sector.py:    產業相對強弱 (用 sector_index_daily)
"""
