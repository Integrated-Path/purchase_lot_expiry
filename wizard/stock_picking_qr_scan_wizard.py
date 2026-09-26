# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPickingQrScanWizard(models.TransientModel):
    _name = 'stock.picking.qr.scan.wizard'
    _description = 'Warehouse QR Receipt Scanner Kiosk'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Receipt',
        required=True,
        readonly=True
    )
    picking_name = fields.Char(
        string='Receipt Reference',
        related='picking_id.name',
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        related='picking_id.partner_id',
        readonly=True
    )
    scan_input = fields.Char(
        string='Scan QR Code / Barcode',
        help='Scan your Lot/Serial QR code here'
    )
    scan_status_message = fields.Char(
        string='Status',
        readonly=True,
        default='Ready for scanning.'
    )
    scan_status_type = fields.Selection([
        ('info', 'Info'),
        ('success', 'Success'),
        ('danger', 'Error'),
    ], default='info', readonly=True)
    scan_log = fields.Text(
        string='Activity Log',
        readonly=True
    )
    line_ids = fields.One2many(
        'stock.picking.qr.scan.wizard.line',
        'wizard_id',
        string='Fulfillment Lines'
    )
    total_demand = fields.Float(
        string='Total Demand',
        compute='_compute_totals'
    )
    total_done = fields.Float(
        string='Total Done',
        compute='_compute_totals'
    )
    is_all_fulfilled = fields.Boolean(
        string='Fully Fulfilled',
        compute='_compute_totals'
    )

    @api.depends('line_ids.demand_qty', 'line_ids.done_qty')
    def _compute_totals(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for wizard in self:
            tot_demand = sum(l.demand_qty for l in wizard.line_ids)
            tot_done = sum(l.done_qty for l in wizard.line_ids)
            wizard.total_demand = tot_demand
            wizard.total_done = tot_done
            all_done = True
            for l in wizard.line_ids:
                if float_compare(l.done_qty, l.demand_qty, precision_digits=precision) < 0:
                    all_done = False
                    break
            wizard.is_all_fulfilled = all_done and bool(wizard.line_ids)

    def _populate_lines(self):
        """ Populate or refresh line_ids from picking active moves """
        self.ensure_one()
        self.line_ids.unlink()
        lines_vals = []
        for move in self.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            lots = move.move_line_ids.mapped('lot_id.name')
            lots_str = ", ".join(filter(None, lots))
            lines_vals.append((0, 0, {
                'move_id': move.id,
                'product_id': move.product_id.id,
                'demand_qty': move.product_uom_qty,
                'done_qty': move.quantity,
                'lot_names_display': lots_str,
            }))
        self.write({'line_ids': lines_vals})

    def action_process_scan(self):
        """ Process barcode/QR scan, refresh progress and keep modal open """
        self.ensure_one()
        if not self.scan_input:
            return self._reopen_wizard()

        raw_scan = self.scan_input.strip()
        self.scan_input = False

        res = self.picking_id._process_receipt_qr_payload(raw_scan) if hasattr(self.picking_id, '_process_receipt_qr_payload') else self.picking_id._process_qr_payload(raw_scan)

        # Refresh progress lines
        self._populate_lines()

        # Update log and status
        now_str = fields.Datetime.now().strftime('%H:%M:%S')
        if res and res.get('params', {}).get('type') == 'success':
            msg = res['params']['message']
            self.scan_status_message = msg
            self.scan_status_type = 'success'
            new_entry = f"[{now_str}] {msg}"
        else:
            err_msg = res.get('params', {}).get('message') if res else _("Failed to process scan.")
            self.scan_status_message = err_msg
            self.scan_status_type = 'danger'
            new_entry = f"[{now_str}] ✗ {err_msg}"

        log_lines = (self.scan_log or "").splitlines()
        log_lines.insert(0, new_entry)
        self.scan_log = "\n".join(log_lines[:15])

        return self._reopen_wizard()

    def action_validate_picking(self):
        """ Validate the picking upon completion """
        self.ensure_one()
        if not self.is_all_fulfilled:
            raise UserError(_("Receipt is not yet fully fulfilled. Please finish scanning all items before validating."))
        res = self.picking_id.button_validate()
        return res

    def _reopen_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class StockPickingQrScanWizardLine(models.TransientModel):
    _name = 'stock.picking.qr.scan.wizard.line'
    _description = 'Receipt Scanner Progress Line'

    wizard_id = fields.Many2one(
        'stock.picking.qr.scan.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    product_barcode = fields.Char(
        string='Barcode',
        related='product_id.barcode',
        readonly=True
    )
    lot_names_display = fields.Char(
        string='Received Lots',
        readonly=True
    )
    demand_qty = fields.Float(
        string='Demand',
        digits='Product Unit of Measure'
    )
    done_qty = fields.Float(
        string='Done',
        digits='Product Unit of Measure'
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
        related='product_id.uom_id',
        readonly=True
    )
    is_fulfilled = fields.Boolean(
        string='Complete',
        compute='_compute_is_fulfilled'
    )

    @api.depends('demand_qty', 'done_qty')
    def _compute_is_fulfilled(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            line.is_fulfilled = float_compare(line.done_qty, line.demand_qty, precision_digits=precision) >= 0
