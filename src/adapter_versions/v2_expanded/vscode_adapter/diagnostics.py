from __future__ import annotations

from typing import Final

from .errors import AdapterError


DIAGNOSTIC_SETTING_KEYS: Final[dict[str, dict[str, str]]] = {
    "python": {
        "general_type_issues": "reportGeneralTypeIssues",
        "incompatible_method_override": "reportIncompatibleMethodOverride",
        "missing_imports": "reportMissingImports",
        "missing_module_source": "reportMissingModuleSource",
        "optional_member_access": "reportOptionalMemberAccess",
        "undefined_variables": "reportUndefinedVariable",
        "unused_imports": "reportUnusedImport",
        "unused_variables": "reportUnusedVariable",
    }
}

DIAGNOSTIC_SEVERITIES: Final[frozenset[str]] = frozenset(
    {"error", "warning", "information", "none"}
)


def diagnostic_setting(
    language: str,
    diagnostic: str,
    severity: str,
) -> tuple[str, dict[str, object]]:
    language_settings = DIAGNOSTIC_SETTING_KEYS.get(language)
    if language_settings is None:
        raise AdapterError(
            "INVALID_REQUEST",
            "unsupported diagnostic language",
            {"language": language, "supported": sorted(DIAGNOSTIC_SETTING_KEYS)},
        )
    setting_key = language_settings.get(diagnostic)
    if setting_key is None:
        raise AdapterError(
            "INVALID_REQUEST",
            "unsupported diagnostic name",
            {"diagnostic": diagnostic, "supported": sorted(language_settings)},
        )
    if severity not in DIAGNOSTIC_SEVERITIES:
        raise AdapterError(
            "INVALID_REQUEST",
            "unsupported diagnostic severity",
            {"severity": severity, "supported": sorted(DIAGNOSTIC_SEVERITIES)},
        )
    return setting_key, {
        "python.analysis.diagnosticSeverityOverrides": {setting_key: severity}
    }
