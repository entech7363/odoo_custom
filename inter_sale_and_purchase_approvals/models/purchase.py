import hashlib
import json

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare

# States in which an order has already been through (or is going through) the
# approval chain, and where editing the lines therefore invalidates it.
REAPPROVAL_STATES = ('to_approve', 'purchase')


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    state = fields.Selection(selection_add=
                             [('to_approve', 'To Approve'),
                              ('sent',)], ondelete={'to_approve': 'cascade'})
    show_approve_button = fields.Boolean(compute='_compute_show_approve_button')
    approval_step_sequence = fields.Integer(string='Approval Step Sequence', default=0)
    approval_history_ids = fields.One2many(
        'purchase.approval.history',
        'purchase_id'
    )
    approval_scope_hash = fields.Char(
        string='Approved Scope',
        copy=False, readonly=True,
        help="Fingerprint of the order lines as they stood when the order last "
             "entered or advanced through the approval chain. A mismatch means "
             "the order was edited and must be approved again.",
    )
    approval_revision = fields.Integer(
        string='Approval Round',
        default=0, copy=False, readonly=True,
        help="0 for the original approval. Incremented each time the order was "
             "edited after approval and sent back through the chain.",
    )

    @api.depends('state', 'user_id')
    def _compute_show_approve_button(self):
        for order in self:
            steps = self.env['approval.steps'].search([
                ('type', '=', 'purchase'),
                ('sequence', '=', order.approval_step_sequence),
                ('company_id', '=', order.company_id.id)
            ])
            user_ids = steps.mapped('user_id').ids
            is_admin = self.env.user.has_group('inter_sale_and_purchase_approvals.group_approval')
            order.show_approve_button = order.state == 'to_approve' and (self.env.uid in user_ids or is_admin)

    def _check_approval_step_sequence(self):
        approval_steps = self.env['approval.steps'].search([('type', '=', 'purchase')])

        company_step_map = {}
        for step in approval_steps:
            key = step.company_id.id
            company_sequences = company_step_map.setdefault(key, set())

            if step.sequence in company_sequences:
                raise ValidationError(
                    f"Duplicate sequence number '{step.sequence}' found in company '{step.company_id.name}' for purchase approval steps."
                )
            company_sequences.add(step.sequence)

    # ------------------------------------------------------------------
    # Re-approval
    # ------------------------------------------------------------------

    def _approval_scope_values(self):
        """Return the part of the order the approvers actually signed off on.

        Description text, sections and notes are deliberately excluded: only
        product, quantity, unit of measure, price, discount and taxes change
        what is being committed to.
        """
        self.ensure_one()
        lines = []
        real_lines = self.order_line.filtered(lambda l: not l.display_type)
        for line in real_lines.sorted(key=lambda l: (l.sequence, l.id)):
            lines.append([
                line.product_id.id,
                '%.6f' % (line.product_qty or 0.0),
                line.product_uom.id,
                '%.6f' % (line.price_unit or 0.0),
                '%.6f' % (line.discount or 0.0),
                sorted(line.taxes_id.ids),
            ])
        return {
            'currency': self.currency_id.id,
            'amount': '%.6f' % (self.amount_total or 0.0),
            'lines': lines,
        }

    def _approval_scope_hash(self):
        self.ensure_one()
        payload = json.dumps(self._approval_scope_values(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _stamp_approval_scope(self):
        """Record the current scope as the one that has been approved."""
        for order in self:
            order.with_context(skip_po_reapproval=True).write({
                'approval_scope_hash': order._approval_scope_hash(),
            })

    def _reapproval_pending(self):
        """True while this order carries edits the approvers have not signed yet.

        purchase_stock updates the receipt from inside its own write(), before
        this module can revert the state, so it must be told to hold off. The
        edited values are already written by then, which is what lets the
        fingerprint comparison here decide.
        """
        self.ensure_one()
        if self.env.context.get('po_force_picking_sync'):
            return False
        if not self.approval_scope_hash:
            return False
        if self.state not in REAPPROVAL_STATES:
            return False
        if not self.company_id.po_reapproval_enabled:
            return False
        return self._approval_scope_hash() != self.approval_scope_hash

    def _sync_deferred_pickings(self):
        """Apply the line changes to the receipt, once the order is confirmed.

        Validated receipts are untouched: Odoo only ever adjusts pickings that
        are neither done nor cancelled.
        """
        self.ensure_one()
        if self.state != 'purchase':
            return
        lines = self.order_line.filtered(lambda l: not l.display_type)
        if lines and hasattr(lines, '_create_or_update_picking'):
            lines.with_context(po_force_picking_sync=True)._create_or_update_picking()

    def _restart_approval(self):
        """Archive the signatures given so far and send the order back to step one."""
        self.ensure_one()
        new_hash = self._approval_scope_hash()
        steps = self.env['approval.steps'].search([
            ('type', '=', 'purchase'),
            ('minimum_amount', '<=', self.amount_total),
            ('company_id', '=', self.company_id.id),
        ], order='sequence asc')

        if not steps:
            # The revised amount no longer reaches any threshold, so this order
            # needs no approval at all. Accept the new scope silently.
            self._stamp_approval_scope()
            # Nothing to approve, so the receipt update that was held back
            # during write() has to be applied now.
            self._sync_deferred_pickings()
            return

        self.approval_history_ids.with_context(skip_po_reapproval=True).write({'active': False})
        revision = self.approval_revision + 1
        self.with_context(skip_po_reapproval=True).write({
            'state': 'to_approve',
            'approval_step_sequence': min(steps.mapped('sequence')),
            'approval_scope_hash': new_hash,
            'approval_revision': revision,
        })
        self.message_post(body=_(
            "Order lines were changed after approval. The approval chain has been "
            "restarted from the first step (round %s); previous signatures have been "
            "archived. The receipt keeps the previously approved quantities until "
            "the chain completes.", revision,
        ))

    def _ensure_approval_baseline(self):
        """Bring an order under the re-approval rule however it got confirmed.

        button_confirm() and button_approve_po() stamp the scope themselves, but
        an order can reach 'purchase' or 'to_approve' by other routes -- a data
        import, a direct state write, another module's flow -- and _check_reapproval()
        treats an unstamped order as exempt for good. Stamping on arrival closes
        that gap; it re-approves nothing, it only records the starting point.
        """
        for order in self:
            if order.approval_scope_hash:
                continue
            if order.state not in REAPPROVAL_STATES:
                continue
            order._stamp_approval_scope()

    def _check_reapproval(self):
        if self.env.context.get('skip_po_reapproval'):
            return
        for order in self:
            if not order.approval_scope_hash:
                # No baseline to compare against. _ensure_approval_baseline()
                # runs before every edit, so this is only reachable for orders
                # outside the flow (draft, sent, cancelled).
                continue
            if order.state not in REAPPROVAL_STATES:
                continue
            if not order.company_id.po_reapproval_enabled:
                continue
            if order._approval_scope_hash() == order.approval_scope_hash:
                continue
            order._restart_approval()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        if not self.env.context.get('skip_po_reapproval'):
            orders._ensure_approval_baseline()
        return orders

    def write(self, vals):
        if not self.env.context.get('skip_po_reapproval'):
            # Before the edit: an order that is already in the flow but carries
            # no baseline gets stamped with its CURRENT scope, so the edit about
            # to be applied is measured against what the approvers actually saw.
            self._ensure_approval_baseline()
        res = super().write(vals)
        if not self.env.context.get('skip_po_reapproval'):
            # After the edit: catches an order that has just arrived in the flow.
            self._ensure_approval_baseline()
        self._check_reapproval()
        return res

    # ------------------------------------------------------------------
    # Approval flow
    # ------------------------------------------------------------------

    def button_confirm(self):
        self._check_approval_step_sequence()
        for order in self:
            steps = self.env['approval.steps'].search([
                ('type', '=', 'purchase'),
                ('minimum_amount', '<=', order.amount_total), ('company_id', '=', order.company_id.id)
            ], order='sequence asc')

            if steps:

                first_sequence = min(steps.mapped('sequence'))
                order.with_context(skip_po_reapproval=True).write({
                    'state': 'to_approve',
                    'approval_step_sequence': first_sequence,
                    'approval_scope_hash': order._approval_scope_hash(),
                })
            else:
                super(PurchaseOrder, order).button_confirm()
                # Stamp it anyway: if the order is later edited above a
                # threshold, that edit must pull it into the chain.
                order._stamp_approval_scope()
        return True

    def button_approve_po(self):
        for order in self:

            # ✅ Get current step
            step = self.env['approval.steps'].search([
                ('type', '=', 'purchase'),
                ('sequence', '=', order.approval_step_sequence),
                ('company_id', '=', order.company_id.id)
            ], limit=1)

            # ✅ Prevent duplicate history (within the current approval round)
            if step:
                existing = self.env['purchase.approval.history'].search([
                    ('purchase_id', '=', order.id),
                    ('sequence', '=', step.sequence),
                    ('revision', '=', order.approval_revision)
                ], limit=1)

                if not existing:
                    self.env['purchase.approval.history'].create({
                        'purchase_id': order.id,
                        'step_id': step.id,
                        'user_id': self.env.user.id,
                        'sequence': step.sequence,
                        'revision': order.approval_revision,
                        'date': fields.Datetime.now(),
                    })

            # ✅ Admin bypass logic (DO NOT return)
            is_admin = self.env.user.has_group(
                'inter_sale_and_purchase_approvals.group_approval'
            )

            if is_admin:
                super(PurchaseOrder, order).button_approve()
                order._stamp_approval_scope()
                order._sync_deferred_pickings()
                continue

            # ✅ Next step logic
            next_sequence = order.approval_step_sequence + 1

            next_steps = self.env['approval.steps'].search([
                ('type', '=', 'purchase'),
                ('sequence', '=', next_sequence),
                ('minimum_amount', '<=', order.amount_total),
                ('company_id', '=', order.company_id.id)
            ])

            if next_steps:
                order.with_context(skip_po_reapproval=True).write({
                    'state': 'to_approve',
                    'approval_step_sequence': next_sequence,
                    'approval_scope_hash': order._approval_scope_hash(),
                })
            else:
                order.with_context(skip_po_reapproval=True).write({'state': 'purchase'})
                super(PurchaseOrder, order).button_approve()
                order._stamp_approval_scope()
                order._sync_deferred_pickings()

    def button_cancel(self):
        self.write({'state': 'cancel'})


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('skip_po_reapproval'):
            order_ids = {v['order_id'] for v in vals_list if v.get('order_id')}
            self.env['purchase.order'].browse(order_ids)._ensure_approval_baseline()
        lines = super().create(vals_list)
        lines.order_id._check_reapproval()
        return lines

    def write(self, vals):
        if not self.env.context.get('skip_po_reapproval'):
            self.order_id._ensure_approval_baseline()
        res = super().write(vals)
        self.order_id._check_reapproval()
        return res

    def unlink(self):
        orders = self.order_id
        if not self.env.context.get('skip_po_reapproval'):
            orders._ensure_approval_baseline()
        res = super().unlink()
        orders.exists()._check_reapproval()
        return res

    def _create_or_update_picking(self):
        """Hold the receipt at the approved quantities.

        purchase_stock calls this from its own write() while the order is still
        'purchase', which would otherwise let the warehouse receive a quantity
        nobody has approved. Lines whose order is heading back into the approval
        chain are skipped here and synced again from button_approve_po().
        """
        deferred = self.filtered(lambda l: l.order_id._reapproval_pending())
        # Odoo normally raises this during the edit. Deferring the picking update
        # must not defer the error too, or an approver would be the one to hit it.
        for line in deferred:
            if line.product_id and line.product_id.type == 'consu':
                rounding = line.product_uom.rounding
                if float_compare(line.product_qty, line.qty_received, precision_rounding=rounding) < 0:
                    raise UserError(_(
                        'You cannot decrease the ordered quantity below the received quantity.\n'
                        'Create a return first.'))
        remaining = self - deferred
        if remaining:
            return super(PurchaseOrderLine, remaining)._create_or_update_picking()
        return None
