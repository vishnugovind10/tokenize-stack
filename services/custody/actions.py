from __future__ import annotations

from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams

from services.common import chain
from services.common.deployment import Deployment
from services.common.models import Intent


def resolve_address(deployment: Deployment, value: str) -> str:
    address = deployment.personas.get(value, value)
    return Web3.to_checksum_address(address)


def build_transaction(
    intent: Intent,
    deployment: Deployment,
    asset_contract: Contract,
    cash_contract: Contract,
    escrow_contract: Contract,
    distributor_contract: Contract,
) -> TxParams:
    actor = resolve_address(deployment, intent.actor)
    escrow_address = resolve_address(deployment, deployment.addresses["DvPEscrow"])

    if intent.action == "transfer_cash":
        destination = resolve_address(deployment, intent.destination)
        return cash_contract.functions.transfer(destination, intent.amount).build_transaction(
            {"from": actor}
        )
    if intent.action == "approve_asset_escrow":
        return asset_contract.functions.approve(escrow_address, intent.amount).build_transaction(
            {"from": actor}
        )
    if intent.action == "approve_cash_escrow":
        return cash_contract.functions.approve(escrow_address, intent.amount).build_transaction(
            {"from": actor}
        )
    if intent.action == "lock_asset":
        trade_id = _required_str(intent, "trade_id")
        destination = resolve_address(deployment, intent.destination)
        cash_amount = _required_int(intent, "cash_amount")
        expiry = _required_int(intent, "expiry")
        return escrow_contract.functions.lockAsset(
            chain.trade_key(trade_id),
            destination,
            intent.amount,
            cash_amount,
            expiry,
        ).build_transaction({"from": actor})
    if intent.action == "settle_trade":
        return escrow_contract.functions.settle(
            chain.trade_key(_required_str(intent, "trade_id"))
        ).build_transaction({"from": actor})
    if intent.action == "unwind_trade":
        return escrow_contract.functions.unwind(
            chain.trade_key(_required_str(intent, "trade_id"))
        ).build_transaction({"from": actor})
    if intent.action == "distribute_coupon":
        round_id = _required_int(intent, "round_id")
        batch_size = _required_int(intent, "batch_size")
        holders = _required_addresses(intent, deployment, "holders")
        return distributor_contract.functions.distribute(
            round_id, holders, batch_size
        ).build_transaction({"from": actor})
    raise ValueError(f"unsupported custody action: {intent.action}")


def _required_str(intent: Intent, key: str) -> str:
    value = intent.params.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{intent.action} requires params.{key}")
    return value


def _required_int(intent: Intent, key: str) -> int:
    value = intent.params.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{intent.action} requires integer params.{key}")
    return value


def _required_addresses(intent: Intent, deployment: Deployment, key: str) -> list[str]:
    value = intent.params.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{intent.action} requires non-empty list params.{key}")
    addresses: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{intent.action} requires string addresses in params.{key}")
        addresses.append(resolve_address(deployment, item))
    return addresses
