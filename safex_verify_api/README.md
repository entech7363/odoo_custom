# SafeX Public Device Verification API (CR-02, option 2)

The SafeX website's **server** sends a Serial Number + IMEI to Odoo; Odoo answers whether it is a
genuine SafeX device sold through a channel distributor. Only the product and the distributor are
returned.

```
Visitor's browser --(form + captcha)--> SafeX website server --(HTTPS + API key)--> Odoo
                  <---- result page ---                      <------- JSON --------
```

## Setup in Odoo

1. Install `safex_verify_api`.
2. Repair → Configuration → Website Verification API → API Keys → New.
3. Name it (e.g. "SafeX Instruments website"), optionally set the website server's IP(s), save.
4. Click **Generate Key**, copy the key (shown once) and hand it over through a secure channel.
5. To revoke: archive the key. To rotate: **Regenerate Key** (the old key stops working at once).

## API for the website developer

```
POST https://<odoo-domain>/api/safex/v1/verify
Content-Type: application/json
X-SafeX-Api-Key: <key>

{"serial_no": "SX123456", "imei": "356789012345678", "client_ip": "198.51.100.23"}
```

| Field | Required | Notes |
|---|---|---|
| `serial_no` | yes | Product serial number, max 64 characters (spaces and case are ignored) |
| `imei` | yes | IMEI 1 or IMEI 2 of the same device, max 64 characters |
| `client_ip` | recommended | The **visitor's** IP address, for the per-visitor rate limit |

### Responses

| Status | Body | Meaning |
|---|---|---|
| 200 | `{"verified": true, "product": "...", "distributor": "..."}` | Genuine SafeX device |
| 200 | `{"verified": false, "message": "..."}` | No SafeX device matches |
| 400 | `{"error": "bad_request", "message": "..."}` | Missing / too long fields, body not JSON |
| 401 | `{"error": "unauthorized", ...}` | Missing or wrong API key |
| 403 | `{"error": "forbidden", ...}` | Server IP not in the key's allowed IPs |
| 429 | `{"error": "rate_limited", "retry_after": 60}` + `Retry-After` header | Too many calls |

### Rules

- Call the API **from the website's server only**. The key must never appear in browser JavaScript
  or page source.
- Put a captcha (reCAPTCHA / hCaptcha) on the website form and check it server-side before calling.
- Use a timeout of about 10 seconds. On a timeout or 5xx, show "Verification unavailable", never
  "not genuine".
- Creating an RMA still requires the dealer portal login: `https://<odoo-domain>/my/rma/new`.

### Test

```bash
curl -i -X POST https://<odoo-domain>/api/safex/v1/verify \
  -H "Content-Type: application/json" \
  -H "X-SafeX-Api-Key: <key>" \
  -d '{"serial_no": "SX123456", "imei": "356789012345678"}'
```

## Rate limits (stored in the database, shared by all Odoo workers)

- Per key: `Calls per Minute (Key)`, default 60.
- Per visitor IP (`client_ip`): `Calls per Minute (Visitor)`, default 10.
- Wrong / missing keys: 10 per minute per server IP, then 429.

Every call is logged (Repair → Configuration → Website Verification API → API Calls). The IMEI is
never stored. Logs are deleted after 90 days.
