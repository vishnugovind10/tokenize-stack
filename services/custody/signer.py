from __future__ import annotations

from eth_account import Account
from eth_account.datastructures import SignedTransaction
from typing import cast
from web3 import Web3
from web3.types import TxParams

from services.common.personas import MNEMONIC, PERSONAS

Account.enable_unaudited_hdwallet_features()


class LocalKeySigner:
    """Published Foundry dev mnemonic signer for demos; replace this seam with HSM/MPC."""

    def __init__(self, private_key: str) -> None:
        self._account = Account.from_key(private_key)
        self.address = str(Web3.to_checksum_address(self._account.address))

    def sign_transaction(self, tx_params: TxParams) -> SignedTransaction:
        return cast(SignedTransaction, self._account.sign_transaction(tx_params))


def signer_for(persona: str) -> LocalKeySigner:
    try:
        key_index = PERSONAS[persona].key_index
    except KeyError as exc:
        raise ValueError(f"unknown signing persona: {persona}") from exc
    account = Account.from_mnemonic(MNEMONIC, account_path=f"m/44'/60'/0'/0/{key_index}")
    return LocalKeySigner(str(account.key.hex()))
