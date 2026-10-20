# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockLot(models.Model):
    _inherit = 'stock.lot'

    qr_code_value = fields.Char(
        string='QR Code Payload',
        compute='_compute_qr_code_value',
        store=True,
        index=True,
        help='Structured QR code payload used for scanning and label printing.'
    )
    product_part_number = fields.Char(
            related='product_id.part_number',
            string='Part Number',
            store=True,
            readonly=True
    )

    @api.depends('name', 'product_id', 'product_id.barcode', 'product_id.default_code', 'expiration_date')
    def _compute_qr_code_value(self):
        for lot in self:
            bc = ''
            if lot.product_id:
                bc = lot.product_id.barcode or lot.product_id.default_code or ''
            lot_name = lot.name or ''
            exp_str = ''
            if lot.expiration_date:
                exp_date = lot.expiration_date.date() if hasattr(lot.expiration_date, 'date') else lot.expiration_date
                exp_str = fields.Date.to_string(exp_date)
            lot.qr_code_value = f"PROD:{bc}|LOT:{lot_name}|EXP:{exp_str}"

    def action_print_lot_qr_labels(self):
        """ Open label printing wizard for this lot or selected lots """
        wizard_lines = []
        for lot in self:
            qty_on_hand = getattr(lot, 'product_qty', 0.0) or 0.0
            copies = int(qty_on_hand) if qty_on_hand >= 1.0 else 1
            wizard_lines.append((0, 0, {
                'product_id': lot.product_id.id,
                'lot_id': lot.id,
                'lot_name': lot.name,
                'expiration_date': lot.expiration_date,
                'quantity': 1.0,
                'copies': copies,
                'is_selected': True,
            }))

        if not wizard_lines:
            raise UserError(_("No Lot/Serial numbers selected."))

        wizard = self.env['purchase.lot.qr.wizard'].create({
            'line_ids': wizard_lines,
        })
        return {
            'name': _('Print Lot/Serial QR Labels'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.lot.qr.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
