// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Minimal ERC1155-based fractional bond token.
 * Each ISIN maps to an ERC1155 token id (uint256).
 * Units represent face value units (e.g., ₹1).
 */
import "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract BondToken is ERC1155, Ownable {
    mapping(bytes12 => uint256) public isinToId;
    uint256 public nextId = 1;

    constructor() ERC1155("") Ownable(msg.sender) {}

    function idForISIN(bytes12 isin) public returns (uint256) {
        if (isinToId[isin] == 0) {
            isinToId[isin] = nextId++;
        }
        return isinToId[isin];
    }

    function mint(bytes12 isin, address to, uint256 amount) external onlyOwner {
        uint256 id = idForISIN(isin);
        _mint(to, id, amount, "");
    }
}
