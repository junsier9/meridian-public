from __future__ import annotations

import asyncio


async def sleep_or_stop(stop_event: asyncio.Event, delay_seconds: float) -> None:
    if delay_seconds <= 0:
        await asyncio.sleep(0)
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=delay_seconds)
    except asyncio.TimeoutError:
        return

