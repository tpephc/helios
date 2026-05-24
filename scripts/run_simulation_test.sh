#!/bin/bash
# One-time simulation test report — runs once then removes itself from cron
set -e
cd /home/tradeagent/projects/helios
LOG="logs/simulation_test.log"
echo "[$(date)] Starting simulation test" >> $LOG

/home/tradeagent/.local/bin/uv run python -c "
import shioaji as sj
from shioaji.constant import Action, StockPriceType, OrderType
from config.settings import get_settings
import time

cfg = get_settings()
api = sj.Shioaji(simulation=True)
api.login(
    api_key=cfg.shioaji_api_key.get_secret_value(),
    secret_key=cfg.shioaji_secret_key.get_secret_value(),
    fetch_contract=True, contracts_timeout=30000, subscribe_trade=True,
)
api.activate_ca(
    ca_path=cfg.ca_cert_path,
    ca_passwd=cfg.ca_password.get_secret_value(),
    person_id=api.stock_account.person_id,
)
print('signed:', api.stock_account.signed)
contract = api.Contracts.Stocks.TSE['2890']
print('contract:', contract.code, contract.reference)
order = sj.order.StockOrder(
    action=Action.Buy, price=contract.reference,
    quantity=1, price_type=StockPriceType.LMT,
    order_type=OrderType.ROD, account=api.stock_account,
)
trade = api.place_order(contract, order)
print('trade:', trade)
time.sleep(2)
api.update_status(api.stock_account)
print('status:', trade.status)
api.logout()
" >> $LOG 2>&1

echo "[$(date)] Done. Removing from cron." >> $LOG

# 自我刪除
crontab -l | grep -v "run_simulation_test.sh" | crontab -
