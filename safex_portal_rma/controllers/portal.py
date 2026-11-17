import json
import time

from odoo import Command, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager

RMA_PER_PAGE = 10
# Warranty data, stock, locations and costs are never sent to dealers.
# CR-04: for a device sold through another dealer only the product and that dealer's name are sent.
PORTAL_VERIFY_KEYS = ('verified', 'status', 'message', 'lot_id', 'serial_no', 'product_name', 'delivery_date',
                      'last_rma', 'distributor')
PHOTO_MAX_COUNT = 5
PHOTO_MAX_SIZE = 5 * 1024 * 1024
PO_MAX_SIZE = 10 * 1024 * 1024
VERIFY_MAX_CALLS = 20  # a dealer adding devices to an RMA verifies each one
VERIFY_WINDOW = 60  # seconds
# An RMA submission verifies its devices again: they count in the same limit, with a margin so that
# the devices just verified one by one can still be submitted.
SUBMIT_MAX_VERIFICATIONS = 60
MAX_DEVICES_PER_RMA = 50
MAX_IDENTIFIER_LENGTH = 64  # serial number / IMEI typed by the dealer
NEW_RMA_ERRORS = ('device', 'empty', 'duplicate', 'mixed_company', 'unavailable', 'other_dealer', 'photo', 'too_many',
                  'accessory_serial_missing', 'battery_serial', 'dock_serial', 'throttled')
ACCESSORY_KEYS = ('charger', 'dock', 'battery', 'screwdriver', 'cable', 'box')
# Accessories whose serial number the dealer must enter when ticked (CR-03).
SERIAL_ACCESSORY_KEYS = ('battery', 'dock')


class SafexRmaPortal(CustomerPortal):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safex_dealer(self):
        return request.env.user.partner_id.commercial_partner_id

    def _safex_rma_domain(self):
        return [('partner_id', 'child_of', [self._safex_dealer().id])]

    def _safex_get_rma(self, rma_id):
        """Return the RMA in sudo after checking it belongs to the dealer's company."""
        rma_sudo = request.env['safex.rma'].sudo().browse(rma_id).exists()
        if not rma_sudo:
            raise MissingError(request.env._("This RMA does not exist."))
        if rma_sudo.partner_id.commercial_partner_id != self._safex_dealer():
            raise AccessError(request.env._("You are not allowed to access this RMA."))
        return rma_sudo

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'rma_count' in counters:
            values['rma_count'] = request.env['safex.rma'].sudo().search_count(
                self._safex_rma_domain() + [('state', 'not in', ('closed', 'cancel'))])
        return values

    def _safex_rma_filters(self):
        return {
            'all': {'label': request.env._("All"), 'domain': []},
            'submitted': {'label': request.env._("Submitted"), 'domain': [('state', '=', 'submitted')]},
            'inspection': {'label': request.env._("In Inspection"), 'domain': [('state', 'in', ('received', 'inspection'))]},
            'po_pending': {'label': request.env._("PO Pending"), 'domain': [('has_po_pending', '=', True)]},
            'in_repair': {'label': request.env._("In Repair"), 'domain': [('line_ids.state', 'in', ('in_repair', 'qc_testing'))]},
            'dispatched': {'label': request.env._("Dispatched"), 'domain': [('state', '=', 'dispatched')]},
            'closed': {'label': request.env._("Closed"), 'domain': [('state', '=', 'closed')]},
        }

    def _safex_rma_sortings(self):
        return {
            'name': {'label': request.env._("Reference"), 'order': 'name desc'},
            'date': {'label': request.env._("Received Date"), 'order': 'received_date desc'},
            'state': {'label': request.env._("Status"), 'order': 'state'},
        }

    # ------------------------------------------------------------------
    # RMA list
    # ------------------------------------------------------------------

    @http.route(['/my/rma', '/my/rma/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_rmas(self, page=1, sortby='name', filterby='all', **kw):
        filters = self._safex_rma_filters()
        sortings = self._safex_rma_sortings()
        filterby = filterby if filterby in filters else 'all'
        sortby = sortby if sortby in sortings else 'name'
        domain = self._safex_rma_domain() + filters[filterby]['domain']
        Rma = request.env['safex.rma'].sudo()
        pager = portal_pager(
            url='/my/rma',
            url_args={'sortby': sortby, 'filterby': filterby},
            total=Rma.search_count(domain),
            page=page,
            step=RMA_PER_PAGE,
        )
        rmas = Rma.search(domain, order=sortings[sortby]['order'], limit=RMA_PER_PAGE, offset=pager['offset'])
        request.session['my_rmas_history'] = rmas.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            'rmas': rmas,
            'page_name': 'safex_rma',
            'pager': pager,
            'default_url': '/my/rma',
            'searchbar_sortings': sortings,
            'sortby': sortby,
            'searchbar_filters': filters,
            'filterby': filterby,
        })
        return request.render('safex_portal_rma.portal_my_rmas', values)

    # ------------------------------------------------------------------
    # Device verification
    # ------------------------------------------------------------------

    @http.route('/my/verify', type='http', auth='user', website=True)
    def portal_verify_device(self, **kw):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'safex_verify'
        return request.render('safex_portal_rma.portal_verify_device', values)

    @staticmethod
    def _safex_read_upload(upload, max_size, allowed):
        """(name, bytes, mimetype) of an uploaded file, or None if empty. Raises ValueError when the
        file is too big or of a type not allowed (mimetype prefixes such as 'image/')."""
        if not upload or not upload.filename:
            return None
        data = upload.read(max_size + 1)
        mimetype = (upload.mimetype or '').lower()
        if not data:
            return None
        if len(data) > max_size or not any(mimetype.startswith(prefix) for prefix in allowed):
            raise ValueError(upload.filename)
        return upload.filename, data, mimetype

    def _safex_attach(self, record, files):
        return request.env['ir.attachment'].sudo().create([{
            'name': name, 'raw': data, 'mimetype': mimetype,
            'res_model': record._name, 'res_id': record.id,
        } for name, data, mimetype in files])

    def _safex_verify_throttled(self, count=1, limit=VERIFY_MAX_CALLS):
        """Per-session limit on device verification lookups: ``count`` more lookups are allowed while
        the session made fewer than ``limit`` in the last VERIFY_WINDOW seconds (shared by the Verify
        tool, Verify & Add and the RMA submission, which verifies every device again)."""
        now = time.time()
        calls = [stamp for stamp in request.session.get('safex_verify_calls', []) if now - stamp < VERIFY_WINDOW]
        throttled = len(calls) + count > limit
        if not throttled:
            calls.extend([now] * count)
        request.session['safex_verify_calls'] = calls
        return throttled

    @http.route('/my/rma/verify_device', type='json', auth='user', methods=['POST'])
    def portal_verify_device_json(self, serial_no=None, imei=None, **kw):
        if self._safex_verify_throttled():
            return {'verified': False, 'message': request.env._(
                "Too many verification attempts. Please wait a minute and try again.")}
        serial_no, imei = (str(serial_no or '').strip(), str(imei or '').strip())
        if not serial_no or not imei:
            return {'verified': False, 'message': request.env._(
                "Enter both the Serial Number and the IMEI (IMEI 1 or IMEI 2) of the device.")}
        if len(serial_no) > MAX_IDENTIFIER_LENGTH or len(imei) > MAX_IDENTIFIER_LENGTH:
            return {'verified': False, 'message': request.env._(
                "Device verification failed. This device was not found in your delivered purchases.")}
        result = request.env['stock.lot'].sudo().verify_device_for_portal(serial_no, imei, self._safex_dealer().id)
        keys = PORTAL_VERIFY_KEYS
        if result.get('status') == 'other_dealer':
            keys = tuple(key for key in keys if key != 'lot_id')  # the internal record id is not needed
        # Only these keys may ever leave the server.
        return {key: result[key] for key in keys if key in result}

    @http.route('/my/rma/verify_accessory', type='json', auth='user', methods=['POST'])
    def portal_verify_accessory_json(self, kind=None, serial_no=None, **kw):
        """Battery / docking station serial checked as soon as the dealer ticks the accessory (the RMA
        submission checks it again)."""
        if self._safex_verify_throttled():
            return {'verified': False, 'message': request.env._(
                "Too many verification attempts. Please wait a minute and try again.")}
        serial_no = str(serial_no or '').strip()
        if kind not in SERIAL_ACCESSORY_KEYS or not serial_no:
            return {'verified': False, 'message': request.env._("Enter the serial number.")}
        if len(serial_no) <= MAX_IDENTIFIER_LENGTH \
                and request.env['stock.lot'].sudo()._safex_accessory_serial_exists(kind, serial_no):
            return {'verified': True, 'serial_no': serial_no}
        if kind == 'battery':
            message = request.env._("Battery serial number %s was not found. Check the serial number printed "
                                    "on the battery and try again.", serial_no[:MAX_IDENTIFIER_LENGTH])
        else:
            message = request.env._("Docking Station serial number %s was not found. Check the serial number "
                                    "printed on the docking station and try again.", serial_no[:MAX_IDENTIFIER_LENGTH])
        return {'verified': False, 'message': message}

    # ------------------------------------------------------------------
    # RMA creation
    # ------------------------------------------------------------------

    def _safex_rma_new_render(self, error=None, error_serial=None, devices=None):
        """New RMA form. After a refused submission, the devices entered (``devices``) are given back
        to the form so that the dealer does not have to enter them again (only file inputs cannot be
        refilled by the browser)."""
        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'safex_rma_new',
            'error': error,
            'error_serial': (error_serial or '')[:128],
            'safex_devices': devices or [],
            # Internal record ids are not sent back to the browser.
            'safex_devices_json': json.dumps([
                {key: value for key, value in device.items() if key != 'lot_id'} for device in devices or []]),
        })
        return request.render('safex_portal_rma.portal_rma_new', values)

    @http.route('/my/rma/new', type='http', auth='user', website=True, methods=['GET'])
    def portal_rma_new(self, **kw):
        # Only known error codes are shown; no free text from the URL is echoed.
        error = kw.get('error')
        return self._safex_rma_new_render(error if error in NEW_RMA_ERRORS else None)

    @staticmethod
    def _safex_read_device_form(post, idx):
        """Values of one device card of the New RMA form, as entered by the dealer."""
        device = {
            'index': idx,
            'serial': (post.get(f'serial_{idx}') or '').strip()[:MAX_IDENTIFIER_LENGTH],
            'imei': (post.get(f'imei_{idx}') or '').strip()[:MAX_IDENTIFIER_LENGTH],
            'product_name': '',
            'lot_id': False,
            'distributor': '',
            # CR-04: the dealer clicked "Proceed to RMA" for a device sold through another dealer.
            'other_dealer_confirmed': '1' if post.get(f'other_dealer_confirmed_{idx}') else '',
        }
        for name in ('customer_name', 'customer_company', 'complaint', 'acc_other',
                     *(f'acc_{key}_sno' for key in SERIAL_ACCESSORY_KEYS)):
            device[name] = (post.get(f'{name}_{idx}') or '').strip()
        for key in ACCESSORY_KEYS:
            device[f'acc_{key}'] = bool(post.get(f'acc_{key}_{idx}'))
        return device

    @http.route('/my/rma/new', type='http', auth='user', website=True, methods=['POST'])
    def portal_rma_create(self, **post):
        dealer = self._safex_dealer()
        form = request.httprequest.form
        files = request.httprequest.files
        devices = [
            device for device in (self._safex_read_device_form(post, idx) for idx in form.getlist('device_index'))
            if device['serial'] or device['imei']
        ]

        def refuse(error, error_serial=None):
            # Re-render the form with the devices entered instead of redirecting to an empty form.
            return self._safex_rma_new_render(error, error_serial, devices)

        if len(devices) > MAX_DEVICES_PER_RMA:
            devices = devices[:MAX_DEVICES_PER_RMA]
            return refuse('too_many')
        # Every device is verified again: the lookups count in the session's verification limit.
        if self._safex_verify_throttled(len(devices), SUBMIT_MAX_VERIFICATIONS):
            return refuse('throttled')

        lines = []
        photos_by_lot = {}
        seen_lot_ids = set()
        Lot = request.env['stock.lot'].sudo()
        checks = []
        for device in devices:
            check = Lot.verify_device_for_portal(device['serial'], device['imei'], dealer.id)
            checks.append(check)
            if check.get('verified'):
                # Shown as the device title if the form has to be displayed again.
                # The other dealer's name is only given back for a device the dealer confirmed (popup).
                device.update(product_name=check.get('product_name') or '', lot_id=check['lot_id'],
                              distributor=(check.get('distributor') or '') if device['other_dealer_confirmed'] else '')
        for device, check in zip(devices, checks):
            idx = device['index']
            if not check.get('verified') or not device['complaint']:
                return refuse('device')
            if check.get('status') == 'other_dealer' and not device['other_dealer_confirmed']:
                # Sold through another dealer: allowed only once the dealer confirmed it (popup).
                return refuse('other_dealer', device['serial'])
            if check['lot_id'] in seen_lot_ids:
                return refuse('duplicate')
            seen_lot_ids.add(check['lot_id'])
            try:
                photos = [photo for photo in (
                    self._safex_read_upload(upload, PHOTO_MAX_SIZE, ('image/',))
                    for upload in files.getlist(f'photos_{idx}')) if photo]
            except ValueError:
                return refuse('photo')
            if len(photos) > PHOTO_MAX_COUNT:
                return refuse('photo')
            photos_by_lot[check['lot_id']] = photos
            vals = {
                'lot_id': check['lot_id'],
                'complaint_description': device['complaint'],
                'end_customer_name': device['customer_name'] or False,
                'end_customer_company': device['customer_company'] or False,
                'acc_declared_other': device['acc_other'] or False,
            }
            for key in ACCESSORY_KEYS:
                vals[f'acc_declared_{key}'] = device[f'acc_{key}']
            for key in SERIAL_ACCESSORY_KEYS:
                if not vals[f'acc_declared_{key}']:
                    continue
                accessory_serial = device[f'acc_{key}_sno']
                if not accessory_serial:
                    return refuse('accessory_serial_missing')
                # Any battery / dock serial known in a SafeX company is accepted, not only the device's own.
                if not Lot._safex_accessory_serial_exists(key, accessory_serial):
                    return refuse(f'{key}_serial', accessory_serial)
                vals[f'acc_declared_{key}_sno'] = accessory_serial
            lines.append((0, 0, vals))
        if not lines:
            return refuse('empty')
        # The RMA is created in the company handling the RMAs of the company that sold the devices
        # ("RMAs Handled By", e.g. SafeX Qatar for SafeX UK): devices sold by different SafeX companies,
        # to this dealer or through another dealer, go on the same RMA. The devices are then put on the
        # RMA with their serial record of that company (see safex.rma.line.create).
        companies = request.env['res.company'].sudo()
        for company in Lot.browse([vals['lot_id'] for _cmd, _id, vals in lines]).company_id:
            companies |= company._get_safex_rma_company()
        if len(companies) > 1:
            # Only when "RMAs Handled By" is not set up on the SafeX companies.
            return refuse('mixed_company', ", ".join(companies.mapped('name')))
        try:
            # Savepoint: a refused RMA must not stay half-created when we redirect back to the form.
            with request.env.cr.savepoint():
                confirmed = [check['lot_id'] for check in checks if check.get('status') == 'other_dealer']
                rma = request.env['safex.rma'].sudo().with_context(
                    safex_portal_other_dealer_confirmed=confirmed).create({
                    'partner_id': dealer.id,
                    'company_id': companies.id or request.env.company.id,
                    'created_from_portal': True,
                    'user_id': False,  # the default would be the dealer's portal user
                    'line_ids': lines,
                })
                for line in rma.line_ids:
                    photos = photos_by_lot.get(line.lot_id.id)
                    if photos:
                        line.complaint_photo_ids = [Command.set(self._safex_attach(line, photos).ids)]
                rma.action_submit()
        except ValidationError:
            # A device is already on another open RMA
            return refuse('duplicate')
        except UserError:
            # The handling company has no product for a device sold by another SafeX company.
            return refuse('unavailable')
        return request.redirect(f'/my/rma/{rma.id}?message=created')

    # ------------------------------------------------------------------
    # RMA detail, quotation actions & PO
    # ------------------------------------------------------------------

    @http.route('/my/rma/<int:rma_id>', type='http', auth='user', website=True)
    def portal_rma_detail(self, rma_id, message=None, **kw):
        try:
            rma_sudo = self._safex_get_rma(rma_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        orders = rma_sudo.sale_order_ids.filtered(lambda so: so.state != 'cancel')
        values = self._prepare_portal_layout_values()
        values.update({
            'rma': rma_sudo,
            'orders': orders,
            'invoices': rma_sudo.invoice_ids.filtered(lambda move: move.state == 'posted'),
            'quotation_open': any(so.state in ('draft', 'sent') for so in orders) and bool(rma_sudo.quote_sent_date),
            'page_name': 'safex_rma_detail',
            'message': message,
            'error': kw.get('error'),
        })
        values = self._get_page_view_values(
            rma_sudo, rma_sudo._portal_ensure_token(), values, 'my_rmas_history', False)
        return request.render('safex_portal_rma.portal_rma_detail', values)

    @http.route('/my/rma/<int:rma_id>/action', type='http', auth='user', website=True, methods=['POST'])
    def portal_rma_action(self, rma_id, action=None, reason=None, line_id=None, **kw):
        rma_sudo = self._safex_get_rma(rma_id)
        reason = (reason or '').strip()
        try:
            if action == 'approve':
                rma_sudo.action_dealer_approve()
            elif action == 'reject':
                line = rma_sudo.line_ids.filtered(lambda l: l.id == int(line_id or 0))
                if not line:
                    raise UserError(request.env._("Select the device to reject."))
                line.action_reject(reason)
                line.message_post(body=request.env._("Rejected by dealer: %s", reason),
                                  author_id=request.env.user.partner_id.id)
                rma_sudo.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=request.env._("Device rejected by dealer"),
                    note=request.env._("%(device)s: %(reason)s", device=line.display_name, reason=reason),
                    user_id=rma_sudo._get_safex_responsible().id)
            elif action == 'clarify':
                rma_sudo.action_dealer_request_clarification(reason, author=request.env.user.partner_id)
            elif action == 'received':
                rma_sudo.action_dealer_confirm_receipt(request.env.user)
            else:
                raise UserError(request.env._("Unknown action."))
        except UserError:
            return request.redirect(f'/my/rma/{rma_id}?error=action')
        return request.redirect(f'/my/rma/{rma_id}?message={action}')

    @http.route('/my/rma/<int:rma_id>/submit_po', type='http', auth='user', website=True, methods=['POST'])
    def portal_rma_submit_po(self, rma_id, po_number=None, **kw):
        """PO number (required) + PO document (optional: the dealer may email it to SafeX instead):
        emailed to the company's PO mailbox and kept on the RMA. Repair starts only once SafeX has
        verified the PO (CR-09)."""
        rma_sudo = self._safex_get_rma(rma_id)
        po_number = (po_number or '').strip()
        if not po_number:
            return request.redirect(f'/my/rma/{rma_id}?error=po')
        try:
            po_file = self._safex_read_upload(
                request.httprequest.files.get('po_file'), PO_MAX_SIZE, ('application/pdf', 'image/'))
        except ValueError:
            return request.redirect(f'/my/rma/{rma_id}?error=po_file')
        try:
            with request.env.cr.savepoint():
                attachment = self._safex_attach(rma_sudo, [po_file]) if po_file else None
                rma_sudo.action_dealer_submit_po(
                    po_number, attachments=attachment, author=request.env.user.partner_id)
        except UserError:
            return request.redirect(f'/my/rma/{rma_id}?error=po')
        return request.redirect(f'/my/rma/{rma_id}?message=po')

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    @http.route('/my/rma/<int:rma_id>/report/<string:document>', type='http', auth='user', website=True)
    def portal_rma_report(self, rma_id, document, order_id=None, **kw):
        rma_sudo = self._safex_get_rma(rma_id)
        if document == 'reference':
            return self._show_report(rma_sudo, 'pdf', 'safex_rma_reports.action_report_rma_reference', download=True)
        if document == 'packing_list' and rma_sudo.state in ('dispatched', 'closed'):
            return self._show_report(
                rma_sudo, 'pdf', 'safex_rma_reports.action_report_outbound_packing_list', download=True)
        if document == 'final_service' and rma_sudo.state in ('dispatched', 'closed'):
            return self._show_report(
                rma_sudo, 'pdf', 'safex_rma_reports.action_report_rma_final_service', download=True)
        if document == 'quotation':
            order = rma_sudo.sale_order_ids.filtered(lambda so: so.id == int(order_id or 0))
            if order:
                return self._show_report(
                    order, 'pdf', 'safex_rma_reports.action_report_sectioned_repair_quotation', download=True)
        if document == 'invoice':
            invoice = rma_sudo.invoice_ids.filtered(lambda move: move.id == int(order_id or 0) and move.state == 'posted')
            if invoice:
                return self._show_report(invoice, 'pdf', 'account.account_invoices', download=True)
        raise MissingError(request.env._("This document is not available."))
