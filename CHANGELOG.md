## [0.0.5](https://github.com/PFund-Software-Ltd/pfund-blocks/compare/v0.0.4...v0.0.5) - 2026-11-16

### 🚜 Refactor

- Move entities from pfund
- *(balances)* Clean up BaseBalance and BalanceUpdate, add tests
- *(positions)* Clean up BasePosition, DualPosition and PositionUpdate, add tests
- *(orders)* Add OrderUpdate/TradeUpdate, repr-based status updates, market on product

### 🎨 Styling

- Fix ruff lint in moved entities
- Fix ruff import order and formatting

### 🧪 Testing

- Use ty's abstract-class-instantiation rule in the MarketData ignore
- *(trades)* Add Quantity tests

### ⚙️ Miscellaneous Tasks

- Run pixi tests on windows-latest too

### 💼 Other

- Bump afterpython to >=0.5.3 and add it as a dev dependency group

## [0.0.4](https://github.com/PFund-Software-Ltd/pfund-blocks/compare/v0.0.3...v0.0.4) - 2026-11-09

### 🐛 Bug Fixes

- Drop future annotations in typing.py so msgspec decodes Message subclasses on Python 3.14

### ⚙️ Miscellaneous Tasks

- Bump afterpython and pytest, drop ruff.toml and ty.toml, relock
- Initialize afterpython (ruff/ty configs, CI, dependabot, pre-commit)
- Run CI before release, publish CI's build artifacts and create a GitHub release

### 💼 Other

- Link .venv to pixi's default env on activation so afterpython's hooks find it

## [0.0.3](https://github.com/PFund-Software-Ltd/pfund-blocks/compare/v0.0.2...v0.0.3) - 2026-11-07

### 💼 Other

- Lower msgspec and pydantic floors so pfund-blocks installs in Pyodide (WASM)
- Version 0.0.2 → 0.0.3

## [0.0.2](https://github.com/PFund-Software-Ltd/pfund-blocks/compare/v0.0.1...v0.0.2) - 2026-10-28

### 💼 Other

- Version 0.0.1 → 0.0.2

## [0.0.1] - 2026-10-25
