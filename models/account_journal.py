from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    allowed_users = fields.Many2many('res.users', string="Allowed Users", store=True)