// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script} from "forge-std/Script.sol";
import "../src/CashToken.sol";
import "../src/ComplianceRegistry.sol";
import "../src/CouponDistributor.sol";
import "../src/DvPEscrow.sol";
import "../src/RestrictedAssetToken.sol";

contract Deploy is Script {
    uint256 internal constant SUPPLY = 1_000_000;
    uint256 internal constant INVESTOR_CASH = 500_000;
    uint256 internal constant UNDERFUNDED_CASH = 1_000;

    function run() external {
        address issuer = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266;
        address investorA = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8;
        address investorB = 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC;
        address investorC = 0x90F79bf6EB2c4f870365E785982E1f101E93b906;
        address investorD = 0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65;
        address investorE = 0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc;

        vm.startBroadcast();
        ComplianceRegistry registry = new ComplianceRegistry();
        RestrictedAssetToken asset = new RestrictedAssetToken(issuer, SUPPLY, registry);
        CashToken cash = new CashToken(issuer, SUPPLY * 5);
        DvPEscrow escrow = new DvPEscrow(asset, cash);
        CouponDistributor distributor = new CouponDistributor(cash, asset);

        registry.setAllowlisted(issuer, true);
        registry.setAllowlisted(investorA, true);
        registry.setAllowlisted(investorB, true);
        registry.setAllowlisted(investorC, true);
        registry.setAllowlisted(investorD, true);
        registry.setAllowlisted(investorE, true);
        registry.setAllowlisted(address(escrow), true);
        registry.setAllowlisted(address(distributor), true);
        registry.setLockup(investorD, block.timestamp + 7 days);

        cash.transfer(investorA, INVESTOR_CASH);
        cash.transfer(investorB, INVESTOR_CASH);
        cash.transfer(investorC, INVESTOR_CASH);
        cash.transfer(investorD, INVESTOR_CASH);
        cash.transfer(investorE, UNDERFUNDED_CASH);
        vm.stopBroadcast();

        string memory json = string.concat(
            '{"chain_id":',
            vm.toString(block.chainid),
            ',"rpc_url":"http://anvil:8545","addresses":{',
            '"ComplianceRegistry":"',
            vm.toString(address(registry)),
            '","RestrictedAssetToken":"',
            vm.toString(address(asset)),
            '","CashToken":"',
            vm.toString(address(cash)),
            '","DvPEscrow":"',
            vm.toString(address(escrow)),
            '","CouponDistributor":"',
            vm.toString(address(distributor)),
            '"},"personas":{',
            '"issuer":"',
            vm.toString(issuer),
            '","investor-a":"',
            vm.toString(investorA),
            '","investor-b":"',
            vm.toString(investorB),
            '","investor-c":"',
            vm.toString(investorC),
            '","investor-d":"',
            vm.toString(investorD),
            '","investor-e":"',
            vm.toString(investorE),
            '"}}'
        );
        vm.writeJson(json, "out/deployment.json");
    }
}
