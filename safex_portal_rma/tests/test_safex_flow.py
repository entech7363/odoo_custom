"""End-to-end functional test of the SafeX RMA flow (BRD 1-11, DES00103-DES00113).

Written to run unchanged on the Odoo 20 and the Odoo 18 versions of the modules, so both can be
compared scenario by scenario. Version differences are kept in the small helpers below.
"""
from dateutil.relativedelta import relativedelta

from odoo import Command, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'safex_flow')
class TestSafexFlow(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.warehouse = env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.company.write({'safex_dealer_warranty_months': 16, 'safex_factory_warranty_months': 18})

        cls.dealer = env['res.partner'].create({
            'name': 'SafeX Test Dealer LLC', 'is_company': True, 'is_safex_dealer': True,
            'email': 'dealer@example.com'})
        cls.dealer_contact = env['res.partner'].create({
            'name': 'Dealer Contact', 'parent_id': cls.dealer.id, 'email': 'contact@example.com'})
        cls.other_dealer = env['res.partner'].create({
            'name': 'Other Dealer LLC', 'is_company': True, 'is_safex_dealer': True})
        cls.portal_user = new_test_user(
            env, login='safex_dealer_portal', groups='base.group_portal', partner_id=cls.dealer_contact.id)
        cls.other_portal_user = new_test_user(
            env, login='safex_other_portal', groups='base.group_portal',
            partner_id=env['res.partner'].create({'name': 'Other Contact', 'parent_id': cls.other_dealer.id}).id)

        cls.device = env['product.product'].create(cls._storable({
            'name': 'Ex Mobile Test Device', 'tracking': 'serial', 'company_id': False}))
        cls.spare = env['product.product'].create(cls._storable({
            'name': 'Test Display Assembly', 'is_safex_spare_part': True, 'standard_price': 50.0,
            'company_id': False}))
        if 'minimum_price' in cls.spare._fields:
            # sale_price_control (Entech): parts are quoted at 0.00, below this minimum price
            cls.spare.minimum_price = 40.0
        env['stock.quant']._update_available_quantity(cls.spare, cls.stock_location, 10)

        cls.serials = ['SFXT0001', 'SFXT0002', 'SFXT0003', 'SFXT0004', 'SFXT0005']
        cls.imeis = ['3500000000000%02d' % i for i in range(1, 6)]
        cls.lots = env['stock.lot'].create([{
            'name': serial, 'product_id': cls.device.id, 'company_id': cls.company.id, 'imei_1': imei,
        } for serial, imei in zip(cls.serials, cls.imeis)])
        cls._receive(cls.lots)
        cls._deliver(cls.lots, cls.dealer)

    # ------------------------------------------------------------------
    # Version helpers
    # ------------------------------------------------------------------

    @classmethod
    def _storable(cls, vals):
        vals['type'] = 'consu'
        if 'is_storable' in cls.env['product.product']._fields:
            vals['is_storable'] = True
        return vals

    @staticmethod
    def _is_scrap_location(location):
        # Odoo 18: boolean scrap_location; Odoo 19+: scrap locations are usage 'inventory'
        if 'scrap_location' in location._fields:
            return location.scrap_location
        return location.usage == 'inventory'

    def _csrf_token(self):
        # Odoo 18: odoo.http.Request; Odoo 19+: odoo.http.requestlib.Request
        request_cls = getattr(http, 'Request', None) or http.requestlib.Request
        return request_cls.csrf_token(self)

    @classmethod
    def _move_vals(cls, vals):
        if 'name' in cls.env['stock.move']._fields:
            vals['name'] = cls.device.name
        return vals

    @classmethod
    def _picking(cls, picking_type, partner, src, dest, qty):
        picking = cls.env['stock.picking'].create({
            'picking_type_id': picking_type.id, 'partner_id': partner.id,
            'location_id': src.id, 'location_dest_id': dest.id,
            'move_ids': [Command.create(cls._move_vals({
                'product_id': cls.device.id, 'product_uom_qty': qty,
                'location_id': src.id, 'location_dest_id': dest.id}))],
        })
        picking.action_confirm()
        return picking

    @classmethod
    def _receive(cls, lots):
        supplier = cls.env.ref('stock.stock_location_suppliers')
        vendor = cls.env['res.partner'].create({'name': 'Factory Vendor'})
        picking = cls._picking(cls.warehouse.in_type_id, vendor, supplier, cls.stock_location, len(lots))
        move = picking.move_ids
        move.move_line_ids.unlink()
        has_imei = 'imei_no_1' in cls.env['stock.move.line']._fields
        for lot in lots:
            vals = {
                'move_id': move.id, 'picking_id': picking.id, 'product_id': cls.device.id, 'lot_id': lot.id,
                'quantity': 1, 'location_id': supplier.id, 'location_dest_id': cls.stock_location.id}
            if has_imei:
                # Entech process: the IMEI is typed on the receipt line and copied to the serial
                vals['imei_no_1'] = lot.imei_1
            cls.env['stock.move.line'].create(vals)
        move.picked = True
        picking.button_validate()
        assert picking.state == 'done', picking.state

    @classmethod
    def _deliver(cls, lots, partner):
        customers = cls.env.ref('stock.stock_location_customers')
        picking = cls._picking(cls.warehouse.out_type_id, partner, cls.stock_location, customers, len(lots))
        picking.action_assign()
        picking.move_ids.picked = True
        picking.button_validate()
        assert picking.state == 'done', picking.state
        assert set(picking.move_line_ids.lot_id.ids) == set(lots.ids)

    def _fill_checklist(self, line, damage=False):
        for result in line.inspection_line_ids:
            options = result.item_id.option_ids
            if damage and result.item_id == line.inspection_line_ids[:1].item_id:
                result.option_id = options.filtered('requires_photo')[:1]
            elif not result.option_id or result.option_id.requires_photo:
                result.option_id = options.filtered(lambda o: not o.requires_photo)[:1]

    def _photo(self, name='photo.png'):
        return self.env['ir.attachment'].create({'name': name, 'raw': b'\x89PNG fake', 'mimetype': 'image/png'})

    def _messages(self, record, text):
        return record.message_ids.filtered(lambda m: text in (m.subject or '') or text in (m.body or ''))

    def _create_rma(self, lots, complaint='Device does not power on'):
        return self.env['safex.rma'].create({
            'partner_id': self.dealer.id,
            'company_id': self.company.id,
            'line_ids': [Command.create({
                'lot_id': lot.id, 'complaint_description': complaint,
                'acc_declared_charger': True, 'acc_declared_battery': True,
            }) for lot in lots],
        })

    # ------------------------------------------------------------------
    # 1. Warranty clocks & verification
    # ------------------------------------------------------------------

    def test_01_warranty_clocks(self):
        today = fields.Date.context_today(self.lots[0])
        for lot in self.lots:
            self.assertEqual(lot.imei_1, self.imeis[self.lots.ids.index(lot.id)])
            self.assertEqual(lot.factory_grn_date, today, "Receipt starts the factory warranty")
            self.assertEqual(lot.factory_warranty_months, 18)
            self.assertEqual(lot.factory_warranty_expiry, today + relativedelta(months=18))
            self.assertEqual(lot.dealer_delivery_date, today, "Delivery to the dealer starts the dealer warranty")
            self.assertEqual(lot.dealer_warranty_months, 16)
            self.assertEqual(lot.dealer_warranty_expiry, today + relativedelta(months=16))
            self.assertTrue(lot._is_under_dealer_warranty())

    def test_02_internal_entity_delivery_ignored(self):
        lot = self.env['stock.lot'].create({
            'name': 'SFXT-INTERNAL', 'product_id': self.device.id, 'company_id': self.company.id,
            'imei_1': '350000000000099'})
        self._receive(lot)
        uk = self.env['res.partner'].create({'name': 'SafeX UK (test)', 'is_company': True,
                                             'is_safex_internal_entity': True})
        self._deliver(lot, uk)
        self.assertFalse(lot.dealer_delivery_date, "Inter-company sales do not start the dealer warranty")
        result = self.env['stock.lot'].verify_device_for_portal('SFXT-INTERNAL', '350000000000099', uk.id)
        self.assertFalse(result['verified'])

    def test_03_device_verification(self):
        Lot = self.env['stock.lot']
        ok = Lot.verify_device_for_portal(self.serials[0], self.imeis[0], self.dealer_contact.id)
        self.assertTrue(ok['verified'])
        self.assertEqual(ok['lot_id'], self.lots[0].id)
        self.assertEqual(set(ok), {'verified', 'lot_id', 'product_name'}, "No stock or warranty data exposed")
        self.assertFalse(Lot.verify_device_for_portal(self.serials[0], '000', self.dealer.id)['verified'])
        self.assertFalse(Lot.verify_device_for_portal(self.serials[0], self.imeis[1], self.dealer.id)['verified'])
        self.assertFalse(Lot.verify_device_for_portal(self.serials[0], self.imeis[0], self.other_dealer.id)['verified'],
                         "A device delivered to another dealer cannot be verified")
        self.assertFalse(Lot.verify_device_for_portal('', '', self.dealer.id)['verified'])
        self.lots[1].imei_2 = '350000000000777'
        self.assertTrue(Lot.verify_device_for_portal(self.serials[1], '350000000000777', self.dealer.id)['verified'],
                        "IMEI 2 is accepted too")

    # ------------------------------------------------------------------
    # 2. Full RMA lifecycle
    # ------------------------------------------------------------------

    def test_10_full_rma_lifecycle(self):
        lot_warranty, lot_paid, lot_nff, lot_rejected = self.lots[:4]
        lot_paid.dealer_delivery_date = fields.Date.today() - relativedelta(months=20)
        self.assertFalse(lot_paid._is_under_dealer_warranty())
        rma = self._create_rma(lot_warranty | lot_paid | lot_nff | lot_rejected)
        line_w, line_p, line_n, line_r = rma.line_ids.sorted(lambda l: self.lots.ids.index(l.lot_id.id))
        self.assertTrue(rma.name.startswith('RMA/'), rma.name)
        self.assertEqual(rma.state, 'draft')
        self.assertEqual(len(line_w.inspection_line_ids), self.env['safex.inspection.item'].search_count([]),
                         "Every active checklist item is added to the device")
        self.assertFalse(line_p.under_dealer_warranty)
        self.assertTrue(line_w.under_dealer_warranty)

        # Submit -> email with shipping instructions
        rma.action_submit()
        self.assertEqual(rma.state, 'submitted')
        self.assertTrue(self._messages(rma, 'registered - shipping instructions'))
        with self.assertRaises(UserError):
            rma.action_submit()

        # Receiving: AWB mandatory
        with self.assertRaises(UserError):
            rma.action_confirm_receipt()
        rma.write({'inbound_awb': 'AWB-IN-1', 'shipment_mode': 'air', 'package_condition': 'intact'})
        rma.action_confirm_receipt()
        self.assertEqual(rma.state, 'received')
        self.assertEqual(rma.receiving_user_id, self.env.user)

        # Accessories: battery declared but not received -> discrepancy
        rma.line_ids.write({'acc_received_charger': True, 'acc_received_battery': True})
        line_r.acc_received_battery = False
        self.assertTrue(line_r.accessory_discrepancy)
        self.assertFalse(line_w.accessory_discrepancy)

        # Physical inspection: cannot complete the RMA while a device is still draft
        with self.assertRaises(UserError):
            rma.action_complete_physical_inspection()
        # Damage option chosen without a photo -> blocked; with a photo -> suggested classification applied
        self._fill_checklist(line_r, damage=True)
        self.assertTrue(line_r.physical_damage_suspected)
        with self.assertRaises(UserError):
            line_r.action_validate_physical_inspection()
        line_r.inspection_photo_ids = [Command.link(self._photo().id)]
        suggested = line_r.inspection_line_ids.option_id.filtered('suggested_classification')[:1]
        line_r.action_validate_physical_inspection()
        self.assertEqual(line_r.state, 'inspected')
        if suggested:
            self.assertEqual(line_r.warranty_classification, suggested.suggested_classification)
        for line in line_w | line_p | line_n:
            self._fill_checklist(line)
            line.action_validate_physical_inspection()
            self.assertEqual(line.state, 'inspected')
        rma.action_complete_physical_inspection()
        self.assertEqual(rma.state, 'inspection')
        self.assertTrue(self._messages(rma, 'Accessory discrepancy'))

        # Technical inspection: mandatory fields, then routing per classification
        technician = self.env.user
        with self.assertRaises(UserError):
            line_w.action_validate_technical_inspection()
        common = {'technician_id': technician.id, 'dealer_facing_report': 'Diagnosed'}
        line_w.write(dict(common, warranty_classification='under_warranty', fault_category='display'))
        line_p.write(dict(common, warranty_classification='out_of_warranty', fault_category='display',
                          service_charge_amount=250.0))
        line_n.write(dict(common, warranty_classification='no_fault_found'))
        line_r.write(dict(common, warranty_classification='physical_damage', fault_category='housing_seal',
                          service_charge_amount=400.0))
        (line_w | line_p | line_n | line_r).action_validate_technical_inspection()
        self.assertEqual(line_w.state, 'in_repair', "Under warranty: free repair")
        self.assertEqual(line_p.state, 'quoted', "Out of warranty: quotation")
        self.assertEqual(line_n.state, 'qc_testing', "No fault found: returned as-is via QC")
        self.assertEqual(line_r.state, 'quoted')
        self.assertTrue(line_p.is_chargeable and line_r.is_chargeable)
        self.assertFalse(line_w.is_chargeable or line_n.is_chargeable)
        self.assertEqual(lot_paid.warranty_classification, 'out_of_warranty', "Classification written to the serial")
        self.assertEqual(rma.state, 'processing')

        # Spare part on the chargeable device
        line_p.part_line_ids = [Command.create({'product_id': self.spare.id, 'quantity': 1})]
        part = line_p.part_line_ids
        self.assertEqual(part.location_id, self.stock_location)
        self.assertEqual(part.local_stock_available, 10)

        # Quotation: one section per chargeable device, one priced service line, parts at 0.00
        rma.action_generate_quotation()
        order = rma.sale_order_ids
        self.assertEqual(len(order), 1)
        self.assertEqual(order.rma_id, rma)
        sections = order.order_line.filtered(lambda l: l.display_type == 'line_section')
        self.assertEqual(len(sections), 2)
        service_lines = order.order_line.filtered('is_service_charge')
        self.assertEqual(sorted(service_lines.mapped('price_unit')), [250.0, 400.0])
        part_lines = order.order_line.filtered('is_spare_part')
        self.assertEqual(len(part_lines), 1)
        self.assertEqual(part_lines.price_unit, 0.0)
        self.assertEqual(order.amount_untaxed, 650.0)
        with self.assertRaises(UserError):
            rma.action_generate_quotation()

        # Send to the portal -> email with the quotation PDF
        rma.action_send_quotation()
        self.assertEqual(order.state, 'sent')
        self.assertTrue(rma.quote_sent_date)
        quote_mail = self._messages(rma, 'repair quotation ready')
        self.assertTrue(quote_mail)
        self.assertTrue(quote_mail.attachment_ids, "Quotation PDF attached")

        # Dealer rejects one device: reason mandatory, section removed, total recalculated
        with self.assertRaises(UserError):
            line_r.action_reject('')
        line_r.action_reject('Too expensive')
        self.assertEqual(line_r.state, 'rejected')
        self.assertFalse(order.order_line.filtered(lambda l: l.rma_line_id == line_r))
        self.assertEqual(order.amount_untaxed, 250.0)

        # Clarification: reason mandatory, To-Do for the responsible
        with self.assertRaises(UserError):
            rma.action_dealer_request_clarification('')
        rma.action_dealer_request_clarification('Why is the display replaced?')
        self.assertTrue(rma.activity_ids.filtered(lambda a: a.summary == 'Dealer clarification requested'))

        # Dealer approves: order confirmed (parts at 0.00 do not need a price approval), PO pending
        rma.action_dealer_approve()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(line_p.state, 'po_pending')
        self.assertTrue(rma.has_po_pending)
        self.assertTrue(rma.po_pending_since)
        self.assertTrue(self._messages(rma, 'PO number required'))
        self.assertFalse(order.picking_ids.move_ids.filtered(lambda m: m.product_id == self.spare),
                         "The 0.00 part line never creates a delivery")

        # PO reminders: days 7/14/30/40 after approval, each milestone sent once
        rma.po_pending_since = fields.Datetime.now() - relativedelta(days=15)
        rma._cron_send_po_pending_reminders()
        self.assertEqual(rma.last_reminder_day, 14)
        self.assertEqual(len(self._messages(rma, 'waiting for your PO number')), 1)
        rma._cron_send_po_pending_reminders()
        self.assertEqual(len(self._messages(rma, 'waiting for your PO number')), 1, "No duplicate reminder")

        # PO number releases the devices
        with self.assertRaises(UserError):
            rma.action_submit_po('  ')
        rma.action_submit_po('PO-778')
        self.assertEqual(line_p.state, 'in_repair')
        self.assertFalse(rma.has_po_pending)
        self.assertEqual(order.client_order_ref, 'PO-778')
        if 'Customer_Purchase' in order._fields:
            self.assertEqual(order.Customer_Purchase, 'PO-778', "Entech PO Number filled too")
            self.assertTrue(order.Customer_Purchase_date)
        self.assertEqual(rma.last_reminder_day, 0)

        # Repair: work description mandatory, parts consumed to scrap on completion
        with self.assertRaises(UserError):
            line_p.action_complete_repair()
        (line_w | line_p).write({'repair_work_done': 'Display replaced'})
        (line_w | line_p).action_complete_repair()
        self.assertEqual(line_p.state, 'qc_testing')
        self.assertTrue(part.consumed)
        self.assertEqual(part.stock_move_id.state, 'done')
        self.assertTrue(self._is_scrap_location(part.stock_move_id.location_dest_id))
        self.assertEqual(self.spare.with_context(location=self.stock_location.id).qty_available, 9)

        # Dispatch blocked until every device passed QC
        rma.outbound_awb = 'AWB-OUT-1'
        with self.assertRaises(ValidationError):
            rma.action_dispatch()

        # QC failure sends the device back to repair
        line_w.write({'final_test_result': 'failed', 'quality_check': 'passed'})
        line_w.action_qc_validate()
        self.assertEqual(line_w.state, 'in_repair')
        line_w.action_complete_repair()
        with self.assertRaises(UserError):
            line_w.action_qc_validate()
        (line_w | line_p | line_n).write({'final_test_result': 'passed', 'quality_check': 'passed'})
        (line_w | line_p | line_n).action_qc_validate()
        for line in line_w | line_p | line_n:
            self.assertEqual(line.state, 'ready')
            self.assertEqual(line.lot_id.last_rma_number, rma.name, "Service history written to the serial")
        self.assertTrue(rma.can_dispatch)

        # Freight: manufacturing defect -> factory pays
        self.assertEqual(rma.freight_payer, 'partner')
        line_p.is_manufacturing_defect = True
        self.assertEqual(rma.freight_payer, 'factory')

        # Dispatch: AWB mandatory, email with tracking
        rma.outbound_awb = False
        with self.assertRaises(UserError):
            rma.action_dispatch()
        rma.outbound_awb = 'AWB-OUT-1'
        rma.action_dispatch()
        self.assertEqual(rma.state, 'dispatched')
        self.assertTrue(self._messages(rma, 'dispatched - AWB AWB-OUT-1'))

        # Invoice for the chargeable repair
        rma.action_create_invoice()
        self.assertEqual(rma.invoice_count, 1)
        self.assertEqual(rma.invoice_ids.amount_untaxed, 250.0)

        rma.action_close()
        self.assertEqual(rma.state, 'closed')

        # Repeat device on a new RMA
        rma2 = self._create_rma(lot_warranty)
        self.assertTrue(rma2.line_ids.is_repeat_device)
        self.assertEqual(rma2.line_ids.last_rma_number, rma.name)
        self.assertIn(rma.name, rma2.line_ids.repeat_repair_warning)
        self.assertEqual(lot_warranty.rma_count, 2)

        # PDFs render
        Report = self.env['ir.actions.report']
        for xmlid, record in (
            ('safex_rma_reports.action_report_rma_reference', rma),
            ('safex_rma_reports.action_report_outbound_packing_list', rma),
            ('safex_rma_reports.action_report_sectioned_repair_quotation', order),
        ):
            html = Report._render_qweb_html(xmlid, record.ids)[0].decode()
            self.assertIn(rma.name, html, xmlid)

    def test_11_po_before_approval_releases_immediately(self):
        lot = self.lots[4]
        lot.dealer_delivery_date = fields.Date.today() - relativedelta(months=20)
        rma = self._create_rma(lot)
        line = rma.line_ids
        rma.action_submit()
        rma.inbound_awb = 'AWB-2'
        rma.action_confirm_receipt()
        self._fill_checklist(line)
        line.action_validate_physical_inspection()
        rma.action_complete_physical_inspection()
        line.write({'technician_id': self.env.uid, 'dealer_facing_report': 'x', 'fault_category': 'battery',
                    'warranty_classification': 'out_of_warranty', 'service_charge_amount': 100.0})
        line.action_validate_technical_inspection()
        rma.action_generate_quotation()
        rma.po_number = 'PO-EARLY'
        rma.action_dealer_approve()
        self.assertEqual(line.state, 'in_repair', "PO already recorded: devices released at approval")

    def test_12_cancel_and_reset(self):
        rma = self._create_rma(self.lots[0])
        rma.action_cancel()
        self.assertEqual(rma.state, 'cancel')
        rma.action_reset_draft()
        self.assertEqual(rma.state, 'draft')

    def test_13_configuration(self):
        with self.assertRaises(ValidationError):
            self.company.safex_po_reminder_days = '7,abc'
        self.company.safex_po_reminder_days = '3, 10'
        self.assertEqual(self.company._get_safex_po_reminder_days(), [3, 10])
        self.device.product_tmpl_id.safex_dealer_warranty_months = 24
        lot = self.env['stock.lot'].create({'name': 'SFXT-OVR', 'product_id': self.device.id,
                                            'company_id': self.company.id})
        self.assertEqual(lot.dealer_warranty_months, 24, "Product override")
        self.assertEqual(lot.factory_warranty_months, 18, "Company default")
        # New checklist item reaches draft devices
        rma = self._create_rma(self.lots[0])
        item = self.env['safex.inspection.item'].create({
            'name': 'Antenna', 'option_ids': [Command.create({'name': 'OK', 'is_default': True})]})
        self.assertIn(item, rma.line_ids.inspection_line_ids.item_id)

    # ------------------------------------------------------------------
    # 3. Dealer portal
    # ------------------------------------------------------------------

    def test_20_portal(self):
        rma = self._create_rma(self.lots[0])
        rma.action_submit()
        other_rma = self.env['safex.rma'].create({
            'partner_id': self.other_dealer.id, 'company_id': self.company.id,
            'line_ids': [Command.create({'lot_id': self.lots[1].id, 'complaint_description': 'x'})]})
        self.authenticate('safex_dealer_portal', 'safex_dealer_portal')

        home = self.url_open('/my')
        self.assertEqual(home.status_code, 200)
        self.assertIn('/my/rma', home.text, "RMA & Repairs card on the portal home")
        self.assertIn('/my/verify', home.text, "Verify a Device card on the portal home")

        res = self.url_open('/my/rma')
        self.assertEqual(res.status_code, 200)
        self.assertIn(rma.name, res.text)
        self.assertNotIn(other_rma.name, res.text, "Dealers only see their own RMAs")

        # First URL with 3+ path segments in the process: Odoo 18 http lazily builds its static-file map
        # by reading every manifest on the addons path (~1300 here), which can exceed the 12 s default.
        detail = self.url_open(f'/my/rma/{rma.id}', timeout=90)
        self.assertEqual(detail.status_code, 200)
        self.assertIn(rma.name, detail.text)
        self.assertNotIn('Dealer Warranty Expiry', detail.text)
        other = self.url_open(f'/my/rma/{other_rma.id}', allow_redirects=False)
        self.assertIn(other.status_code, (301, 302, 303))

        self.assertEqual(self.url_open('/my/verify').status_code, 200)
        self.assertEqual(self.url_open('/my/rma/new').status_code, 200)
        result = self.make_jsonrpc_request('/my/rma/verify_device',
                                           {'serial_no': self.serials[2], 'imei': self.imeis[2]})
        self.assertTrue(result['verified'])
        self.assertEqual(set(result), {'verified', 'lot_id', 'product_name'})
        self.assertFalse(self.make_jsonrpc_request('/my/rma/verify_device',
                                                   {'serial_no': self.serials[2], 'imei': '1'})['verified'])

        pdf = self.url_open(f'/my/rma/{rma.id}/report/reference')
        self.assertEqual(pdf.status_code, 200)

        # New multi-device RMA from the portal
        csrf = self._csrf_token()
        res = self.url_open('/my/rma/new', data={
            'csrf_token': csrf, 'device_index': ['0', '1'],
            'serial_0': self.serials[2], 'imei_0': self.imeis[2], 'complaint_0': 'No signal',
            'acc_charger_0': '1', 'acc_dock_0': '1',
            'serial_1': self.serials[3], 'imei_1': self.imeis[3], 'complaint_1': 'Cracked screen',
        })
        self.assertEqual(res.status_code, 200)
        new_rma = self.env['safex.rma'].search([('created_from_portal', '=', True)], limit=1, order='id desc')
        self.assertTrue(new_rma)
        self.assertEqual(new_rma.state, 'submitted')
        self.assertEqual(new_rma.partner_id, self.dealer)
        self.assertEqual(len(new_rma.line_ids), 2)
        self.assertTrue(new_rma.line_ids.filtered(lambda l: l.lot_id == self.lots[2]).acc_declared_dock)
        # A device of another dealer is refused
        res = self.url_open('/my/rma/new', data={
            'csrf_token': csrf, 'device_index': ['0'],
            'serial_0': 'SFXT-UNKNOWN', 'imei_0': '1', 'complaint_0': 'x'}, allow_redirects=False)
        self.assertIn('error=device', res.headers.get('Location', ''))

        # PO number from the portal
        res = self.url_open(f'/my/rma/{rma.id}/submit_po', data={'csrf_token': csrf, 'po_number': 'PO-PORTAL'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(rma.po_number, 'PO-PORTAL')

        # Clarification from the portal needs a reason
        res = self.url_open(f'/my/rma/{rma.id}/action', data={'csrf_token': csrf, 'action': 'clarify', 'reason': ''},
                            allow_redirects=False)
        self.assertIn('error=action', res.headers.get('Location', ''))
        self.url_open(f'/my/rma/{rma.id}/action', data={'csrf_token': csrf, 'action': 'clarify', 'reason': 'When?'})
        self.assertTrue(self._messages(rma, 'Clarification requested by dealer: When?'))

    def test_21_portal_record_rules(self):
        rma = self._create_rma(self.lots[0])
        other_rma = self.env['safex.rma'].create({
            'partner_id': self.other_dealer.id, 'company_id': self.company.id,
            'line_ids': [Command.create({'lot_id': self.lots[1].id, 'complaint_description': 'x'})]})
        Rma = self.env['safex.rma'].with_user(self.portal_user)
        self.assertEqual(Rma.search([('id', 'in', (rma | other_rma).ids)]), rma)
        Line = self.env['safex.rma.line'].with_user(self.portal_user)
        self.assertEqual(Line.search([('rma_id', 'in', (rma | other_rma).ids)]), rma.line_ids)
