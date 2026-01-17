# EDA Checklist (DVK)

Use this as a consistent exploratory analysis flow before writing conclusions.

## 1) Context
| Item | Notes |
|------|------|
| Device / FW | model, firmware version, build hash |
| Test conditions | temperature, power, fixture, sampling rate |
| Data source | `data/processed/{device_id}/decoded.*` |

## 2) Ingest & Schema
| Check | What to do |
|------|------------|
| File format | detect `parquet/csv/json` |
| Column types | enforce numeric/time columns |
| Units | verify `unit` metadata if present |

## 3) Data Quality
| Check | What to do |
|------|------------|
| Missing values | % missing per column; decide drop/fill |
| Duplicates | duplicate rows and duplicate timestamps |
| Outliers | robust z-score / IQR; tag not delete by default |
| Integrity | monotonic time, sequence gaps, drop-rate |

## 4) Distributions
| Plot/Stat | Notes |
|-----------|------|
| Hist/KDE | per key metric |
| Box/Violin | compare groups / modes |
| Summary stats | mean/std/min/max/percentiles |

## 5) Time Series
| Plot/Stat | Notes |
|-----------|------|
| Trend | rolling mean/median |
| Noise | rolling std / Allan variance (if needed) |
| Drift | temperature/time vs metric |
| Events | change-point markers (optional) |

## 6) Relationships
| Plot/Stat | Notes |
|-----------|------|
| Scatter | metric vs strength/temp/etc |
| Correlation | pearson/spearman with caution |
| Residuals | if fitting a model |

## 7) Outputs
| Artifact | Path |
|----------|------|
| Cleaned dataset | `data/processed/{device_id}/cleaned.*` |
| Figures | `reports/{device_id}/analysis/figures/` |
| Notebook | `reports/{device_id}/analysis/notebooks/` |
| Summary | `reports/{device_id}/analysis/summary.md` |

