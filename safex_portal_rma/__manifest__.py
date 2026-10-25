{
    'name': 'SafeX Dealer Portal RMA',
    'version': '18.0.1.0.0',
    'category': 'Website/Portal',
    'summary': 'Dealer portal: device verification, multi-device RMA, quotation review and PO entry',
    'description': """
SafeX Dealer Portal RMA (DES00103, DES00104, DES00105, DES00112)
================================================================
- "RMA & Repairs" portal card with a live count; dealers only see their own company's RMAs.
- /my/verify: Serial + IMEI verification across SafeX Qatar and SafeX UK (no stock or warranty data).
- /my/rma/new: one submission with several verified devices, complaint and accessories.
- /my/rma/<id>: device cards, sectioned quotation, approve / reject device / clarify, PO number.
- Downloads: RMA reference, repair quotation, invoices and packing list.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'portal',
        'safex_warranty_core',
        'safex_rma_core',
        'safex_rma_sale_account',
        'safex_rma_reports',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/safex_security.xml',
        'views/portal_templates.xml',
        'views/portal_verify_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'safex_portal_rma/static/src/scss/portal_rma.scss',
            'safex_portal_rma/static/src/js/portal_rma.js',
        ],
    },
    'installable': True,
    'application': False,
}
