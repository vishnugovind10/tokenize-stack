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

    address internal constant ISSUER = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266;
    address internal constant INVESTOR_A = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8;
    address internal constant INVESTOR_B = 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC;
    address internal constant INVESTOR_C = 0x90F79bf6EB2c4f870365E785982E1f101E93b906;
    address internal constant INVESTOR_D = 0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65;
    address internal constant INVESTOR_E = 0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc;
    address internal constant INVESTOR_F = 0x976EA74026E726554dB657fA54763abd0C3a0aa9;

    function run() external {
        vm.startBroadcast();
        ComplianceRegistry registry = new ComplianceRegistry();
        RestrictedAssetToken asset = new RestrictedAssetToken(ISSUER, SUPPLY, registry);
        CashToken cash = new CashToken(ISSUER, SUPPLY * 5);
        DvPEscrow escrow = new DvPEscrow(asset, cash);
        CouponDistributor distributor = new CouponDistributor(cash, asset);

        registry.setAllowlisted(ISSUER, true);
        registry.setAllowlisted(INVESTOR_A, true);
        registry.setAllowlisted(INVESTOR_B, true);
        registry.setAllowlisted(INVESTOR_C, true);
        registry.setAllowlisted(INVESTOR_D, true);
        registry.setAllowlisted(INVESTOR_E, true);
        registry.setAllowlisted(address(escrow), true);
        registry.setAllowlisted(address(distributor), true);
        registry.setLockup(INVESTOR_D, block.timestamp + 7 days);

        cash.transfer(INVESTOR_A, INVESTOR_CASH);
        cash.transfer(INVESTOR_B, INVESTOR_CASH);
        cash.transfer(INVESTOR_C, INVESTOR_CASH);
        cash.transfer(INVESTOR_D, INVESTOR_CASH);
        cash.transfer(INVESTOR_E, UNDERFUNDED_CASH);
        cash.transfer(INVESTOR_F, INVESTOR_CASH);
        vm.stopBroadcast();

        vm.writeJson(deploymentJson(registry, asset, cash, escrow, distributor), "out/deployment.json");
    }

    function deploymentJson(
        ComplianceRegistry registry,
        RestrictedAssetToken asset,
        CashToken cash,
        DvPEscrow escrow,
        CouponDistributor distributor
    ) internal view returns (string memory) {
        return string.concat(
            '{"chain_id":',
            vm.toString(block.chainid),
            ',"rpc_url":"http://anvil:8545","addresses":',
            addressesJson(registry, asset, cash, escrow, distributor),
            ',"personas":',
            personasJson(),
            "}"
        );
    }

    function addressesJson(
        ComplianceRegistry registry,
        RestrictedAssetToken asset,
        CashToken cash,
        DvPEscrow escrow,
        CouponDistributor distributor
    ) internal view returns (string memory) {
        return string.concat(
            "{",
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
            '"}'
        );
    }

    function personasJson() internal view returns (string memory) {
        return string.concat(
            "{",
            '"issuer":"',
            vm.toString(ISSUER),
            '","investor-a":"',
            vm.toString(INVESTOR_A),
            '","investor-b":"',
            vm.toString(INVESTOR_B),
            '","investor-c":"',
            vm.toString(INVESTOR_C),
            '","investor-d":"',
            vm.toString(INVESTOR_D),
            '","investor-e":"',
            vm.toString(INVESTOR_E),
            '","investor-f":"',
            vm.toString(INVESTOR_F),
            '"}'
        );
    }
}
