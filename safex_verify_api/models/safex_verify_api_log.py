from datetime import timedelta

from odoo import api, fields, models

LOG_RETENTION_DAYS = 90
RESULTS = [
    ('verified', "Verified"),
    ('not_found', "Not Found"),
    ('bad_request', "Bad Request"),
    ('unauthorized', "Wrong / Missing Key"),
    ('forbidden_ip', "IP Not Allowed"),
    ('rate_limited', "Rate Limited"),
]


class SafexVerifyApiLog(models.Model):
    """One call of the public device verification API. Also used to count the calls for the rate
    limits (stored in the database: shared by all the Odoo workers)."""
    _name = 'safex.verify.api.log'
    _description = "SafeX Verification API Call"
    _order = 'id desc'
    _log_access = False

    create_date = fields.Datetime(string="Date", default=fields.Datetime.now, readonly=True, index=True)
    key_id = fields.Many2one('safex.verify.api.key', string="API Key", readonly=True, index=True, ondelete='cascade')
    remote_ip = fields.Char(string="Server IP", readonly=True, index=True,
                            help="IP address the call came from (the website's server).")
    client_ip = fields.Char(string="Visitor IP", readonly=True, index=True,
                            help="IP address of the visitor, as sent by the website.")
    serial_no = fields.Char(string="Serial Number", readonly=True)
    result = fields.Selection(RESULTS, readonly=True, index=True)

    @api.model
    def _count_recent(self, domain, seconds=60):
        since = fields.Datetime.now() - timedelta(seconds=seconds)
        return self.sudo().search_count(domain + [('create_date', '>=', since)])

    @api.autovacuum
    def _gc_old_logs(self):
        limit = fields.Datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        self.sudo().search([('create_date', '<', limit)]).unlink()
