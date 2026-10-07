# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup

from .purchase_order import LOGISTICS_STAGES

BILL_LOGISTICS_STAGES = [
    ('shipment_booking', 'حجز الشحنة (Shipment Booking)'),
    ('transport_port', 'نقل للميناء / المطار (Transport)'),
    ('on_the_way', 'الشحنة في الطريق (On the way)'),
    ('clearance', 'بدء التخليص (Clearance)'),
    ('received', 'الاستلام المخزني (Received)'),
]

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Stored reference to linked Purchase Order
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='أمر الشراء / Purchase Order',
        compute='_compute_purchase_order_id',
        store=True,
        readonly=False,
        copy=False,
        help="Linked Purchase Order for logistics and clearance tracking."
    )
    purchase_type = fields.Selection(
        related='purchase_order_id.purchase_type',
        string='Purchase Type',
        readonly=True
    )
    purchase_journal = fields.Many2one(
        related='purchase_order_id.purchase_journal',
        string='Purchase Journal',
        store=True,
        readonly=True
    )

    # Synchronized logistics stage from linked Purchase Order
    logistics_stage = fields.Selection(
        LOGISTICS_STAGES,
        string='مرحلة الشحنة / Logistics Stage',
        compute='_compute_logistics_stage',
        store=True,
        readonly=True,
        copy=False,
        tracking=True,
        help='Tracks the logistics pipeline synchronized with the purchase order.'
    )

    @api.depends('purchase_order_id.logistics_stage', 'purchase_order_id.purchase_type')
    def _compute_logistics_stage(self):
        for move in self:
            if move.purchase_order_id and move.purchase_order_id.purchase_type == 'internal_po':
                move.logistics_stage = False
            else:
                move.logistics_stage = move.purchase_order_id.logistics_stage if move.purchase_order_id else False

    freight_type = fields.Selection(
        related='purchase_order_id.freight_type',
        string='نوع الشحن / Freight Type',
        readonly=True
    )

    destination_warehouse_id = fields.Many2one(
        related='purchase_order_id.destination_warehouse_id',
        string='المخزن المستلم / Destination Warehouse',
        readonly=True
    )

    # Checklist Item 1: MOH Approval (موافقة وزارة الصحة)
    moh_approval = fields.Boolean(
        string='موافقة وزارة الصحة (MOH Approval)',
        tracking=True,
        copy=False
    )
    moh_attachment_ids = fields.Many2many(
        'ir.attachment',
        'bill_moh_attachment_rel',
        'move_id',
        'attachment_id',
        string='مرفقات موافقة وزارة الصحة',
        copy=False
    )
    moh_ref = fields.Char(string='رقم مرجع وزارة الصحة', copy=False)
    moh_date = fields.Date(string='تاريخ موافقة وزارة الصحة', copy=False)

    # Checklist Item 2: MOT Approval (موافقة وزارة التجارة)
    mot_approval = fields.Boolean(
        string='موافقة وزارة التجارة (MOT Approval)',
        tracking=True,
        copy=False
    )
    mot_attachment_ids = fields.Many2many(
        'ir.attachment',
        'bill_mot_attachment_rel',
        'move_id',
        'attachment_id',
        string='مرفقات موافقة وزارة التجارة',
        copy=False
    )
    mot_ref = fields.Char(string='رقم مرجع وزارة التجارة', copy=False)
    mot_date = fields.Date(string='تاريخ موافقة وزارة التجارة', copy=False)

    # Checklist Item 3: Attestation & Legalization (التصديق)
    attestation_approval = fields.Boolean(
        string='التصديق (Attestation / Legalization)',
        tracking=True,
        copy=False
    )
    attestation_attachment_ids = fields.Many2many(
        'ir.attachment',
        'bill_attestation_attachment_rel',
        'move_id',
        'attachment_id',
        string='مرفقات التصديق',
        copy=False
    )
    attestation_ref = fields.Char(string='رقم مرجع التصديق', copy=False)
    attestation_date = fields.Date(string='تاريخ التصديق', copy=False)

    # Checklist Item 4: Customs Release (إخراج كمرك)
    customs_release_approval = fields.Boolean(
        string='إخراج كمرك (Customs Release)',
        tracking=True,
        copy=False
    )
    customs_attachment_ids = fields.Many2many(
        'ir.attachment',
        'bill_customs_attachment_rel',
        'move_id',
        'attachment_id',
        string='مرفقات إخراج كمرك',
        copy=False
    )
    customs_ref = fields.Char(string='رقم البيان الجمركي', copy=False)
    customs_date = fields.Date(string='تاريخ الإخراج الجمركي', copy=False)

    @api.depends('invoice_line_ids.purchase_order_id', 'line_ids.purchase_line_id.order_id')
    def _compute_purchase_order_id(self):
        for move in self:
            if not move.purchase_order_id:
                pos = move.invoice_line_ids.purchase_order_id | move.line_ids.purchase_line_id.order_id
                move.purchase_order_id = pos[:1] if pos else False

    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        
        if not self.env.context.get('skip_checklist_sync'):
            checklist_fields = {
                'moh_approval', 'moh_ref', 'moh_date', 'moh_attachment_ids',
                'mot_approval', 'mot_ref', 'mot_date', 'mot_attachment_ids',
                'attestation_approval', 'attestation_ref', 'attestation_date', 'attestation_attachment_ids',
                'customs_release_approval', 'customs_ref', 'customs_date', 'customs_attachment_ids',
            }
            updated = checklist_fields & set(vals.keys())
            if updated:
                for move in self:
                    if move.purchase_order_id and move.purchase_order_id.purchase_type != 'internal_po':
                        po_vals = {}
                        for field in updated:
                            if field.endswith('_attachment_ids'):
                                po_vals[field] = [(6, 0, move[field].ids)]
                            else:
                                po_vals[field] = vals[field]
                        move.purchase_order_id.with_context(skip_checklist_sync=True).write(po_vals)
        return res

    def action_stage_shipment_booking(self):
        for move in self:
            if move.purchase_order_id and move.purchase_order_id.purchase_type != 'internal_po':
                move.purchase_order_id.action_stage_shipment_booking()

    def action_stage_transport_port(self):
        for move in self:
            if move.purchase_order_id and move.purchase_order_id.purchase_type != 'internal_po':
                move.purchase_order_id.action_stage_transport_port()

    def action_stage_on_the_way(self):
        for move in self:
            if move.purchase_order_id and move.purchase_order_id.purchase_type != 'internal_po':
                move.purchase_order_id.action_stage_on_the_way()

    def action_stage_clearance(self):
        for move in self:
            if move.purchase_order_id and move.purchase_order_id.purchase_type != 'internal_po':
                move.purchase_order_id.action_stage_clearance()

    def action_stage_received(self):
        for move in self:
            if move.purchase_order_id and move.purchase_order_id.purchase_type != 'internal_po':
                return move.purchase_order_id.action_stage_received()

    def action_stage_previous(self):
        for move in self:
            if move.purchase_order_id and move.purchase_order_id.purchase_type != 'internal_po':
                move.purchase_order_id.action_stage_previous()
