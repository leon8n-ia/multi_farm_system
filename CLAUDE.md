# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the simulation
python main.py

# Run a specific test file (stdlib unittest)
python -m pytest tests/          # if pytest is installed
python -m unittest tests/test_economy.py
```

## Project Structure

```
multi_farm_system/
├── config.py          # All economic constants (single source of truth)
├── main.py            # Entry point — main simulation loop
├── shared/
│   └── models.py      # Dataclasses and enums shared across the system
├── core/
│   └── economy.py     # EconomyEngine: credit/penalty/reward logic
└── CLAUDE.md
```

## Architecture

This is a multi-agent farm simulation with a credit-based economy.

**Data flow:** `config.py` → `shared/models.py` (data shapes) → `core/economy.py` (mutations) → `main.py` (orchestration loop).

**Key concepts:**
- Every agent has `credits`; the economy engine debits/credits them based on game events.
- `CYCLE_INTERVAL_SECONDS` controls simulation speed; each cycle is one game tick.
- `REPRODUCTION_THRESHOLD` / `FARM_DEATH_THRESHOLD` are the lifecycle boundaries for agents and farms.
- All numeric tuning lives exclusively in `config.py` — never hardcode values elsewhere.

**Enums:** `AgentStatus` (ALIVE/DEAD/REPRODUCING), `FarmType` (CROP/LIVESTOCK/MIXED).

**EconomyEngine methods:**
- `apply_cost_of_living(agent)` — deducted every cycle
- `apply_action_cost(agent)` — deducted per agent action
- `apply_winner_reward` / `apply_loser_penalty` — competition outcomes
- `apply_sale_reward(agent, usd_amount)` — scales with `REWARD_PER_USD_SOLD`
- `calculate_roi(farm)` — returns `(revenue - expenses) / capital_invested`
