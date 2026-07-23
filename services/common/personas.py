from __future__ import annotations

from dataclasses import dataclass

# Published Foundry dev mnemonic - demo only.
MNEMONIC = "test test test test test test test test test test test junk"


@dataclass(frozen=True)
class Persona:
    name: str
    key_index: int
    address: str


PERSONAS: dict[str, Persona] = {
    "issuer": Persona("issuer", 0, "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"),
    "investor-a": Persona("investor-a", 1, "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"),
    "investor-b": Persona("investor-b", 2, "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc"),
    "investor-c": Persona("investor-c", 3, "0x90f79bf6eb2c4f870365e785982e1f101e93b906"),
    "investor-d": Persona("investor-d", 4, "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65"),
    "investor-e": Persona("investor-e", 5, "0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc"),
}


def persona_address(name: str) -> str:
    try:
        return PERSONAS[name].address
    except KeyError as exc:
        raise ValueError(f"unknown persona: {name}") from exc
