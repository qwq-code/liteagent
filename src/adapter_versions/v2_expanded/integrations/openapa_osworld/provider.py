from __future__ import annotations

import os
import math
from collections.abc import Callable
from typing import Any

import psutil
from filelock import FileLock

from .network_policy import (
    install_agent_egress_policy,
    verify_agent_egress_policy,
)


ADAPTER_PORTS = {
    "libreoffice_calc": 8765,
    "libreoffice_impress": 8766,
    "chrome": 8767,
    "gimp": 8768,
    "os": 8769,
    "libreoffice_writer": 8770,
    "vs_code": 8771,
    "vlc": 8772,
    "thunderbird": 8773,
    "multi_apps": 8774,
}

SHARED_GUEST_PORTS = {
    "server": ("OSWORLD_CONTROL_PORT", 5020),
    "vnc": ("OSWORLD_VNC_PORT", 8020),
    "chromium": ("OSWORLD_CHROME_PORT", 9236),
    "vlc": ("OSWORLD_VLC_PORT", 8095),
    "libreoffice_calc": ("OSWORLD_CALC_PORT", 8905),
    "libreoffice_impress": ("OSWORLD_IMPRESS_PORT", 8906),
    "chrome": ("OSWORLD_CHROME_ADAPTER_PORT", 8907),
    "gimp": ("OSWORLD_GIMP_PORT", 8908),
    "os": ("OSWORLD_OS_PORT", 8909),
    "libreoffice_writer": ("OSWORLD_WRITER_PORT", 8910),
    "vs_code": ("OSWORLD_VSCODE_PORT", 8911),
    "vlc_adapter": ("OSWORLD_VLC_ADAPTER_PORT", 8912),
    "thunderbird": ("OSWORLD_THUNDERBIRD_PORT", 8913),
    "multi_apps": ("OSWORLD_MULTI_APPS_PORT", 8914),
}

RUN_OWNER_LABEL = "openapa.run_owner"
DEFAULT_PORT_LOCK_TIMEOUT = 180.0
DEFAULT_DOCKER_REQUEST_TIMEOUT = 180.0
VM_READINESS_ATTEMPTS = 2
USER_MODE_FORWARD_PORTS = (5000, 8080, 9222, *ADAPTER_PORTS.values())


def run_vm_readiness_attempts(
    start: Callable[[], None],
    wait_until_ready: Callable[[], None],
    cleanup: Callable[[], None],
) -> None:
    """Rebuild once when a fresh VM alone times out waiting for readiness."""

    for attempt in range(1, VM_READINESS_ATTEMPTS + 1):
        start()
        try:
            wait_until_ready()
        except TimeoutError:
            cleanup()
            if attempt == VM_READINESS_ATTEMPTS:
                raise
        else:
            return
    raise AssertionError("unreachable")


def collect_used_host_ports(client: Any) -> set[int]:
    system_ports: set[int] = set()
    for connection in psutil.net_connections(kind="inet"):
        local_address = getattr(connection, "laddr", None)
        port = getattr(local_address, "port", None)
        if port is None and isinstance(local_address, tuple) and len(local_address) > 1:
            port = local_address[1]
        if port is not None:
            system_ports.add(int(port))

    docker_ports: set[int] = set()
    for summary in client.api.containers(all=False):
        for mapping in summary.get("Ports") or []:
            public_port = mapping.get("PublicPort")
            if public_port is not None:
                docker_ports.add(int(public_port))
    return system_ports | docker_ports


class AdapterDockerProvider:
    """Factory wrapper installed after OSWorld is importable."""

    @staticmethod
    def create(region: str | None = None):
        from desktop_env.providers.docker.provider import DockerProvider

        class _Provider(DockerProvider):
            adapter_host_ports: dict[str, int]

            @staticmethod
            def _shared_guest_port(name: str) -> int:
                env_name, default = SHARED_GUEST_PORTS[name]
                return int(os.environ.get(env_name, str(default)))

            def _attach_shared_guest(self) -> None:
                name = os.environ["OPENAPA_REUSE_DOCKER_CONTAINER"]
                self.container = self.client.containers.get(name)
                self.container.reload()
                if self.container.status != "running":
                    raise RuntimeError(f"shared Docker guest {name!r} is not running")
                self.server_port = self._shared_guest_port("server")
                self.vnc_port = self._shared_guest_port("vnc")
                self.chromium_port = self._shared_guest_port("chromium")
                self.vlc_port = self._shared_guest_port("vlc")
                self.adapter_host_ports = {
                    adapter: self._shared_guest_port(adapter)
                    for adapter in ADAPTER_PORTS
                }
                self._owns_container = False

            def _get_used_ports(self) -> set[int]:
                return collect_used_host_ports(self.client)

            def start_emulator(self, path_to_vm: str, headless: bool, os_type: str):
                # Cold overlay creation can exceed the Docker SDK's 60-second
                # default before a VM even exists. This is host setup time,
                # independent of model requests and the agent episode budget.
                request_timeout = float(os.environ.get(
                    "OPENAPA_DOCKER_REQUEST_TIMEOUT", str(DEFAULT_DOCKER_REQUEST_TIMEOUT)
                ))
                if not math.isfinite(request_timeout) or request_timeout <= 0:
                    raise ValueError("OPENAPA_DOCKER_REQUEST_TIMEOUT must be positive and finite")
                self.client.api.timeout = request_timeout
                lock_timeout = float(
                    os.environ.get(
                        "OPENAPA_DOCKER_PORT_LOCK_TIMEOUT",
                        str(DEFAULT_PORT_LOCK_TIMEOUT),
                    )
                )
                self.adapter_host_ports = {}
                self.agent_egress_policy = {}
                self._owns_container = True

                if os.environ.get("OPENAPA_REUSE_DOCKER_CONTAINER"):
                    self._attach_shared_guest()
                    self._wait_for_vm_ready()
                    self.agent_egress_policy = install_agent_egress_policy(
                        self.container
                    )
                    return

                def start() -> None:
                    lock = FileLock(str(self.lock_file), timeout=lock_timeout)
                    with lock:
                        reserved_ports = self._get_used_ports()

                        def reserve(start: int) -> int:
                            port = start
                            while port in reserved_ports:
                                port += 1
                            if port >= 65354:
                                raise RuntimeError(f"no available port from {start}")
                            reserved_ports.add(port)
                            return port

                        self.vnc_port = reserve(8006)
                        self.server_port = reserve(5000)
                        self.chromium_port = reserve(9222)
                        self.vlc_port = reserve(8080)
                        self.adapter_host_ports = {
                            name: reserve(port) for name, port in ADAPTER_PORTS.items()
                        }

                        devices = []
                        if os.path.exists("/dev/kvm"):
                            devices.append("/dev/kvm")
                        else:
                            self.environment["KVM"] = "N"

                        port_bindings = {
                            8006: self.vnc_port,
                            5000: self.server_port,
                            9222: self.chromium_port,
                            8080: self.vlc_port,
                        }
                        port_bindings.update(
                            {
                                container_port: self.adapter_host_ports[name]
                                for name, container_port in ADAPTER_PORTS.items()
                            }
                        )
                        run_owner = os.environ.get("OPENAPA_RUN_OWNER")
                        self.environment.update(
                            {
                                "NETWORK": "user",
                                "USER_PORTS": ",".join(
                                    str(port) for port in USER_MODE_FORWARD_PORTS
                                ),
                            }
                        )
                        labels = {RUN_OWNER_LABEL: run_owner} if run_owner else None
                        self.container = self.client.containers.run(
                            "happysixd/osworld-docker",
                            environment=self.environment,
                            cap_add=["NET_ADMIN"],
                            devices=devices,
                            volumes={
                                os.path.abspath(path_to_vm): {
                                    "bind": "/System.qcow2",
                                    "mode": "ro",
                                }
                            },
                            ports=port_bindings,
                            labels=labels,
                            detach=True,
                        )

                def cleanup() -> None:
                    if self.container:
                        try:
                            self.container.stop()
                        except Exception:
                            pass
                        try:
                            self.container.remove(v=True, force=True)
                        except Exception:
                            pass
                    self.container = None
                    self.server_port = None
                    self.vnc_port = None
                    self.chromium_port = None
                    self.vlc_port = None
                    self.adapter_host_ports = {}
                    self.agent_egress_policy = {}

                try:
                    run_vm_readiness_attempts(
                        start,
                        lambda: self._wait_for_vm_ready(),
                        cleanup,
                    )
                    self.agent_egress_policy = install_agent_egress_policy(
                        self.container
                    )
                except Exception:
                    cleanup()
                    raise

            def adapter_urls(self) -> dict[str, str]:
                return {
                    name: f"http://127.0.0.1:{port}"
                    for name, port in self.adapter_host_ports.items()
                }

            def assert_agent_egress_policy(self) -> dict[str, Any]:
                if not self.container:
                    raise RuntimeError("OSWorld container is not running")
                self.agent_egress_policy = verify_agent_egress_policy(self.container)
                return dict(self.agent_egress_policy)

            def stop_emulator(self, path_to_vm: str, region=None, *args, **kwargs):
                if getattr(self, "_owns_container", True):
                    super().stop_emulator(path_to_vm, region, *args, **kwargs)
                else:
                    self.container = None
                    self.server_port = None
                    self.vnc_port = None
                    self.chromium_port = None
                    self.vlc_port = None
                self.adapter_host_ports = {}
                self.agent_egress_policy = {}

        return _Provider(region)


def install_provider_patch() -> None:
    from desktop_env import desktop_env as desktop_env_module
    from desktop_env.providers.docker.manager import DockerVMManager

    if hasattr(desktop_env_module, "_v2_original_provider_factory"):
        return
    original = desktop_env_module.create_vm_manager_and_provider
    desktop_env_module._v2_original_provider_factory = original

    def factory(provider_name: str, region: str | None, use_proxy: bool = False):
        if provider_name == "docker":
            return DockerVMManager(), AdapterDockerProvider.create(region)
        return original(provider_name, region, use_proxy=use_proxy)

    desktop_env_module.create_vm_manager_and_provider = factory
