# Clients Directory

Each active client gets their own subdirectory here.

## Structure

```
clients/
├── README.md                      ← This file
├── shop_thoi_trang_abc/           ← One folder per client
│   ├── main.py                    ← Copy from delivery/templates/<service>/
│   ├── config.json                ← Client-specific credentials & settings
│   ├── client_data.json           ← Client contact & business info
│   ├── data/                      ← SQLite databases (gitignored)
│   │   ├── orders.db
│   │   └── inventory.db
│   ├── logs/                      ← Log files (gitignored)
│   └── reports/                   ← Generated reports
└── shop_my_pham_xyz/
    └── ...
```

## Adding a New Client

```bash
# 1. Create client directory
mkdir -p clients/CLIENT_SLUG

# 2. Copy service template
cp -r delivery/templates/order_sync/ clients/CLIENT_SLUG/
# or
cp -r delivery/templates/inventory_alerts/ clients/CLIENT_SLUG/

# 3. Fill in credentials
nano clients/CLIENT_SLUG/config.json

# 4. Save client info
cat > clients/CLIENT_SLUG/client_data.json << 'EOF'
{
  "client_name": "Nguyen Van A",
  "business_name": "Shop Thoi Trang ABC",
  "email": "contact@shop.vn",
  "phone": "0901234567",
  "platform": "Shopee",
  "city": "Ho Chi Minh",
  "service": "order_sync",
  "start_date": "2026-03-01",
  "monthly_retainer": 2000000
}
EOF

# 5. Test the connection
cd clients/CLIENT_SLUG
python main.py --status
python main.py --test-zalo

# 6. Run sync
python main.py --once

# 7. Start daemon (on server)
python main.py --daemon
```

## Client Status Codes

| Status | Meaning |
|--------|---------|
| `onboarding` | Contract signed, setting up |
| `active` | Running, all systems go |
| `paused` | Temporarily suspended |
| `churned` | Contract ended |

## Privacy Note

This directory is **gitignored** for private client data.
Do not commit `config.json` files containing API keys or tokens.
Only commit `client_data.json` if it contains no sensitive info.

The `.gitignore` at the project root excludes:
- `clients/*/config.json`
- `clients/*/data/`
- `clients/*/logs/`
- `clients/*/*.json` (except `client_data.json` explicitly)
