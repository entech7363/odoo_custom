{
    'name': 'SafeX RMA Core',
    'version': '18.0.1.0.0',
    'category': 'Services/SafeX RMA',
    'summary': 'Multi-device RMA container, receiving, inspections, repair, spare parts and QC',
    'description': """
SafeX RMA Core (DES00105-DES00111, DES00113)
============================================
- safex.rma: one shipment/batch per dealer, RMA/YYYY/00001 numbering, inbound & outbound logistics.
- safex.rma.line: one card per device (serial), accessories audit, physical inspection,
  technical inspection, warranty decision, repair, final test and quality check.
- safex.rma.line.part: spare parts consumed; validated stock moves reduce inventory.
- Repeat-device alert and serial number service history.
- Single PO number per RMA that unlocks all PO-pending devices.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'mail',
        'stock',
        'repair',
        'safex_warranty_core',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/safex_security.xml',
        'data/ir_sequence_data.xml',
        'data/inspection_checklist_data.xml',
        'views/safex_inspection_views.xml',
        'views/safex_rma_line_views.xml',
        'views/safex_rma_views.xml',
        'views/res_company_views.xml',
        'views/product_template_views.xml',
        'views/safex_rma_menus.xml',
    ],
    'installable': True,
    'application': False,
}
