// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./CashToken.sol";
import "./RestrictedAssetToken.sol";

contract CouponDistributor {
    CashToken public cash;
    RestrictedAssetToken public asset;
    mapping(uint256 => mapping(address => bool)) public paid;
    mapping(uint256 => uint256) public cursor;

    event Paid(uint256 indexed roundId, address indexed holder, uint256 amount);

    constructor(CashToken cashToken, RestrictedAssetToken assetToken) {
        cash = cashToken;
        asset = assetToken;
    }

    function distribute(uint256 roundId, address[] calldata holders, uint256 batchSize) external {
        uint256 index = cursor[roundId];
        uint256 end = index + batchSize;
        if (end > holders.length) end = holders.length;
        for (; index < end; index++) {
            address holder = holders[index];
            if (!paid[roundId][holder]) {
                uint256 amount = asset.balanceOf(holder) / 100;
                paid[roundId][holder] = true;
                require(cash.transfer(holder, amount), "coupon transfer");
                emit Paid(roundId, holder, amount);
            }
        }
        cursor[roundId] = index;
    }
}
