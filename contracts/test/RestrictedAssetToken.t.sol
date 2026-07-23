// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";
import "../src/ComplianceRegistry.sol";
import "../src/RestrictedAssetToken.sol";

contract RestrictedAssetTokenTest is Test {
    ComplianceRegistry registry;
    RestrictedAssetToken token;

    address issuer = address(0xA11CE);
    address investor = address(0xB0B);

    function setUp() public {
        registry = new ComplianceRegistry();
        token = new RestrictedAssetToken(issuer, 1_000, registry);
        registry.setAllowlisted(issuer, true);
        registry.setAllowlisted(investor, true);
    }

    function testAllowlistedTransfer() public {
        vm.prank(issuer);
        token.transfer(investor, 100);
        assertEq(token.balanceOf(investor), 100);
    }

    function testNotAllowlistedRevert() public {
        address blocked = address(0xBAD);
        vm.expectRevert(abi.encodeWithSelector(NotAllowlisted.selector, blocked));
        vm.prank(issuer);
        token.transfer(blocked, 100);
    }

    function testPausedRevert() public {
        registry.setPaused(true);
        vm.expectRevert(TokenPaused.selector);
        vm.prank(issuer);
        token.transfer(investor, 100);
    }

    function testLockupRevert() public {
        registry.setLockup(issuer, block.timestamp + 7 days);
        vm.expectRevert(abi.encodeWithSelector(LockupActive.selector, issuer, block.timestamp + 7 days));
        vm.prank(issuer);
        token.transfer(investor, 100);
    }

    function testForceTransfer() public {
        token.forceTransfer(issuer, investor, 100);
        assertEq(token.balanceOf(investor), 100);
    }
}
