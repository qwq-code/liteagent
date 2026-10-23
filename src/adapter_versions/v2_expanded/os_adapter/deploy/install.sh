#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-os-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-os-adapter"
unit_dir="${HOME}/.config/systemd/user"
pymupdf_wheel="${payload_dir}/os_adapter/vendor/pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl"

test -f "${payload_dir}/os_adapter/service.py"
test -f "${payload_dir}/os_adapter/actions.py"
test -f "${payload_dir}/os_adapter/vendor/pypdf-6.14.2-py3-none-any.whl"
test -f "${payload_dir}/os_adapter/vendor/typing_extensions-4.15.0-py3-none-any.whl"
test -f "${pymupdf_wheel}"
test -f "${payload_dir}/os_adapter/deploy/osworld-os-adapter.service"
for command in gio gsettings pactl timedatectl gnome-terminal gnome-screenshot wmctrl snap sudo useradd usermod openssl pdftocairo; do
  command -v "${command}"
done
/usr/bin/python3 -c 'import flask'

PYTHONPATH="${payload_dir}" /usr/bin/python3 -m os_adapter.desktop_dependencies \
  "${payload_dir}/os_adapter/vendor"

mkdir -p "${install_dir}" "${unit_dir}"
rm -rf "${install_dir}/os_adapter"
rm -rf "${install_dir}/pypdf" "${install_dir}"/pypdf-*.dist-info
rm -rf "${install_dir}/typing_extensions.py" "${install_dir}"/typing_extensions-*.dist-info
cp -a "${payload_dir}/os_adapter" "${install_dir}/os_adapter"
/usr/bin/python3 -m pip install \
  --disable-pip-version-check \
  --no-index \
  --no-deps \
  --upgrade \
  --target "${install_dir}" \
  "${payload_dir}/os_adapter/vendor/pypdf-6.14.2-py3-none-any.whl" \
  "${payload_dir}/os_adapter/vendor/typing_extensions-4.15.0-py3-none-any.whl" \
  "${pymupdf_wheel}"
install -m 0644 \
  "${payload_dir}/os_adapter/deploy/osworld-os-adapter.service" \
  "${unit_dir}/osworld-os-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-os-adapter.service
systemctl --user restart osworld-os-adapter.service
