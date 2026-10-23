from pathlib import Path

from chrome_adapter import deploy_host


def test_chrome_deploy_packages_offline_pychrome_dependencies() -> None:
    root = Path(__file__).parents[1]
    vendor = root / "chrome_adapter" / "vendor"
    wheels = set(vendor.glob("*.whl"))

    assert any(path.name.startswith("pychrome-0.2.4-") for path in wheels)
    assert wheels.issubset(set(deploy_host.source_files(root)))
    assert len(wheels) >= 3


def test_chrome_install_uses_packaged_wheels_only() -> None:
    script = (
        Path(__file__).parents[1] / "chrome_adapter" / "deploy" / "install.sh"
    ).read_text(encoding="utf-8")

    assert "--no-index" in script
    assert '--find-links "${payload_dir}/chrome_adapter/vendor"' in script
    assert "'pychrome==0.2.4'" in script
