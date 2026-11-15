from odoo import fields, models


class SafexFaultCategory(models.Model):
    """Fault category recorded at technical inspection, e.g. "Display" (CR-10).
    Configurable in RMA & Repairs > Configuration > Fault Categories; a device can have several."""
    _name = 'safex.fault.category'
    _description = "SafeX Fault Category"
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', "A fault category with this name already exists."),
    ]
