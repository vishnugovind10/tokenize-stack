from __future__ import annotations

from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams

from services.common.deployment import Deployment
from services.common.models import Intent


def resolve_address(deployment: Deployment, value: str) -> str:
    address = deployment.personas.get(value, value)
    return Web3.to_checksum_address(address)


def build_transaction(
    intent: Intent,
    deployment: Deployment,
    cash_contract: Contract,
) -> TxParams:
    if intent.action != "transfer_cash":
        raise ValueError(f"unsupported custody action: {intent.action}")
    actor = resolve_address(deployment, intent.actor)
    destination = resolve_address(deployment, intent.destination)
    return cash_contract.functions.transfer(destination, intent.amount).build_transaction(
        {"from": actor}
    )
