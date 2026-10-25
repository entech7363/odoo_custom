{
    'name': 'SafeX RMA Sales & Invoicing',
    'version': '18.0.1.0.0',
    'category': 'Services/SafeX RMA',
    'summary': 'Sectioned repair quotations, dealer approval, PO gating, reminders and invoicing',
    'description': """
SafeX RMA Sales & Invoicing (DES00112)
======================================
- Sectioned quotation per RMA: one section per device, a single priced Repair Service
  Charge line, replaced spare parts listed at 0.00 (display only, no extra stock move).
- Dealer actions: approve (devices go to PO Pending), reject a device with a mandatory
  reason (quotation recalculated), request clarification with a mandatory reason.
- PO number links to the quotation (also Entech's PO Number / PO Date, printed on deliveries and
  invoices); PO pending reminders on days 7, 14, 30 and 40.
- RMA quotations skip the sale_price_control minimum-price approval for the 0.00 replaced-part lines.
- Invoice creation for chargeable repairs.
- Configurable quotation Terms & Conditions per company.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'sale_stock',
        'account',
        'entech_custom',
        'sale_price_control',
        'safex_rma_core',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_data.xml',
        'data/mail_template_data.xml',
        'data/ir_cron_data.xml',
        'views/safex_rma_views.xml',
        'views/sale_order_views.xml',
        'views/res_company_views.xml',
    ],
    'installable': True,
    'application': False,
}
