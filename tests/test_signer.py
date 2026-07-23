from __future__ import annotations

import pytest
from eth_account import Account

from services.common.personas import persona_address
from services.custody.signer import signer_for


@pytest.mark.parametrize(
    "tx",
    [
        {
            "nonce": 0,
            "gas": 21_000,
            "gasPrice": 1_000_000_000,
            "to": "0x0000000000000000000000000000000000000002",
            "value": 1,
            "chainId": 31337,
        },
        {
            "nonce": 1,
            "gas": 21_000,
            "maxFeePerGas": 2_000_000_000,
            "maxPriorityFeePerGas": 1_000_000_000,
            "to": "0x0000000000000000000000000000000000000002",
            "value": 1,
            "chainId": 31337,
        },
    ],
)
def test_local_key_signer_recovers_persona_address(tx: dict[str, object]) -> None:
    signed = signer_for("issuer").sign_transaction(tx)
    recovered = Account.recover_transaction(signed.raw_transaction)

    assert recovered.lower() == persona_address("issuer")
