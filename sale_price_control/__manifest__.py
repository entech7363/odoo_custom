{
    'name':"Sale Price Control",
    'version':'1.2',
    'summary':"Management of sales price",
    'description':"Margin and minimum sales price of the product",
    'author':'AGM Global Services',
    'website':'https://www.agmservices.co/',
    'license':'OPL-1',
    'depends':['sale'],
    'data':[
            'security/ir.model.access.csv',
            'security/groups.xml',
            'views/product_template_view.xml',
            'views/sale_order_approval.xml',
            'views/res_users_views.xml',
            'wizard/sale_order_approval_wizard.xml',

    ],
    'installable': True,
    'application': False,
}