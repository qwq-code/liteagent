"""Strict OSWorld provider integration for the v2 Adapter stack."""

from .provider import AdapterDockerProvider, install_provider_patch
from .network_policy import install_agent_egress_policy, verify_agent_egress_policy

__all__ = [
    "AdapterDockerProvider",
    "install_agent_egress_policy",
    "install_provider_patch",
    "verify_agent_egress_policy",
]
