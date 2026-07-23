// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./SimpleERC20.sol";

// Demo settlement asset. Replace this interface with a real cash-leg integration.
contract CashToken is SimpleERC20 {
    constructor(address issuer, uint256 supply) SimpleERC20("MockEURCash", "MEUR") {
        _mint(issuer, supply);
    }
}
