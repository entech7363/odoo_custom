{
    'name': "Intergulf Sale and Purchase Approvals",
    'version': '1.1',
    'author': 'AGM Global Services',
    'depends': ['base','sale_management','sale','purchase'],
    'data': [
        'security/ir.model.access.csv',
        'security/groups.xml',
        'views/approvals.xml',
         #'views/sale_order.xml',
         'views/purchase_order.xml',

    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
