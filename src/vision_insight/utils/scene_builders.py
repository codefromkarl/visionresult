"""Builders for SceneAnalysis and DetectedObject from parsed LLM JSON dicts."""

from vision_insight.models.schemas import (
    DetectedObject,
    LocationGuess,
    PeopleInfo,
    SceneAnalysis,
    TimeGuess,
)


def build_scene_analysis(data: dict) -> SceneAnalysis:
    """Build SceneAnalysis from parsed JSON dict."""
    location = None
    if lg := data.get("location_guess"):
        location = LocationGuess(
            location=lg.get("location", ""),
            confidence=float(lg.get("confidence", 0.0)),
            evidence=lg.get("evidence", []),
        )

    time = None
    if tg := data.get("time_guess"):
        time = TimeGuess(
            time_of_day=tg.get("time_of_day", ""),
            season=tg.get("season", ""),
            year_estimate=tg.get("year_estimate", ""),
            evidence=tg.get("evidence", []),
        )

    people = []
    for p in data.get("people", []):
        people.append(
            PeopleInfo(
                count=int(p.get("count", 0)),
                age_group=p.get("age_group", ""),
                activity=p.get("activity", ""),
            )
        )

    return SceneAnalysis(
        scene_type=data.get("scene_type", "unknown"),
        description=data.get("description", ""),
        location_guess=location,
        time_guess=time,
        people=people,
        key_evidence=data.get("key_evidence", []),
        uncertainties=data.get("uncertainties", []),
    )


def build_detected_object(item: dict) -> DetectedObject:
    """Build DetectedObject from parsed JSON dict."""
    return DetectedObject(
        label=item.get("label", ""),
        confidence=float(item.get("confidence", 0.0)),
        bbox=item.get("bbox"),
        category=item.get("category", ""),
    )
