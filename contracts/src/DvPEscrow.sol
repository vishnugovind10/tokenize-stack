// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./CashToken.sol";
import "./RestrictedAssetToken.sol";

contract DvPEscrow {
    enum State {
        None,
        AssetLocked,
        Settled,
        Unwound
    }

    struct Trade {
        address seller;
        address buyer;
        uint256 assetAmount;
        uint256 cashAmount;
        uint256 expiry;
        State state;
    }

    RestrictedAssetToken public asset;
    CashToken public cash;
    mapping(bytes32 => Trade) public trades;
    bool private locked;

    event AssetLocked(bytes32 indexed tradeId, address indexed seller, address indexed buyer);
    event Settled(bytes32 indexed tradeId);
    event Unwound(bytes32 indexed tradeId);

    modifier nonReentrant() {
        require(!locked, "reentrant");
        locked = true;
        _;
        locked = false;
    }

    constructor(RestrictedAssetToken assetToken, CashToken cashToken) {
        asset = assetToken;
        cash = cashToken;
    }

    function lockAsset(bytes32 tradeId, address buyer, uint256 assetAmount, uint256 cashAmount, uint256 expiry)
        external
        nonReentrant
    {
        require(trades[tradeId].state == State.None, "exists");
        require(expiry > block.timestamp, "expiry");
        trades[tradeId] = Trade(msg.sender, buyer, assetAmount, cashAmount, expiry, State.AssetLocked);
        require(asset.transferFrom(msg.sender, address(this), assetAmount), "asset transfer");
        emit AssetLocked(tradeId, msg.sender, buyer);
    }

    function settle(bytes32 tradeId) external nonReentrant {
        Trade storage trade = trades[tradeId];
        require(trade.state == State.AssetLocked, "state");
        require(msg.sender == trade.buyer, "buyer");
        require(block.timestamp <= trade.expiry, "expired");
        trade.state = State.Settled;
        require(cash.transferFrom(trade.buyer, trade.seller, trade.cashAmount), "cash transfer");
        require(asset.transfer(trade.buyer, trade.assetAmount), "asset transfer");
        emit Settled(tradeId);
    }

    function unwind(bytes32 tradeId) external nonReentrant {
        Trade storage trade = trades[tradeId];
        require(trade.state == State.AssetLocked, "state");
        require(block.timestamp > trade.expiry, "not expired");
        trade.state = State.Unwound;
        require(asset.transfer(trade.seller, trade.assetAmount), "asset return");
        emit Unwound(tradeId);
    }
}
