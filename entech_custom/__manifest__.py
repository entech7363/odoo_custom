{
    'name':"Entech custom changes",
    'version':'1.12',
    'summary':'Creating various fields in the sale and purchase',
    'description':"module for the management of sales and purchases",
    'author': 'AGM Global Services',
    'website': 'https://www.agmglobal.co/',
    'licence': 'OPL-1',
    'depends':['base','sale','stock','account','purchase',],
    'data':['views/sale_order_view.xml',
             'views/stock_picking_view.xml',
             'views/purchase_order_view.xml',
             'views/account_move_view.xml',
             'views/res_partner.xml',
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