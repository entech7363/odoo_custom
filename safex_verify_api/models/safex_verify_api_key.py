import hashlib
import ipaddress
import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError

KEY_PREFIX = 'sfx_'


def hash_api_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


class SafexVerifyApiKey(models.Model):
    """API key of a website calling the public device verification API (CR-02 option 2). Only a hash
    of the key is stored: the key is shown once, when it is generated."""
    _name = 'safex.verify.api.key'
    _description = "SafeX Verification API Key"
    _order = 'name'

    name = fields.Char(required=True, help="Who uses this key, e.g. \"SafeX Instruments website\".")
    active = fields.Boolean(default=True, help="Archive the key to revoke it: calls with it are refused.")
    key_hash = fields.Char(readonly=True, copy=False, index=True, groups='base.group_system')
    key_hint = fields.Char(string="Key", readonly=True, copy=False,
                           help="First characters of the key, to recognise it.")
    allowed_ips = fields.Char(
        string="Allowed Server IPs",
        help="Comma-separated IP addresses or networks (e.g. 203.0.113.10, 198.51.100.0/24) of the website's "
             "server. Empty: any IP.")
    rate_limit = fields.Integer(
        string="Calls per Minute (Key)", default=60, required=True,
        help="Maximum calls per minute with this key, all visitors together.")
    client_rate_limit = fields.Integer(
        string="Calls per Minute (Visitor)", default=10, required=True,
        help="Maximum calls per minute for one visitor IP (sent by the website as \"client_ip\").")
    last_used = fields.Datetime(readonly=True, copy=False)
    log_ids = fields.One2many('safex.verify.api.log', 'key_id', string="Calls")
    log_count = fields.Integer(compute='_compute_log_count', string="Calls Logged")

    _sql_constraints = [
        ('key_hash_unique', 'UNIQUE(key_hash)', "This API key already exists."),
        ('rate_limits_positive', 'CHECK(rate_limit > 0 AND client_rate_limit > 0)',
         "The rate limits must be positive."),
    ]

    @api.depends('log_ids')
    def _compute_log_count(self):
        counts = dict(self.env['safex.verify.api.log']._read_group(
            [('key_id', 'in', self.ids)], ['key_id'], ['__count']))
        for key in self:
            key.log_count = counts.get(key, 0)

    @api.constrains('allowed_ips')
    def _check_allowed_ips(self):
        for key in self:
            key._get_allowed_networks(raise_invalid=True)

    def _get_allowed_networks(self, raise_invalid=False):
        self.ensure_one()
        networks = []
        for value in (self.allowed_ips or '').replace(';', ',').split(','):
            value = value.strip()
            if not value:
                continue
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                if raise_invalid:
                    raise ValidationError(self.env._("\"%s\" is not a valid IP address or network.", value))
        return networks

    def _is_ip_allowed(self, ip):
        self.ensure_one()
        networks = self._get_allowed_networks()
        if not networks:
            return True
        try:
            address = ipaddress.ip_address(ip or '')
        except ValueError:
            return False
        return any(address in network for network in networks)

    @api.model
    def _find_by_key(self, key):
        """Active API key record matching the raw key sent by the website (empty when none)."""
        if not key or not key.startswith(KEY_PREFIX) or len(key) > 128:
            return self.browse()
        return self.sudo().search([('key_hash', '=', hash_api_key(key))], limit=1)

    def action_generate_key(self):
        """Generate a new key (replacing the current one) and show it once."""
        self.ensure_one()
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        self.sudo().write({'key_hash': hash_api_key(key), 'key_hint': key[:10] + '…'})
        wizard = self.env['safex.verify.api.key.show'].create({'key_id': self.id, 'api_key': key})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("New API Key"),
            'res_model': 'safex.verify.api.key.show',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("API Calls"),
            'res_model': 'safex.verify.api.log',
            'view_mode': 'list,form',
            'domain': [('key_id', '=', self.id)],
        }
