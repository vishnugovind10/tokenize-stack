// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

contract ComplianceRegistry {
    enum Reason {
        None,
        NotAllowlisted,
        TokenPaused,
        LockupActive
    }

    address public owner;
    bool public paused;
    mapping(address => bool) public allowlisted;
    mapping(address => uint256) public lockupUntil;

    event Allowlisted(address indexed account, bool allowed);
    event LockupSet(address indexed account, uint256 until);
    event Paused(bool paused);

    modifier onlyOwner() {
        require(msg.sender == owner, "owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function setAllowlisted(address account, bool allowed) external onlyOwner {
        allowlisted[account] = allowed;
        emit Allowlisted(account, allowed);
    }

    function setLockup(address account, uint256 until) external onlyOwner {
        lockupUntil[account] = until;
        emit LockupSet(account, until);
    }

    function setPaused(bool value) external onlyOwner {
        paused = value;
        emit Paused(value);
    }

    function canTransfer(address from, address to, uint256) external view returns (bool, Reason) {
        if (paused) return (false, Reason.TokenPaused);
        if (!allowlisted[from]) return (false, Reason.NotAllowlisted);
        if (!allowlisted[to]) return (false, Reason.NotAllowlisted);
        if (block.timestamp < lockupUntil[from]) return (false, Reason.LockupActive);
        return (true, Reason.None);
    }
}
