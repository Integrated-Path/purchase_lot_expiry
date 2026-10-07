# -*- coding: utf-8 -*-
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseLotQrWizard(models.TransientModel):
    _name = 'purchase.lot.qr.wizard'
    _description = 'Lot/Serial QR Code Generation Wizard'

    purchase_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        readonly=True
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Receipt',
        readonly=True
    )
    layout_type = fields.Selection([
        ('thermal_50x30', 'Thermal Roll (50 x 30 mm)'),
        ('thermal_40x20', 'Thermal Roll (40 x 20 mm)'),
        ('avery_12_sheet', 'Avery Sheet (3 x 4 per page)'),
    ], string='Label Format', default='thermal_50x30', required=True)

    payload_format = fields.Selection([
        ('delimited', 'Structured Delimited (PROD|LOT|EXP|QTY)'),
        ('json', 'Structured JSON'),
        ('plain_lot', 'Plain Lot Number'),
    ], string='QR Payload Format', default='delimited', required=True)

    line_ids = fields.One2many(
        'purchase.lot.qr.wizard.line',
        'wizard_id',
        string='Labels to Print'
    )
    total_labels_to_print = fields.Integer(
        string='Total Labels',
        compute='_compute_total_labels'
    )

    @api.depends('line_ids.is_selected', 'line_ids.copies')
    def _compute_total_labels(self):
        for wizard in self:
            wizard.total_labels_to_print = sum(
                l.copies for l in wizard.line_ids if l.is_selected and l.copies > 0
            )

    def action_select_all(self):
        self._ensure_external_source()
        self.line_ids.write({'is_selected': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_unselect_all(self):
        self._ensure_external_source()
        self.line_ids.write({'is_selected': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_print(self):
        self.ensure_one()
        self._ensure_external_source()
        selected_lines = self.line_ids.filtered(lambda l: l.is_selected and l.copies > 0)
        if not selected_lines:
            raise UserError(_("Please select at least one lot line with copies > 0 to print labels."))
        
        report = self.env.ref('purchase_lot_expiry.action_report_lot_qr_labels')
        if self.layout_type == 'thermal_50x30':
            report.paperformat_id = self.env.ref('purchase_lot_expiry.paperformat_thermal_50x30').id
        elif self.layout_type == 'thermal_40x20':
            report.paperformat_id = self.env.ref('purchase_lot_expiry.paperformat_thermal_40x20').id
        else:
            report.paperformat_id = False

        res = report.report_action(self)
        
        def _clean_none(val):
            if val is None:
                return False
            if isinstance(val, dict):
                return {k: _clean_none(v) for k, v in val.items()}
            if isinstance(val, (list, tuple)):
                return [_clean_none(v) for v in val]
            return val

        return _clean_none(res)

    def _ensure_external_source(self):
        for wizard in self:
            purchase_order = wizard.purchase_id or wizard.picking_id.purchase_id
            if purchase_order and purchase_order.purchase_type == 'internal_po':
                raise UserError(_("Custom QR labels are not available for internal purchase orders."))


class PurchaseLotQrWizardLine(models.TransientModel):
    _name = 'purchase.lot.qr.wizard.line'
    _description = 'Lot QR Wizard Line'

    wizard_id = fields.Many2one(
        'purchase.lot.qr.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    is_selected = fields.Boolean(
        string='Print',
        default=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    product_name = fields.Char(
        string='Product Name',
        related='product_id.name',
        readonly=True
    )
    product_code = fields.Char(
        string='Product Code',
        related='product_id.default_code',
        readonly=True
    )
    product_barcode = fields.Char(
        string='Barcode',
        related='product_id.barcode',
        readonly=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot Record'
    )
    lot_name = fields.Char(
        string='Lot/Serial Number',
        required=True
    )
    expiration_date = fields.Datetime(
        string='Expiration Date'
    )
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        default=1.0
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
        related='product_id.uom_id',
        readonly=True
    )
    copies = fields.Integer(
        string='Copies',
        default=1
    )
    qr_code_value = fields.Char(
        string='QR Payload',
        compute='_compute_qr_code_value'
    )

    @api.depends('wizard_id.payload_format', 'product_barcode', 'product_code', 'lot_name', 'expiration_date', 'quantity')
    def _compute_qr_code_value(self):
        for line in self:
            payload_fmt = line.wizard_id.payload_format or 'delimited'
            lot = line.lot_name or ''
            bc = line.product_barcode or line.product_code or ''
            exp_str = ''
            if line.expiration_date:
                exp_date = line.expiration_date.date() if hasattr(line.expiration_date, 'date') else line.expiration_date
                exp_str = fields.Date.to_string(exp_date)

            qty = line.quantity or 1.0

            if payload_fmt == 'json':
                payload = {
                    'b': bc,
                    'l': lot,
                    'e': exp_str,
                    'q': qty,
                }
                line.qr_code_value = json.dumps(payload, separators=(',', ':'))
            elif payload_fmt == 'plain_lot':
                line.qr_code_value = lot
            else:  # delimited
                line.qr_code_value = f"PROD:{bc}|LOT:{lot}|EXP:{exp_str}|QTY:{qty}"
