import hashlib
import json
from statistics import fmean
from typing import Any


VITAL_KEYS = ["heart_rate", "systolic_bp", "respiratory_rate", "spo2", "temperature", "glucose"]
VITAL_RANGES = {
    "heart_rate": (50.0, 110.0, "bpm"),
    "systolic_bp": (90.0, 160.0, "mmHg"),
    "respiratory_rate": (10.0, 24.0, "/min"),
    "spo2": (94.0, 100.0, "%"),
    "temperature": (35.8, 38.0, "C"),
    "glucose": (70.0, 180.0, "mg/dL"),
}


def payload_size_kb(payload: Any) -> float:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return max(0.1, len(encoded) / 1024)


def pseudonymize(patient_id: str) -> str:
    return hashlib.sha256(patient_id.encode("utf-8")).hexdigest()[:12]


def validate_patient_record(patient: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ["patient_id", "age", "sex", "ward", "bed", "primary_diagnosis", "vitals"]
    for key in required:
        if key not in patient:
            errors.append(f"missing:{key}")

    vitals = patient.get("vitals", [])
    if not isinstance(vitals, list) or not vitals:
        errors.append("missing:vitals_series")
        return errors

    for index, sample in enumerate(vitals):
        for key in VITAL_KEYS:
            if key not in sample:
                errors.append(f"vitals[{index}].missing:{key}")
    return errors


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clean_vital_sample(sample: dict[str, Any]) -> dict[str, float]:
    return {
        "heart_rate": clamp(float(sample["heart_rate"]), 30, 220),
        "systolic_bp": clamp(float(sample["systolic_bp"]), 50, 260),
        "respiratory_rate": clamp(float(sample["respiratory_rate"]), 5, 60),
        "spo2": clamp(float(sample["spo2"]), 50, 100),
        "temperature": clamp(float(sample["temperature"]), 30, 43),
        "glucose": clamp(float(sample["glucose"]), 40, 500),
    }


def abnormal_vitals(sample: dict[str, Any]) -> list[dict[str, Any]]:
    cleaned = clean_vital_sample(sample)
    findings: list[dict[str, Any]] = []
    for key, (low, high, unit) in VITAL_RANGES.items():
        value = cleaned[key]
        if value < low or value > high:
            findings.append(
                {
                    "vital": key,
                    "value": value,
                    "unit": unit,
                    "normal_min": low,
                    "normal_max": high,
                    "direction": "low" if value < low else "high",
                }
            )
    return findings


def validation_summary(patient: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    vitals = patient.get("vitals", [])
    latest = vitals[-1] if isinstance(vitals, list) and vitals else {}
    return {
        "valid": not errors,
        "errors": errors,
        "vital_samples": len(vitals) if isinstance(vitals, list) else 0,
        "latest_timestamp": latest.get("timestamp", ""),
        "required_vitals": VITAL_KEYS,
    }


def alert_from_findings(findings: list[dict[str, Any]]) -> tuple[int, str, str]:
    if any(item["vital"] == "spo2" and item["value"] < 90 for item in findings):
        return 10, "critical", "Immediate physician review and continuous monitoring"
    if len(findings) >= 3:
        return 8, "high", "Nurse escalation and repeat vitals within 15 minutes"
    if findings:
        return 4, "medium", "Repeat vitals within 30 minutes and review treatment plan"
    return 0, "low", "Routine monitoring"


def wearable_alert_result(patient: dict[str, Any], vitals: list[dict[str, Any]]) -> dict[str, Any]:
    latest = clean_vital_sample(vitals[-1])
    findings = abnormal_vitals(vitals[-1])
    score, level, recommended = alert_from_findings(findings)
    return {
        "patient_id": patient["patient_id"],
        "patient_hash": pseudonymize(patient["patient_id"]),
        "ward": patient["ward"],
        "bed": patient["bed"],
        "age": patient["age"],
        "primary_diagnosis": patient["primary_diagnosis"],
        "risk_score": score,
        "risk_level": level,
        "component_scores": {
            "out_of_range_vitals": len(findings),
            "schema_validation": 0,
            "context": 0,
        },
        "features": {
            "latest": latest,
            "abnormal_vitals": findings,
        },
        "recommended_action": recommended,
        "abnormal_vitals": findings,
    }


def smooth_vitals(vitals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = [clean_vital_sample(sample) | {"timestamp": sample.get("timestamp", "")} for sample in vitals]
    smoothed: list[dict[str, Any]] = []

    for index, sample in enumerate(cleaned):
        window = cleaned[max(0, index - 1) : min(len(cleaned), index + 2)]
        smoothed_sample = {"timestamp": sample["timestamp"]}
        for key in VITAL_KEYS:
            smoothed_sample[key] = round(fmean(float(item[key]) for item in window), 2)
        smoothed.append(smoothed_sample)
    return smoothed


def extract_features(patient: dict[str, Any], vitals: list[dict[str, Any]]) -> dict[str, Any]:
    latest = clean_vital_sample(vitals[-1])
    first = clean_vital_sample(vitals[0])
    averages = {
        key: round(fmean(float(clean_vital_sample(sample)[key]) for sample in vitals), 2)
        for key in VITAL_KEYS
    }
    trends = {key: round(latest[key] - first[key], 2) for key in VITAL_KEYS}

    return {
        "age": patient["age"],
        "comorbidity_count": len(patient.get("comorbidities", [])),
        "medication_count": len(patient.get("medications", [])),
        "latest": latest,
        "averages": averages,
        "trends": trends,
    }


def vital_score(features: dict[str, Any]) -> int:
    latest = features["latest"]
    score = 0

    hr = latest["heart_rate"]
    if hr >= 130 or hr <= 40:
        score += 3
    elif hr >= 110 or hr <= 50:
        score += 2
    elif hr >= 95:
        score += 1

    sbp = latest["systolic_bp"]
    if sbp <= 90:
        score += 3
    elif sbp <= 100:
        score += 2
    elif sbp <= 110 or sbp >= 180:
        score += 1

    rr = latest["respiratory_rate"]
    if rr >= 30 or rr <= 8:
        score += 3
    elif rr >= 25:
        score += 2
    elif rr >= 21:
        score += 1

    spo2 = latest["spo2"]
    if spo2 <= 90:
        score += 3
    elif spo2 <= 93:
        score += 2
    elif spo2 <= 95:
        score += 1

    temp = latest["temperature"]
    if temp >= 39 or temp <= 35:
        score += 2
    elif temp >= 38 or temp < 36:
        score += 1

    glucose = latest["glucose"]
    if glucose >= 250 or glucose <= 60:
        score += 2
    elif glucose >= 180:
        score += 1

    return score


def trend_score(features: dict[str, Any]) -> int:
    trends = features["trends"]
    score = 0
    if trends["heart_rate"] >= 12:
        score += 1
    if trends["respiratory_rate"] >= 4:
        score += 1
    if trends["spo2"] <= -3:
        score += 1
    if trends["systolic_bp"] <= -12:
        score += 1
    if trends["temperature"] >= 0.7:
        score += 1
    return score


def context_score(patient: dict[str, Any], features: dict[str, Any]) -> int:
    score = 0
    if int(patient["age"]) >= 75:
        score += 1
    if features["comorbidity_count"] >= 3:
        score += 1
    high_risk_terms = {"sepsis", "pneumonia", "copd", "heart failure", "stroke"}
    diagnosis = str(patient.get("primary_diagnosis", "")).lower()
    if any(term in diagnosis for term in high_risk_terms):
        score += 1
    return score


def classify_risk(score: int) -> str:
    if score >= 10:
        return "critical"
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def recommended_action(risk_level: str) -> str:
    return {
        "critical": "Immediate physician review and continuous monitoring",
        "high": "Nurse escalation and repeat vitals within 15 minutes",
        "medium": "Repeat vitals within 30 minutes and review treatment plan",
        "low": "Routine monitoring",
    }[risk_level]


def compute_risk(patient: dict[str, Any], vitals: list[dict[str, Any]]) -> dict[str, Any]:
    features = extract_features(patient, vitals)
    component_scores = {
        "vitals": vital_score(features),
        "trend": trend_score(features),
        "context": context_score(patient, features),
    }
    total_score = sum(component_scores.values())
    risk_level = classify_risk(total_score)

    return {
        "patient_id": patient["patient_id"],
        "patient_hash": pseudonymize(patient["patient_id"]),
        "ward": patient["ward"],
        "bed": patient["bed"],
        "age": patient["age"],
        "primary_diagnosis": patient["primary_diagnosis"],
        "risk_score": total_score,
        "risk_level": risk_level,
        "component_scores": component_scores,
        "features": features,
        "recommended_action": recommended_action(risk_level),
    }


def cloud_pipeline_result(patient: dict[str, Any]) -> dict[str, Any]:
    validation_errors = validate_patient_record(patient)
    vitals = patient["vitals"]
    risk = wearable_alert_result(patient, vitals)
    return {
        "processing_mode": "cloud_wearable_alert_validation",
        "validation_errors": validation_errors,
        "validation": validation_summary(patient, validation_errors),
        "stored_payload": "full_patient_record",
        "stored_fields": [
            "demographics",
            "diagnosis",
            "comorbidities",
            "medications",
            "wearable_vital_timeseries",
            "out_of_range_alert",
        ],
        "risk": risk,
        "alert": bool(validation_errors) or bool(risk["abnormal_vitals"]),
        "clinical_payload": {
            "patient": patient,
            "risk": risk,
            "alert": bool(validation_errors) or bool(risk["abnormal_vitals"]),
        },
    }


def edge_pipeline_result(patient: dict[str, Any]) -> dict[str, Any]:
    validation_errors = validate_patient_record(patient)
    risk = wearable_alert_result(patient, patient["vitals"])
    edge_summary = {
        "patient_id": patient["patient_id"],
        "patient_hash": risk["patient_hash"],
        "ward": patient["ward"],
        "bed": patient["bed"],
        "latest_vitals": risk["features"]["latest"],
        "risk_score": risk["risk_score"],
        "risk_level": risk["risk_level"],
        "abnormal_vitals": risk["abnormal_vitals"],
        "recommended_action": risk["recommended_action"],
        "alert": bool(validation_errors) or bool(risk["abnormal_vitals"]),
    }
    return {
        "processing_mode": "edge_wearable_alert_validation",
        "validation_errors": validation_errors,
        "validation": validation_summary(patient, validation_errors),
        "local_steps": [
            "schema_validation",
            "wearable_sample_validation",
            "out_of_range_threshold_check",
            "local_alert_generation",
        ],
        "risk": risk,
        "alert": edge_summary["alert"],
        "clinical_payload": edge_summary,
    }
