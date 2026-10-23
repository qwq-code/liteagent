from types import SimpleNamespace

import pytest

from integrations.openapa_osworld import provider


@pytest.mark.parametrize('override,expected', [(None, 180.0), ('240', 240.0)])
def test_cold_container_create_gets_setup_timeout_before_start(monkeypatch, tmp_path, override, expected):
    from desktop_env.providers.docker.provider import DockerProvider
    monkeypatch.delenv('OPENAPA_REUSE_DOCKER_CONTAINER', raising=False)
    monkeypatch.delenv('OPENAPA_DOCKER_REQUEST_TIMEOUT', raising=False)
    if override is not None:
        monkeypatch.setenv('OPENAPA_DOCKER_REQUEST_TIMEOUT', override)
    api = SimpleNamespace(timeout=60)
    calls = []
    container = object()

    def run(*args, **kwargs):
        calls.append(('create', api.timeout))
        # A simulated 90-second cold create must fit the setup allowance.
        if api.timeout < 90:
            raise TimeoutError('cold overlay creation')
        return container

    def init(self, region):
        self.client = SimpleNamespace(api=api, containers=SimpleNamespace(run=run))
        self.environment = {}
        self.lock_file = tmp_path / 'ports.lock'
        self.container = None

    monkeypatch.setattr(DockerProvider, '__init__', init)
    monkeypatch.setattr(provider, 'collect_used_host_ports', lambda client: set())
    monkeypatch.setattr(DockerProvider, '_wait_for_vm_ready', lambda self: calls.append(('ready', self.container)))
    monkeypatch.setattr(provider, 'install_agent_egress_policy', lambda c: {'verified': c is container})
    guest = provider.AdapterDockerProvider.create()
    guest.start_emulator(str(tmp_path / 'image.qcow2'), True, 'Ubuntu')
    assert calls == [('create', expected), ('ready', container)]
    assert guest.agent_egress_policy == {'verified': True}
