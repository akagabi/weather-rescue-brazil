import pytest
from wrb.guard import assert_personal, BillingGuardError

def test_blocks_desert_ant_identifiers():
    for bad in ["desert-ant-labs", "Desert-Ant-Labs/x", "org=desert-ant"]:
        with pytest.raises(BillingGuardError):
            assert_personal(bad)

def test_allows_personal():
    assert_personal("akagabi")          # returns None, no raise
    assert_personal("https://generativelanguage.googleapis.com")
