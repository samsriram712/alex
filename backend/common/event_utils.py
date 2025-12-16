from common.events import EventSeverity


EVENT_TO_ALERT_SEVERITY = {
    "info": "info",
    "low": "warning",
    "medium": "warning",
    "high": "critical",
    "critical": "critical",
}


def map_event_severity_to_alert(severity: EventSeverity) -> str:
    mapped = EVENT_TO_ALERT_SEVERITY.get(severity)
    if not mapped:
        print(f"[WARN] Unknown event severity: {severity}, defaulting to warning")
        return "warning"
    return mapped
