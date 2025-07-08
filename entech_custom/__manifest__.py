{
    'name':"education management",
    'version':'1.0',
    'description':"module for the education",
    'depends':['sale','stock','account','purchase'],
    'data':['views/sale_order_view.xml',
             'views/stock_picking_view.xml',
             'views/purchase_order_view.xml',
             'views/account_move_view.xml',
             'reports/sale_report.xml',
            'reports/invoice_report.xml',
            'reports/delivery_report.xml',
            'reports/purchase_order_report.xml',
            'reports/receipt_report.xml',
            'reports/bill_report.xml',
            ],
    'installable':True,
    'application':False,


}