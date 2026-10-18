# WireGuard configs (Mullvad egress)

Drop Mullvad WireGuard `.conf` files into this directory to use the
`wg-gateway` egress option. They are git-ignored (they contain private keys).

## Where to get configs

Download from Mullvad (https://mullvad.net/en/account/wireguard-config) — pick
**WireGuard**, choose exits (US exits are a good default for archive scraping),
and generate. Each file looks like:

```ini
[Interface]
PrivateKey = <redacted>
Address = 10.x.x.x/32,fc00:.../128
DNS = 10.64.0.1

[Peer]
PublicKey = <redacted>
AllowedIPs = 0.0.0.0/0,::0/0
Endpoint = <ip>:51820
```

You can also copy an existing local set, e.g.:

```bash
cp /home/bizon/Development/munin-community/local-dev/wireguard/*.conf ./
```

## How it's used

The `wg-gateway` service (compose profile `mullvad`) brings up one tunnel with
`wg-quick`, forcing **MTU 1280** (Mullvad stalls bulk transfers at a higher MTU)
and stripping IPv6/DNS. It exposes an HTTP proxy on `:8888` and SOCKS5 on `:1080`
that egress through the tunnel.

- Pick a specific exit: set `WG_GATEWAY_CONF=us-nyc-wg-504.conf` in `.env`.
- Leave `WG_GATEWAY_CONF` empty to pick a random `.conf` on each start.

## Switching egress

In `.env`:

```
EGRESS_PROVIDER=mullvad   # or "decodo" (default) or "none"
```

Then start the stack with the gateway:

```bash
docker compose --profile mullvad up -d
```

`EGRESS_PROVIDER=mullvad` points the backend/celery `PROXY_SERVER` at
`http://wg-gateway:8888`, so all archive/content fetches exit through Mullvad.

## Rotating the exit

```bash
./scripts/wg-rotate.sh        # restart the gateway -> new random exit, prints IP
```
