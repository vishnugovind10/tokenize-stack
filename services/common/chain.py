from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Protocol, cast

from eth_account.datastructures import SignedTransaction
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import TxParams, TxReceipt

from services.common.deployment import Deployment
from services.common.models import RestrictionReason

_NONCE_LOCKS: dict[str, asyncio.Lock] = {}


class TransactionSigner(Protocol):
    address: str

    def sign_transaction(self, tx_params: TxParams) -> SignedTransaction: ...


def get_w3(deployment: Deployment, attempts: int = 30, interval: float = 2.0) -> Web3:
    w3 = Web3(Web3.HTTPProvider(deployment.rpc_url))
    for _ in range(attempts):
        if w3.is_connected():
            return w3
        time.sleep(interval)
    raise RuntimeError(
        f"web3 provider not connected after {attempts * interval:.0f}s: {deployment.rpc_url}"
    )


def load_abi(deployment: Deployment, contract_name: str) -> list[dict[str, Any]]:
    artifact_path = Path(deployment.abi_dir) / f"{contract_name}.json"
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    return cast(list[dict[str, Any]], data["abi"])


def contract_handle(w3: Web3, deployment: Deployment, contract_name: str) -> Contract:
    return w3.eth.contract(
        address=Web3.to_checksum_address(deployment.addresses[contract_name]),
        abi=load_abi(deployment, contract_name),
    )


def registry(w3: Web3, deployment: Deployment) -> Contract:
    return contract_handle(w3, deployment, "ComplianceRegistry")


def asset(w3: Web3, deployment: Deployment) -> Contract:
    return contract_handle(w3, deployment, "RestrictedAssetToken")


def cash(w3: Web3, deployment: Deployment) -> Contract:
    return contract_handle(w3, deployment, "CashToken")


def escrow(w3: Web3, deployment: Deployment) -> Contract:
    return contract_handle(w3, deployment, "DvPEscrow")


def distributor(w3: Web3, deployment: Deployment) -> Contract:
    return contract_handle(w3, deployment, "CouponDistributor")


def trade_key(trade_id: str) -> bytes:
    return Web3.keccak(text=trade_id)


def decode_revert(err: BaseException) -> str:
    text = str(err)
    selector_map = {
        Web3.keccak(text="NotAllowlisted(address)")[
            :4
        ].hex(): RestrictionReason.NOT_ALLOWLISTED.value,
        Web3.keccak(text="TokenPaused()")[:4].hex(): RestrictionReason.TOKEN_PAUSED.value,
        Web3.keccak(text="LockupActive(address,uint256)")[
            :4
        ].hex(): RestrictionReason.LOCKUP_ACTIVE.value,
    }
    for selector, reason in selector_map.items():
        if selector in text:
            return reason
    if "NotAllowlisted" in text:
        return RestrictionReason.NOT_ALLOWLISTED.value
    if "TokenPaused" in text:
        return RestrictionReason.TOKEN_PAUSED.value
    if "LockupActive" in text:
        return RestrictionReason.LOCKUP_ACTIVE.value
    for reason in ("state", "expired", "not expired", "exists"):
        if reason in text:
            return reason
    return text


async def send(
    w3: Web3, deployment: Deployment, signer: TransactionSigner, tx_params: TxParams
) -> TxReceipt:
    address = Web3.to_checksum_address(signer.address)
    lock = _NONCE_LOCKS.setdefault(address, asyncio.Lock())
    async with lock:
        prepared = dict(tx_params)
        prepared.setdefault("from", address)
        prepared.setdefault("chainId", deployment.chain_id)
        prepared.setdefault("nonce", w3.eth.get_transaction_count(address, "pending"))
        priority_fee = int(
            cast(int, prepared.setdefault("maxPriorityFeePerGas", w3.eth.max_priority_fee))
        )
        latest = w3.eth.get_block("latest")
        base_fee = int(latest.get("baseFeePerGas", w3.eth.gas_price))
        prepared.setdefault("maxFeePerGas", base_fee + priority_fee * 2)
        if "gas" not in prepared:
            prepared["gas"] = w3.eth.estimate_gas(cast(TxParams, prepared))
        try:
            signed = signer.sign_transaction(cast(TxParams, prepared))
            raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        except ContractLogicError as exc:
            raise RuntimeError(decode_revert(exc)) from exc
        if int(receipt["status"]) == 0:
            raise RuntimeError("transaction reverted")
        return receipt
