# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPickingMobileQrWizard(models.TransientModel):
    _name = 'stock.picking.mobile.qr.wizard'
    _description = 'Mobile Camera QR Scanner Wizard for Receipts'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Transfer',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    picking_name = fields.Char(related='picking_id.name', readonly=True)
    partner_id = fields.Many2one(related='picking_id.partner_id', readonly=True)
    picking_type_code = fields.Selection(related='picking_id.picking_type_code', readonly=True)

    last_scan_message = fields.Char(
        string='Last Scan Message',
        readonly=True,
        default='Ready to scan box labels.'
    )
    last_scan_status = fields.Selection([
        ('info', 'Info'),
        ('success', 'Success'),
        ('danger', 'Error'),
    ], default='info', readonly=True)

    scan_log = fields.Text(
        string='Scan Activity Log',
        readonly=True
    )

    total_demand = fields.Float(string='Total Demand', compute='_compute_progress')
    total_done = fields.Float(string='Total Done', compute='_compute_progress')
    is_all_fulfilled = fields.Boolean(string='Fully Received', compute='_compute_progress')

    line_ids = fields.One2many(
        'stock.picking.mobile.qr.wizard.line',
        'wizard_id',
        string='Receipt Lines',
        compute='_compute_lines',
        store=False
    )

    @api.depends('picking_id.move_ids.quantity', 'picking_id.move_ids.product_uom_qty')
    def _compute_progress(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for wizard in self:
            moves = wizard.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
            tot_demand = sum(m.product_uom_qty for m in moves)
            tot_done = sum(m.quantity for m in moves)
            wizard.total_demand = tot_demand
            wizard.total_done = tot_done
            wizard.is_all_fulfilled = bool(moves) and all(
                float_compare(m.quantity, m.product_uom_qty, precision_digits=precision) >= 0
                for m in moves
            )

    @api.depends('picking_id.move_ids.quantity', 'picking_id.move_ids.product_uom_qty', 'picking_id.move_line_ids.quantity', 'picking_id.move_line_ids.lot_id')
    def _compute_lines(self):
        for wizard in self:
            if (
                wizard.picking_id.purchase_id
                and wizard.picking_id.purchase_id.purchase_type == 'internal_po'
            ):
                wizard.line_ids = False
                continue
            lines = []
            for move in wizard.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                lots_str = ", ".join(filter(None, move.move_line_ids.mapped('lot_id.name')))
                lines.append((0, 0, {
                    'wizard_id': wizard.id,
                    'product_id': move.product_id.id,
                    'demand_qty': move.product_uom_qty,
                    'done_qty': move.quantity,
                    'lot_names_display': lots_str,
                }))
            wizard.line_ids = lines

    def process_mobile_qr_scan(self, raw_payload):
        """
        Invoked asynchronously by the OWL camera widget upon every successful scan.
        Supports:
        1. Structured Delimited: PROD:code|LOT:lot|EXP:date|QTY:qty
        2. Positional Delimited: code|lot|qty or code|lot|exp|qty
        3. Structured JSON: {"b": code, "l": lot, "e": date, "q": qty}
        4. Plain lot / barcode or GS1-128
        """
        self.ensure_one()
        self._ensure_external_purchase()
        if not raw_payload:
            return {'success': False, 'message': _("Empty QR scan received.")}

        raw_str = raw_payload.strip()

        try:
            res = self.picking_id._process_receipt_qr_payload(raw_str)
            params = res.get('params', {}) if isinstance(res, dict) else {}
            res_type = params.get('type', 'info')
            msg = params.get('message', _("Scan processed."))

            is_success = (res_type == 'success')
            status_type = 'success' if is_success else 'danger'
            self._append_log(msg, status_type)

            self.invalidate_recordset(['line_ids', 'total_demand', 'total_done', 'is_all_fulfilled'])

            return {
                'success': is_success,
                'message': msg,
            }
        except Exception as e:
            err_msg = str(e)
            self._append_log(err_msg, 'danger')
            return {
                'success': False,
                'message': err_msg,
            }

    def _append_log(self, message, status_type):
        now_str = fields.Datetime.now().strftime('%H:%M:%S')
        new_entry = f"[{now_str}] {message}"
        lines = (self.scan_log or "").splitlines()
        lines.insert(0, new_entry)
        self.write({
            'last_scan_message': message,
            'last_scan_status': status_type,
            'scan_log': "\n".join(lines[:25]),
        })

    def action_validate_transfer(self):
        """ Directly validate picking from mobile wizard """
        self.ensure_one()
        self._ensure_external_purchase()
        return self.picking_id.button_validate()

    def _ensure_external_purchase(self):
        if (
            self.picking_id.purchase_id
            and self.picking_id.purchase_id.purchase_type == 'internal_po'
        ):
            raise UserError(_("Custom QR receiving is not available for internal purchase orders."))


class StockPickingMobileQrWizardLine(models.TransientModel):
    _name = 'stock.picking.mobile.qr.wizard.line'
    _description = 'Mobile QR Wizard Line'

    wizard_id = fields.Many2one('stock.picking.mobile.qr.wizard', ondelete='cascade')
    product_id = fields.Many2one('product.product', readonly=True)
    lot_names_display = fields.Char(string='Lots', readonly=True)
    demand_qty = fields.Float(string='Demand', readonly=True)
    done_qty = fields.Float(string='Done', readonly=True)
    is_fulfilled = fields.Boolean(compute='_compute_fulfilled')

    @api.depends('demand_qty', 'done_qty')
    def _compute_fulfilled(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            line.is_fulfilled = float_compare(line.done_qty, line.demand_qty, precision_digits=precision) >= 0
