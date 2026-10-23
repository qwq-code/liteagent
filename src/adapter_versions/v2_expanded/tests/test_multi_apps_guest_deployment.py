from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from multi_apps_adapter.deploy_host import package_paths
from multi_apps_adapter.local_paths import (
    NON_ROOT_LOCAL_PATH_PATTERN as MULTI_APPS_NON_ROOT_LOCAL_PATH_PATTERN,
)
from multi_apps_adapter.local_paths import (
    is_protected_local_root as multi_apps_is_protected_local_root,
)
from os_adapter.local_paths import NON_ROOT_LOCAL_PATH_PATTERN
from os_adapter.local_paths import is_protected_local_root


@pytest.mark.parametrize(
    "value",
    ["/", "/.", "/..", "~/", "~/..", "/tmp/report.xlsx", "~/report.xlsx"],
)
def test_multi_apps_local_path_rules_match_os_adapter(value: str) -> None:
    assert MULTI_APPS_NON_ROOT_LOCAL_PATH_PATTERN == NON_ROOT_LOCAL_PATH_PATTERN
    assert bool(re.fullmatch(MULTI_APPS_NON_ROOT_LOCAL_PATH_PATTERN, value)) == bool(
        re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, value)
    )
    path = Path(value).expanduser()
    assert multi_apps_is_protected_local_root(path) == is_protected_local_root(path)


def test_local_path_schema_pattern_avoids_guided_regex_lookahead() -> None:
    assert "(?=" not in NON_ROOT_LOCAL_PATH_PATTERN
    assert "(?!" not in NON_ROOT_LOCAL_PATH_PATTERN
    assert re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, "/") is None
    assert re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, "~/") is None
    assert re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, "/..") is not None
    assert re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, "~/.") is not None


def test_packaged_service_imports_without_repository_sibling_packages(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    guest_root = tmp_path / "guest"
    for source in package_paths(root):
        destination = guest_root / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; "
                "sys.path.insert(0, sys.argv[1]); "
                "from multi_apps_adapter.service import create_app; "
                "app = create_app(); "
                "response = app.test_client().get('/health'); "
                "assert response.status_code == 200; "
                "assert response.get_json()['mode'] == 'strict_generic'"
            ),
            str(guest_root),
        ],
        cwd=guest_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
