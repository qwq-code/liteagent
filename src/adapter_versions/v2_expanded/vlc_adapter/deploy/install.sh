#!/usr/bin/env bash
set -euo pipefail

payload_dir="${1:-/tmp/osworld-vlc-adapter-payload}"
install_dir="${HOME}/.local/share/osworld-vlc-adapter"
dependency_dir="${install_dir}/python-deps"
unit_dir="${HOME}/.config/systemd/user"
opencv_wheel="${payload_dir}/vlc_adapter/vendor/opencv_python_headless-4.11.0.86-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"

test -f "${payload_dir}/vlc_adapter/service.py"
test -f "${payload_dir}/vlc_adapter/deploy/osworld-vlc-adapter.service"
test -f "${opencv_wheel}"
for command in vlc ffmpeg ffprobe wmctrl gsettings xrandr python3 flock; do
  command -v "${command}"
done
/usr/bin/python3 -c 'import flask'

mkdir -p "${install_dir}" "${unit_dir}" "${HOME}/.config/vlc"
test -f "${HOME}/.config/vlc/vlcrc"
grep -Eq '^extraintf=.*http' "${HOME}/.config/vlc/vlcrc"
grep -Eq '^http-password=.+$' "${HOME}/.config/vlc/vlcrc"
rm -rf "${install_dir}/vlc_adapter"
cp -a "${payload_dir}/vlc_adapter" "${install_dir}/vlc_adapter"
rm -rf "${dependency_dir}"
/usr/bin/python3 -s -m pip install \
  --disable-pip-version-check \
  --no-input \
  --no-deps \
  --target "${dependency_dir}" \
  "${opencv_wheel}"
PYTHONNOUSERSITE=1 PYTHONPATH="${dependency_dir}" \
  /usr/bin/python3 -s -c 'import cv2; assert cv2.__version__ == "4.11.0"'

install -m 0644 \
  "${payload_dir}/vlc_adapter/deploy/osworld-vlc-adapter.service" \
  "${unit_dir}/osworld-vlc-adapter.service"

systemctl --user daemon-reload
systemctl --user enable osworld-vlc-adapter.service
systemctl --user restart osworld-vlc-adapter.service
