{
    'name': "En Custom Header",
    'version': '1.3',
    'author': 'AGM Global Services',
    'description': "Custom header",
    'depends': ['sale_management', 'sale', 'stock', 'account', 'web', 'base'],
    'data': [
        'reports/report_template_header.xml',
        'reports/report_print.xml',
        'views/en_company_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}
