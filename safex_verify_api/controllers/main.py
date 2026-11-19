import ipaddress
import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 4096  # bytes
MAX_IDENTIFIER_LENGTH = 64
UNAUTHORIZED_LIMIT = 10  # wrong / missing keys per minute and server IP
RETRY_AFTER = 60  # seconds


class SafexVerifyApi(http.Controller):
    """CR-02 option 2: device verification called by the SafeX website's server.

    POST /api/safex/v1/verify
    Headers: Content-Type: application/json, X-SafeX-Api-Key: <key>
    Body:    {"serial_no": "...", "imei": "...", "client_ip": "<visitor IP, optional>"}
    See the module README for the responses.
    """

    @http.route('/api/safex/v1/verify', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def safex_verify(self, **kw):
        env = request.env(su=True)
        Log = env['safex.verify.api.log']
        remote_ip = request.httprequest.remote_addr or ''
        log_vals = {'remote_ip': remote_ip}

        def reply(status, result, payload, headers=None):
            Log.create(dict(log_vals, result=result))
            return request.make_json_response(payload, headers=headers, status=status)

        def rate_limited():
            return reply(429, 'rate_limited', {
                'error': 'rate_limited',
                'message': "Too many verification requests. Please try again in a minute.",
                'retry_after': RETRY_AFTER,
            }, headers=[('Retry-After', str(RETRY_AFTER))])

        # 1. API key (wrong keys are limited per server IP: no brute force)
        key = env['safex.verify.api.key']._find_by_key(request.httprequest.headers.get('X-SafeX-Api-Key', '').strip())
        if not key:
            if Log._count_recent([('remote_ip', '=', remote_ip), ('result', '=', 'unauthorized')]) >= UNAUTHORIZED_LIMIT:
                return rate_limited()
            return reply(401, 'unauthorized', {'error': 'unauthorized', 'message': "Missing or invalid API key."})
        log_vals['key_id'] = key.id
        if not key._is_ip_allowed(remote_ip):
            return reply(403, 'forbidden_ip', {'error': 'forbidden', 'message': "This server IP is not allowed."})

        # 2. Request body
        body = None
        if (request.httprequest.content_length or 0) <= MAX_BODY_SIZE:
            try:
                body = json.loads(request.httprequest.get_data(cache=False, as_text=True) or 'null')
            except ValueError:
                body = None
        if not isinstance(body, dict):
            return reply(400, 'bad_request', {'error': 'bad_request', 'message': "The body must be a JSON object."})
        serial_no = str(body.get('serial_no') or '').strip()
        imei = str(body.get('imei') or '').strip()
        client_ip = str(body.get('client_ip') or '').strip()
        if client_ip:
            try:
                client_ip = str(ipaddress.ip_address(client_ip))
            except ValueError:
                client_ip = ''
        log_vals.update(serial_no=serial_no[:MAX_IDENTIFIER_LENGTH], client_ip=client_ip or False)

        # 3. Rate limits (per key, per visitor)
        if Log._count_recent([('key_id', '=', key.id)]) >= key.rate_limit:
            return rate_limited()
        if client_ip and Log._count_recent(
                [('key_id', '=', key.id), ('client_ip', '=', client_ip)]) >= key.client_rate_limit:
            return rate_limited()

        if not serial_no or not imei:
            return reply(400, 'bad_request', {
                'error': 'bad_request', 'message': "Both serial_no and imei are required."})
        if len(serial_no) > MAX_IDENTIFIER_LENGTH or len(imei) > MAX_IDENTIFIER_LENGTH:
            return reply(400, 'bad_request', {
                'error': 'bad_request',
                'message': "serial_no and imei must be at most %s characters." % MAX_IDENTIFIER_LENGTH})

        # 4. Lookup
        key.last_used = fields.Datetime.now()
        try:
            result = env['stock.lot']._safex_public_verify(serial_no, imei)
        except Exception:
            _logger.exception("SafeX verification API: lookup failed for serial %s", serial_no)
            raise
        if not result:
            return reply(200, 'not_found', {
                'verified': False,
                'message': "No SafeX device matches this Serial Number and IMEI.",
            })
        return reply(200, 'verified', {
            'verified': True,
            'product': result['product'],
            'distributor': result['distributor'],
        })
