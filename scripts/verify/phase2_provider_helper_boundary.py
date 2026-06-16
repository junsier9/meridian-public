from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import ExecutionLeaseError
from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import ProviderRequest


def main() -> int:
    provider = OfflineReplayCEXProvider(ROOT / "fixtures" / "snapshots")
    request = ProviderRequest(
        object_id="phase2-provider",
        object_type=ObjectType.ASSET,
        subject="AIX",
        scope="spot+perp",
        scenario="bullish_publish",
    )
    for fn in (provider.fetch, provider._load_snapshot):
        try:
            fn(request)
        except ExecutionLeaseError:
            continue
        raise AssertionError(f"provider boundary bypassed through {fn.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
