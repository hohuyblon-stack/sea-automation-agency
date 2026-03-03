# Order Sync — Client Delivery Template

This is the deployment template for the **Multi-Platform Order Sync** service.

## Setup for a New Client

### 1. Copy this directory to the client folder

```bash
cp -r delivery/templates/order_sync clients/CLIENTNAME/
```

### 2. Fill in config.json

Edit `clients/CLIENTNAME/config.json`:

- `client.name` — Client's name
- `client.zalo_webhook` — Zalo OA webhook URL for notifications
- `platforms.shopee.*` — Shopee Open Platform credentials
- `platforms.tiktok_shop.*` — TikTok Shop credentials
- `platforms.lazada.*` — Lazada API credentials

Enable only the platforms the client uses (`"enabled": true`).

### 3. Get Platform API Credentials

**Shopee:**
1. Register at [open.shopee.com](https://open.shopee.com)
2. Create an app → get `partner_id` and `partner_key`
3. OAuth flow → get `shop_id`, `access_token`, `refresh_token`

**TikTok Shop:**
1. Register at [seller.tiktok.com/university/openplatform](https://seller.tiktok.com)
2. Create app → get `app_key` and `app_secret`
3. OAuth flow → get `access_token` and `shop_id`

**Lazada:**
1. Register at [open.lazada.com](https://open.lazada.com)
2. Create app → get `app_key` and `app_secret`
3. OAuth flow → get `access_token`

### 4. Install dependencies

```bash
cd clients/CLIENTNAME
pip install -r ../../requirements.txt
```

### 5. Run

```bash
# One-time test
python main.py --once

# Start daemon (runs every 15 minutes)
python main.py --daemon

# Check sync status
python main.py --status
```

### 6. Run as a service (production)

Using systemd (Linux VPS):

```ini
[Unit]
Description=Order Sync - CLIENTNAME
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/clients/CLIENTNAME/main.py --daemon
WorkingDirectory=/path/to/clients/CLIENTNAME
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Or use `cron` for a lighter setup:

```cron
*/15 * * * * /usr/bin/python3 /path/to/clients/CLIENTNAME/main.py --once >> logs/cron.log 2>&1
```

## Directory Structure After Deployment

```
clients/CLIENTNAME/
├── main.py          # Sync daemon (this file)
├── config.json      # Client-specific credentials & settings
├── data/
│   ├── orders.db    # SQLite order database
│   └── inventory.db # SQLite inventory database
└── logs/
    ├── sync.log     # Sync activity log
    └── errors.log   # Error log
```

## Monitoring

The system sends a Zalo message at 9am daily with:
- Orders synced (new, processing, shipped, cancelled)
- Revenue vs. previous day
- Low-stock items (if any)
- Any sync errors from the past 24h

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Token expired` error | Run `python main.py --refresh-tokens` |
| Orders not syncing | Check `logs/errors.log`, verify API credentials |
| Zalo not receiving | Test webhook URL with `python main.py --test-zalo` |
| High order volume lag | Decrease `sync.interval_minutes` in config.json |
