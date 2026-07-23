// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";
import "../src/CashToken.sol";
import "../src/ComplianceRegistry.sol";
import "../src/CouponDistributor.sol";
import "../src/RestrictedAssetToken.sol";

contract CouponDistributorTest is Test {
    ComplianceRegistry registry;
    RestrictedAssetToken asset;
    CashToken cash;
    CouponDistributor distributor;

    address issuer = address(this);
    address holderA = address(0xA);
    address holderB = address(0xB);

    function setUp() public {
        registry = new ComplianceRegistry();
        asset = new RestrictedAssetToken(issuer, 10_000, registry);
        cash = new CashToken(address(this), 10_000);
        distributor = new CouponDistributor(cash, asset);
        registry.setAllowlisted(issuer, true);
        registry.setAllowlisted(holderA, true);
        registry.setAllowlisted(holderB, true);
        registry.setAllowlisted(address(distributor), true);
        asset.transfer(holderA, 1_000);
        asset.transfer(holderB, 2_000);
        cash.transfer(address(distributor), 1_000);
    }

    function testCursorResumeAndIdempotency() public {
        address[] memory holders = new address[](2);
        holders[0] = holderA;
        holders[1] = holderB;

        distributor.distribute(1, holders, 1);
        assertEq(distributor.cursor(1), 1);
        assertEq(cash.balanceOf(holderA), 10);

        distributor.distribute(1, holders, 2);
        assertEq(distributor.cursor(1), 2);
        assertEq(cash.balanceOf(holderB), 20);

        distributor.distribute(1, holders, 2);
        assertEq(cash.balanceOf(holderA), 10);
        assertEq(cash.balanceOf(holderB), 20);
    }
}
