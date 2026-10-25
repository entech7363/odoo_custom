{
    'name': 'SafeX Warranty Core',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Warranty',
    'summary': 'Serial/IMEI registry, dual warranty clocks and cross-company device verification',
    'description': """
SafeX Warranty Core (DES00104, DES00110)
========================================
- Extends entech_components_tracking: IMEI 1 / IMEI 2 and the vendor / customer warranty
  fields already on serial numbers are reused as the SafeX factory / dealer warranty.
- Factory warranty (GRN date + 18 months) and SafeX dealer warranty
  (dealer delivery date + 16 months) defaults, visible to internal users only.
- Warranty classification (6 BRD values) and service traceability.
- Cross-company (SafeX Qatar / SafeX UK) verification API used by the dealer portal.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'stock',
        'sale_stock',
        'entech_components_tracking',
    ],
    'data': [
        'views/stock_lot_views.xml',
        'views/res_partner_views.xml',
        'views/res_company_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
}
