{
    'name': 'SafeX RMA Reports & Communication',
    'version': '18.0.1.4.1',
    'category': 'Services/SafeX RMA',
    'summary': 'RMA reference slip, sectioned repair quotation, packing list and RMA emails',
    'description': """
SafeX RMA Reports & Communication (DES00106)
============================================
- QWeb PDFs: RMA Reference (inbound intake slip with barcode), Sectioned Repair Quotation,
  Consolidated Outbound Packing List, Inspection Report, Final Service Report.
- Units of the same model are grouped (model once, serial / IMEI per unit) on the RMA Reference,
  the repair quotation and RMA invoices.
- Emails: RMA submission (with reference PDF), receipt, inspection report (staff button),
  quotation ready (with quotation PDF), dispatch tracking (packing list + final service report).
- Manufacturer claim reporting on manufacturing-defect devices.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'mail',
        'sale',
        'account',
        'stock',
        'safex_rma_core',
        'safex_rma_sale_account',
        # Their invoice layouts both print the amount in words: printed once on SafeX invoices.
        'amount_in_words_invoice',
        'entech_custom',
    ],
    'data': [
        'reports/safex_paperformats.xml',
        'reports/safex_report_actions.xml',
        'reports/report_rma_reference.xml',
        'reports/report_repair_quotation.xml',
        'reports/report_outbound_packing_list.xml',
        'reports/report_inspection.xml',
        'reports/report_invoice.xml',
        'data/mail_template_data.xml',
        'views/manufacturer_claim_views.xml',
        'views/safex_rma_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'safex_rma_reports/static/src/scss/safex_report.scss',
        ],
    },
    'installable': True,
    'application': False,
}
