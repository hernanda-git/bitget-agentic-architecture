import json

import pytest

from src.policy.kill_switch import KillSwitch


def test_missing_or_corrupt_state_fails_active(tmp_path):
    switch = KillSwitch(tmp_path / "kill.json")
    assert switch.is_active() is True
    switch.path.write_text("bad")
    assert switch.is_active() is True


def test_activation_persists_across_instances(tmp_path):
    path = tmp_path / "kill.json"
    first = KillSwitch(path)
    first.clear("EXPLICIT_OPERATOR_CLEAR")
    assert KillSwitch(path).is_active() is False
    first.activate("provider drift")
    assert KillSwitch(path).is_active() is True
    assert json.loads(path.read_text())["reason"] == "provider drift"


def test_model_cannot_clear_kill_switch(tmp_path):
    switch = KillSwitch(tmp_path / "kill.json")
    with pytest.raises(PermissionError):
        switch.clear("MODEL_RESPONSE")
