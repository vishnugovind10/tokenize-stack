// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";
import "../src/CashToken.sol";
import "../src/ComplianceRegistry.sol";
import "../src/DvPEscrow.sol";
import "../src/RestrictedAssetToken.sol";

contract DvPEscrowTest is Test {
    ComplianceRegistry registry;
    RestrictedAssetToken asset;
    CashToken cash;
    DvPEscrow escrow;

    address seller = address(0xA11CE);
    address buyer = address(0xB0B);

    function setUp() public {
        registry = new ComplianceRegistry();
        asset = new RestrictedAssetToken(seller, 1_000_000, registry);
        cash = new CashToken(buyer, 500_000);
        escrow = new DvPEscrow(asset, cash);

        registry.setAllowlisted(seller, true);
        registry.setAllowlisted(buyer, true);
        registry.setAllowlisted(address(escrow), true);

        vm.prank(seller);
        asset.approve(address(escrow), type(uint256).max);
        vm.prank(buyer);
        cash.approve(address(escrow), type(uint256).max);
    }

    function testSettleHappyPathMovesBothLegs() public {
        bytes32 tradeId = keccak256("trade-1");
        vm.prank(seller);
        escrow.lockAsset(tradeId, buyer, 100, 75, block.timestamp + 1 days);

        vm.prank(buyer);
        escrow.settle(tradeId);

        assertEq(asset.balanceOf(buyer), 100);
        assertEq(cash.balanceOf(seller), 75);
    }

    function testDoubleSettleReverts() public {
        bytes32 tradeId = keccak256("trade-2");
        vm.prank(seller);
        escrow.lockAsset(tradeId, buyer, 100, 75, block.timestamp + 1 days);
        vm.prank(buyer);
        escrow.settle(tradeId);

        vm.expectRevert("state");
        vm.prank(buyer);
        escrow.settle(tradeId);
    }

    function testSettleAfterExpiryReverts() public {
        bytes32 tradeId = keccak256("trade-3");
        vm.prank(seller);
        escrow.lockAsset(tradeId, buyer, 100, 75, block.timestamp + 1 days);

        vm.warp(block.timestamp + 2 days);
        vm.expectRevert("expired");
        vm.prank(buyer);
        escrow.settle(tradeId);
    }

    function testUnwindBeforeExpiryReverts() public {
        bytes32 tradeId = keccak256("trade-4");
        vm.prank(seller);
        escrow.lockAsset(tradeId, buyer, 100, 75, block.timestamp + 1 days);

        vm.expectRevert("not expired");
        escrow.unwind(tradeId);
    }

    function testUnwindAfterExpiryReturnsAsset() public {
        bytes32 tradeId = keccak256("trade-5");
        vm.prank(seller);
        escrow.lockAsset(tradeId, buyer, 100, 75, block.timestamp + 1 days);

        vm.warp(block.timestamp + 2 days);
        escrow.unwind(tradeId);

        assertEq(asset.balanceOf(seller), 1_000_000);
    }

    function testNonAllowlistedBuyerSettleReverts() public {
        address blockedBuyer = address(0xBAD);
        cash = new CashToken(blockedBuyer, 500_000);
        escrow = new DvPEscrow(asset, cash);
        registry.setAllowlisted(address(escrow), true);
        vm.prank(seller);
        asset.approve(address(escrow), type(uint256).max);
        vm.prank(blockedBuyer);
        cash.approve(address(escrow), type(uint256).max);

        bytes32 tradeId = keccak256("trade-6");
        vm.prank(seller);
        escrow.lockAsset(tradeId, blockedBuyer, 100, 75, block.timestamp + 1 days);

        vm.expectRevert(abi.encodeWithSelector(NotAllowlisted.selector, blockedBuyer));
        vm.prank(blockedBuyer);
        escrow.settle(tradeId);
    }
}
