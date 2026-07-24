"""Built-in tool: get current date and time."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta


def get_current_time(timezone_offset: str = "") -> str:
    """Get the current date and time.

    Args:
        timezone_offset: Optional UTC offset like "+08:00" or "-05:00".
                        Returns UTC if not specified.
    """
    try:
        if timezone_offset:
            sign = 1 if timezone_offset[0] == "+" else -1
            parts = timezone_offset[1:].split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            offset = timedelta(hours=hours * sign, minutes=minutes * sign)
            tz = timezone(offset)
            now = datetime.now(tz)
        else:
            now = datetime.now(timezone.utc)

        return (
            f'{{"iso":"{now.isoformat()}","date":"{now.strftime("%Y-%m-%d")}",'
            f'"time":"{now.strftime("%H:%M:%S")}",'
            f'"weekday":"{now.strftime("%A")}"}}'
        )
    except Exception as exc:
        return f'{{"error":"{exc}"}}'


def _register_all(registry) -> None:
    """Register all built-in tools into the given ToolRegistry."""
    registry.register(
        name="get_current_time",
        fn=get_current_time,
        description="Get the current date and time. Returns ISO format, date, time, and weekday. "
        "Args: timezone_offset (optional, e.g. '+08:00' for CST, default UTC).",
        group="builtin",
        risk="safe",
        confirm="auto_allow",
        parameters={
            "timezone_offset": {
                "type": "string",
                "description": 'Optional. UTC offset like "+08:00" or "-05:00". Leave empty for UTC.',
            }
        },
    )
