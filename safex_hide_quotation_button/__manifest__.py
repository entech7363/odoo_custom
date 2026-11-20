{
    'name': 'Hide Quotation Email Button',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Setting to remove the View/Accept & Sign/Pay Quotation button from quotation emails',
    'description': """
Hide Quotation Email Button
============================
Adds a single checkbox in Settings -> Sales ("Hide Quotation Email Button"). When enabled, the
View Quotation / Accept & Sign Quotation / Accept & Pay Quotation button is removed from every
quotation and sales order email, for every company. Used when the database's own portal URL
(e.g. after a domain change) should not be exposed to customers of a company that isn't meant
to see it.
    """,
    'author': 'SafeX Instruments',
    'license': 'OEEL-1',
    'depends': [
        'sale',
    ],
    'data': [
        'views/res_config_settings_views.xml',
        'views/mail_notification_layout_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
