import pytest
from src.execution.testnet_gate import ConfigGateError, gate_status, validate_testnet_config

def test_testnet_gate_rejects_production():
    with pytest.raises(ConfigGateError): validate_testnet_config('testnet','USDT-FUTURES',True)
    with pytest.raises(ConfigGateError): validate_testnet_config('testnet','BTC-USDT',True)

def test_testnet_gate_requires_testnet_mode_and_dry_run():
    with pytest.raises(ConfigGateError): validate_testnet_config('live','SUSDT-FUTURES',True)
    with pytest.raises(ConfigGateError): validate_testnet_config('testnet','SUSDT-FUTURES',False)
    validate_testnet_config('testnet','SUSDT-FUTURES',True)
    assert gate_status()=='SCAFFOLD_ONLY_NO_SIGNED_CALLS'
