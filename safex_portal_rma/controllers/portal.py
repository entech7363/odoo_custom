import time

from odoo import Command, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager

RMA_PER_PAGE = 10
# Warranty data, stock, locations and costs are never sent to dealers.
PORTAL_VERIFY_KEYS = ('verified', 'message', 'lot_id', 'serial_no', 'product_name', 'delivery_date', 'last_rma')
PHOTO_MAX_COUNT = 5
PHOTO_MAX_SIZE = 5 * 1024 * 1024
PO_MAX_SIZE = 10 * 1024 * 1024
VERIFY_MAX_CALLS = 20  # a dealer adding devices to an RMA verifies each one
VERIFY_WINDOW = 60  # seconds
ACCESSORY_KEYS = ('charger', 'dock', 'battery', 'screwdriver', 'cable', 'box')


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

    def _safex_verify_throttled(self):
        """Simple per-session limit on device verification lookups (VERIFY_MAX_CALLS per window)."""
        now = time.time()
        calls = [stamp for stamp in request.session.get('safex_verify_calls', []) if now - stamp < VERIFY_WINDOW]
        throttled = len(calls) >= VERIFY_MAX_CALLS
        if not throttled:
            calls.append(now)
        request.session['safex_verify_calls'] = calls
        return throttled

    @http.route('/my/rma/verify_device', type='json', auth='user', methods=['POST'])
    def portal_verify_device_json(self, serial_no=None, imei=None, **kw):
        if self._safex_verify_throttled():
            return {'verified': False, 'message': request.env._(
                "Too many verification attempts. Please wait a minute and try again.")}
        if not (serial_no or '').strip() or not (imei or '').strip():
            return {'verified': False, 'message': request.env._(
                "Enter both the Serial Number and the IMEI (IMEI 1 or IMEI 2) of the device.")}
        result = request.env['stock.lot'].sudo().verify_device_for_portal(serial_no, imei, self._safex_dealer().id)
        # Only these keys may ever leave the server.
        return {key: result[key] for key in PORTAL_VERIFY_KEYS if key in result}

    # ------------------------------------------------------------------
    # RMA creation
    # ------------------------------------------------------------------

    @http.route('/my/rma/new', type='http', auth='user', website=True, methods=['GET'])
    def portal_rma_new(self, **kw):
        values = self._prepare_portal_layout_values()
        values.update({'page_name': 'safex_rma_new', 'error': kw.get('error')})
        return request.render('safex_portal_rma.portal_rma_new', values)

    @http.route('/my/rma/new', type='http', auth='user', website=True, methods=['POST'])
    def portal_rma_create(self, **post):
        dealer = self._safex_dealer()
        form = request.httprequest.form
        files = request.httprequest.files
        lines = []
        photos_by_lot = {}
        seen_lot_ids = set()
        for idx in form.getlist('device_index'):
            serial = (post.get(f'serial_{idx}') or '').strip()
            imei = (post.get(f'imei_{idx}') or '').strip()
            complaint = (post.get(f'complaint_{idx}') or '').strip()
            if not serial and not imei:
                continue
            check = request.env['stock.lot'].sudo().verify_device_for_portal(serial, imei, dealer.id)
            if not check.get('verified') or not complaint:
                return request.redirect('/my/rma/new?error=device')
            if check['lot_id'] in seen_lot_ids:
                return request.redirect('/my/rma/new?error=duplicate')
            seen_lot_ids.add(check['lot_id'])
            try:
                photos = [photo for photo in (
                    self._safex_read_upload(upload, PHOTO_MAX_SIZE, ('image/',))
                    for upload in files.getlist(f'photos_{idx}')) if photo]
            except ValueError:
                return request.redirect('/my/rma/new?error=photo')
            if len(photos) > PHOTO_MAX_COUNT:
                return request.redirect('/my/rma/new?error=photo')
            photos_by_lot[check['lot_id']] = photos
            vals = {
                'lot_id': check['lot_id'],
                'complaint_description': complaint,
                'end_customer_name': post.get(f'customer_name_{idx}') or False,
                'end_customer_company': post.get(f'customer_company_{idx}') or False,
                'acc_declared_other': post.get(f'acc_other_{idx}') or False,
            }
            for key in ACCESSORY_KEYS:
                vals[f'acc_declared_{key}'] = bool(post.get(f'acc_{key}_{idx}'))
            lines.append((0, 0, vals))
        if not lines:
            return request.redirect('/my/rma/new?error=empty')
        lot = request.env['stock.lot'].sudo().browse(lines[0][2]['lot_id'])
        try:
            # Savepoint: a refused RMA must not stay half-created when we redirect back to the form.
            with request.env.cr.savepoint():
                rma = request.env['safex.rma'].sudo().create({
                    'partner_id': dealer.id,
                    'company_id': lot.company_id.id or request.env.company.id,
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
            return request.redirect('/my/rma/new?error=duplicate')
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
        rma_sudo = self._safex_get_rma(rma_id)
        try:
            po_file = self._safex_read_upload(
                request.httprequest.files.get('po_file'), PO_MAX_SIZE, ('application/pdf', 'image/'))
        except ValueError:
            return request.redirect(f'/my/rma/{rma_id}?error=po_file')
        try:
            rma_sudo.action_submit_po((po_number or '').strip())
        except UserError:
            return request.redirect(f'/my/rma/{rma_id}?error=po')
        if po_file:
            attachment = self._safex_attach(rma_sudo, [po_file])
            rma_sudo.po_document_ids = [Command.link(attachment.id)]
            rma_sudo.message_post(
                body=request.env._("PO document uploaded by the dealer for PO %s.", rma_sudo.po_number),
                attachment_ids=attachment.ids, author_id=request.env.user.partner_id.id)
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
