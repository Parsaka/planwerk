"""Detection metrics exactly as pre-registered in ADR-0001 (Q2)."""

from __future__ import annotations

MISS_THRESHOLD = 0.98  # actual or forecast < 98 % of target = miss / flag


def flags(forecasts: list[float], target: float) -> list[bool]:
    return [f < MISS_THRESHOLD * target for f in forecasts]


def detection_month(flag_list: list[bool]) -> int:
    """First month m from which the flag stays on for every later month; 13 if never."""
    det = 13
    for m in range(len(flag_list), 0, -1):
        if flag_list[m - 1]:
            det = m
        else:
            break
    return det


def false_alarm(flag_list: list[bool]) -> bool:
    """A stable flag at some month <= 11 in a scenario without a miss."""
    return detection_month(flag_list[:11]) <= 11 if any(flag_list[:11]) else False
