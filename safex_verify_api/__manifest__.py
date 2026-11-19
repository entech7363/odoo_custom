{
    'name': 'SafeX Public Device Verification API',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'CR-02 option 2: JSON API used by the SafeX website to verify a device (Serial + IMEI)',
    'description': """
SafeX Public Device Verification API (CR-02, option 2)
======================================================
- POST /api/safex/v1/verify: the SafeX website's server sends a Serial Number + IMEI, Odoo answers
  whether it is a genuine SafeX device sold through a channel distributor (product + distributor only).
- API keys per website (only a hash is stored, the key is shown once), optional allowed server IPs.
- Rate limiting per API key, per visitor IP and on wrong keys, stored in the database (all workers).
- Call log for audit, cleaned up automatically after 90 days.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'repair',
        'safex_warranty_core',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/safex_verify_api_key_show_views.xml',
        'views/safex_verify_api_views.xml',
    ],
    'installable': True,
    'application': False,
}
