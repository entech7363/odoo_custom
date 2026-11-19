from odoo import fields, models


class SafexVerifyApiKeyShow(models.TransientModel):
    """Shows a newly generated API key once (Odoo keeps only its hash on the key record)."""
    _name = 'safex.verify.api.key.show'
    _description = "SafeX Verification API Key (shown once)"
    # The plain key is deleted on Close, else by the daily transient-record cleanup.
    _transient_max_hours = 0.1

    key_id = fields.Many2one('safex.verify.api.key', required=True, ondelete='cascade')
    api_key = fields.Char(readonly=True)

    def action_close(self):
        self.unlink()
        return {'type': 'ir.actions.act_window_close'}
