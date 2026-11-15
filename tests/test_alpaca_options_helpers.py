import pandas as pd

from market_agent.clients.alpaca_options import _contract_open_interest


def test_contract_open_interest_lookup():
    contracts = pd.DataFrame(
        [
            {"symbol": "C1", "open_interest": 1200.0},
            {"symbol": "P1", "open_interest": None},
        ]
    )
    assert _contract_open_interest(contracts, "C1") == 1200.0
    assert _contract_open_interest(contracts, "P1") is None
    assert _contract_open_interest(contracts, "X") is None