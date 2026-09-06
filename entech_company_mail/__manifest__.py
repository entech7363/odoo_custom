{
    'name': "Entech Multi-Company Outgoing Mail",
    'version': '18.0.1.0.0',
    'category': 'Productivity/Discuss',
    'summary': 'Configurable company-specific outgoing email sender for multi-company setup',
    'description': """
Entech Multi-Company Outgoing Mail
==================================
Allows administrators to configure per company and per model whether outgoing emails
(Sales, Invoicing, Purchase, Inventory) automatically use the Company Email address
instead of the individual salesperson/user email.
    """,
    'author': 'AGM Global Services',
    'website': 'https://www.agmglobal.co/',
    'license': 'OPL-1',
    'depends': [
        'base',
        'base_setup',
        'mail',
        'sale',
        'account',
        'purchase',
        'stock',
    ],
    'data': [
        'views/res_config_settings_views.xml',
        'views/res_company_views.xml',
        'views/mail_compose_message_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
