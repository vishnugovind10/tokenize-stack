// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./ComplianceRegistry.sol";
import "./SimpleERC20.sol";

error NotAllowlisted(address account);
error TokenPaused();
error LockupActive(address account, uint256 until);

contract RestrictedAssetToken is SimpleERC20 {
    ComplianceRegistry public registry;

    event ForcedTransfer(address indexed from, address indexed to, uint256 amount);

    constructor(address issuer, uint256 supply, ComplianceRegistry complianceRegistry)
        SimpleERC20("Restricted Asset Token", "RAT")
    {
        registry = complianceRegistry;
        _mint(issuer, supply);
    }

    function transfer(address to, uint256 amount) public override returns (bool) {
        _check(msg.sender, to, amount);
        return super.transfer(to, amount);
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        _check(from, to, amount);
        return super.transferFrom(from, to, amount);
    }

    function forceTransfer(address from, address to, uint256 amount) external {
        require(msg.sender == registry.owner(), "registry owner");
        _transfer(from, to, amount);
        emit ForcedTransfer(from, to, amount);
    }

    function _check(address from, address to, uint256 amount) internal view {
        (bool allowed, ComplianceRegistry.Reason reason) = registry.canTransfer(from, to, amount);
        if (!allowed && reason == ComplianceRegistry.Reason.TokenPaused) revert TokenPaused();
        if (!allowed && reason == ComplianceRegistry.Reason.LockupActive) {
            revert LockupActive(from, registry.lockupUntil(from));
        }
        if (!allowed) {
            if (!registry.allowlisted(from)) revert NotAllowlisted(from);
            revert NotAllowlisted(to);
        }
    }
}
