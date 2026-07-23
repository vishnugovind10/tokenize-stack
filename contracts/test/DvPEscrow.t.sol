// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "../src/CashToken.sol";
import "../src/ComplianceRegistry.sol";
import "../src/DvPEscrow.sol";
import "../src/RestrictedAssetToken.sol";

contract DvPEscrowTest {
    ComplianceRegistry registry;
    RestrictedAssetToken asset;
    CashToken cash;
    DvPEscrow escrow;

    constructor() {
        registry = new ComplianceRegistry();
        registry.setAllowlisted(address(this), true);
        asset = new RestrictedAssetToken(address(this), 1_000_000 ether, registry);
        cash = new CashToken(address(this), 1_000_000 ether);
        escrow = new DvPEscrow(asset, cash);
    }

    function testLockAsset() public {
        asset.approve(address(escrow), 100 ether);
        escrow.lockAsset(bytes32("trade-1"), address(this), 100 ether, 100 ether, block.timestamp + 1);
    }
}
