// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "../src/CashToken.sol";
import "../src/ComplianceRegistry.sol";
import "../src/DvPEscrow.sol";
import "../src/RestrictedAssetToken.sol";

contract Deploy {
    function deploy() external returns (ComplianceRegistry, RestrictedAssetToken, CashToken, DvPEscrow) {
        ComplianceRegistry registry = new ComplianceRegistry();
        registry.setAllowlisted(msg.sender, true);
        RestrictedAssetToken asset = new RestrictedAssetToken(msg.sender, 1_000_000 ether, registry);
        CashToken cash = new CashToken(msg.sender, 1_000_000 ether);
        DvPEscrow escrow = new DvPEscrow(asset, cash);
        return (registry, asset, cash, escrow);
    }
}
