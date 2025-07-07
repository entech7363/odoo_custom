{
    'name': "En Custom Header",
    'version': '1.0',
    'author': 'AGM Global Services',
    'description': "Custom header",
    'depends': ['sale_management', 'sale', 'stock', 'account', 'web', 'base'],
    'data': [
        'reports/report_layout_striped_header.xml',
        'reports/report_paperformat_custom.xml',
        'views/res_company_form_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}
