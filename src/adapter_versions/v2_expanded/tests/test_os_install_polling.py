import json
import subprocess
import sys

import pytest
from os_adapter import deploy_host


@pytest.mark.parametrize('exit_code', [0, 7])
def test_install_worker_records_real_exit_status_and_output(tmp_path, exit_code):
    result = subprocess.run([sys.executable, '-c', deploy_host.INSTALL_WORKER, str(tmp_path),
                             sys.executable, '-c', f'print("install evidence"); raise SystemExit({exit_code})'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path/'status.json').read_text())['returncode'] == exit_code
    assert 'install evidence' in (tmp_path/'install.log').read_text()


@pytest.mark.parametrize('exit_code', [0, 7])
def test_poll_waits_for_completion_and_propagates_failure(monkeypatch, exit_code):
    responses = iter([{}, {'output': json.dumps({'running': True})},
                      {'output': json.dumps({'returncode': exit_code, 'log': 'evidence'})}])
    commands = []
    def execute(url, command, **kwargs):
        commands.append(command)
        return next(responses)
    monkeypatch.setattr(deploy_host, 'execute', execute)
    monkeypatch.setattr(deploy_host.time, 'sleep', lambda _: None)
    if exit_code:
        with pytest.raises(RuntimeError, match='evidence'):
            deploy_host.install_payload('http://synthetic', ['bash', '/tmp/install.sh'])
    else:
        deploy_host.install_payload('http://synthetic', ['bash', '/tmp/install.sh'])
    assert len(commands) == 3
    assert commands[0][-2:] == ['bash', '/tmp/install.sh']
    assert commands[1][-1] == commands[2][-1] == commands[0][3]
