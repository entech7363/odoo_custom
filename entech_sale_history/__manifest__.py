{
    'name':"Inter Sale",
    'version':'1.0',
    'summary':"Management of order history",
    'description':"All information and history about the orders made by a customer",
    'author':'AGM Global Services',
    'website':'https://www.agmservices.co/',
    'license':'OPL-1',
    'depends':['sale'],
    'data':[
          'security/ir.model.access.csv',
          'views/sale_order_line_view.xml',
          'wizard/sale_order_wizard_view.xml',
          ],
    'installable': True,
    'application': False,
}