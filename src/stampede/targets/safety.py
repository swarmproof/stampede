"""Target Safety Gate (⊕ FR-TA-05, NFR-SEC-01, ADR-6). Mandatory, on by default.

An adversarial + chaos swarm is a foot-gun; a *trust* brand cannot ship one that
silently hits production or mainnet. The gate runs **before** ``discover()`` and
fails closed: unless the target is on the allowlist (or the run carries an explicit
non-production acknowledgement), it refuses and prints exactly which flag is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch

from stampede.config import SafetyConfig
from stampede.targets.base import SafetyDescriptor


class SafetyViolation(Exception):
    """Raised when the gate blocks a run. Message names the required flag."""


@dataclass
class SafetyPosture:
    """Recorded onto the ``safety.gate`` span so the report shows the run's posture."""

    allowed: bool
    posture: str  # "allowlisted" | "acknowledged-non-production" | "evm-fork"
    endpoint: str
    reason: str = ""


class SafetyGate:
    def __init__(self, config: SafetyConfig) -> None:
        self.config = config

    def check(self, descriptor: SafetyDescriptor) -> SafetyPosture:
        endpoint = descriptor.endpoint

        # EVM: refuse a non-fork RPC unless the fork requirement is waived (ADR-6).
        if (
            descriptor.kind == "evm"
            and self.config.evm_require_fork
            and descriptor.evm_is_fork is not True
        ):
            raise SafetyViolation(
                f"EVMTarget refuses {endpoint!r}: it is not a detected fork. "
                "Point at an Anvil/Foundry fork, or set "
                "`safety.evm_require_fork: false` to override (dangerous)."
            )

        allowlisted = any(fnmatch(endpoint, pat) for pat in self.config.allow_targets)
        if allowlisted:
            return SafetyPosture(True, "allowlisted", endpoint)

        if self.config.acknowledge_non_production:
            return SafetyPosture(
                True,
                "acknowledged-non-production",
                endpoint,
                reason="off-allowlist target permitted by acknowledge_non_production",
            )

        # Blocked. Name the exact remediation (TEST-PLAN §4.4).
        raise SafetyViolation(
            f"Target {endpoint!r} is not on safety.allow_targets "
            f"({', '.join(self.config.allow_targets)}) and "
            "`safety.acknowledge_non_production` is false. Refusing to point the "
            "swarm at it. To proceed, either add it to safety.allow_targets or set "
            "`safety.acknowledge_non_production: true` (only for sandboxes you own)."
        )
