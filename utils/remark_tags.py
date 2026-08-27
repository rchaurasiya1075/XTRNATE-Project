"""Tag last-remark text for meeting analysis."""

import pandas as pd

TAG_RULES = [
    ("Vendor Change", ["vendor change", "change of vendor", "vendor changed", "new vendor", "lm vendor", "last mile vendor"]),
    ("ISP Change", ["isp change", "change of isp", "isp changed", "airtel to", "bsnl to", "switch isp"]),
    ("Migration", ["migration", "migrat", "link migration", "shifting", "media change", "fiber to air", "air to fiber"]),
    ("Feasibility", ["feasibility", "feasibl", "not feasible", "survey pending", "feasibility pending"]),
    ("Technical Issue", ["technical", "tech issue", "hardware", "configuration", "config issue", "device issue", "onu", "modem", "olt", "backend", "node isolation", "upstream"]),
    ("Fibre Cut", ["fibre cut", "fiber cut", "ofc cut", "cable cut"]),
    ("Power Issue", ["power outage", "power fail", "power issue", "no power", "electricity"]),
    ("Third Party", ["third party", "3rd party", "customer end", "bank end", "lan issue"]),
    ("Force Majeure", ["force maj", "rain", "flood", "landslide", "natural calamity", "storm"]),
    ("Pending Confirmation", ["confirmation pending", "link up confirmation", "customer confirmation"]),
    ("FE Visit", ["fe will visit", "fe visit", "visit at site", "engineer visit"]),
]


def tag_remark(text):
    t = str(text or "").lower()
    if not t or t in ("nan", "none", "--"):
        return ["Unclassified"]
    hits = [name for name, keys in TAG_RULES if any(k in t for k in keys)]
    return hits or ["Others"]


def primary_tag(text):
    tags = tag_remark(text)
    return tags[0]


def apply_tags(df, reason_col="reason"):
    out = df.copy()
    src = out[reason_col] if reason_col in out.columns else pd.Series("", index=out.index)
    out["remark_tag"] = src.apply(primary_tag)
    out["remark_tags"] = src.apply(lambda x: ", ".join(tag_remark(x)))
    return out


def dt_hrs(row):
    if "down_time_min" in row.index and pd.notna(row.get("down_time_min")):
        try:
            return round(float(row["down_time_min"]) / 60.0, 2)
        except Exception:
            pass
    if pd.notna(row.get("submitted_time")) and pd.notna(row.get("resolved_time")):
        try:
            return round((row["resolved_time"] - row["submitted_time"]).total_seconds() / 3600.0, 2)
        except Exception:
            return None
    return None
