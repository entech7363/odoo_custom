{
    'name': 'SafeX RMA Reports & Communication',
    'version': '18.0.1.0.0',
    'category': 'Services/SafeX RMA',
    'summary': 'RMA reference slip, sectioned repair quotation, packing list and RMA emails',
    'description': """
SafeX RMA Reports & Communication (DES00106)
============================================
- QWeb PDFs: RMA Reference (inbound intake slip with barcode), Sectioned Repair Quotation,
  Consolidated Outbound Packing List.
- Emails: RMA submission (with reference PDF), quotation ready (with quotation PDF),
  dispatch tracking (with packing list).
- Manufacturer claim reporting on manufacturing-defect devices.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'mail',
        'sale',
        'stock',
        'safex_rma_core',
        'safex_rma_sale_account',
    ],
    'data': [
        'reports/safex_paperformats.xml',
        'reports/safex_report_actions.xml',
        'reports/report_rma_reference.xml',
        'reports/report_repair_quotation.xml',
        'reports/report_outbound_packing_list.xml',
        'data/mail_template_data.xml',
        'views/manufacturer_claim_views.xml',
    ],
    'installable': True,
    'application': False,
}
