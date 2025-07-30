{
    'name': 'Entech Components Tracking',
    'version': '1.8',
    'category': 'Custom',
    'depends': ['base', 'sale', 'purchase', 'product', 'stock', 'account'],
    'data': [
        'views/product_template_views.xml',
        'views/stock_move_line_wizard.xml',
        'views/res_partner_view.xml',
        'views/partner_type_context_inherit_views.xml',
        'views/product_part_menu.xml',
        'views/stock_move.xml',
        'views/stock_production_lot_view.xml',
        'views/account_move.xml',
        # 'views/account_move_line.xml',
        # 'views/stock_picking.xml',
        'data/sequence.xml',
        'security/ir.model.access.csv',
        'report/report_delivery.xml',
        'report/report_invoice.xml',


    ],

    'installable': True,
    'application': True,

    'assets': {
        'web.assets_backend': [
            'entech_components_tracking/static/src/js/auto_tab.js',
        ],
    },
}
