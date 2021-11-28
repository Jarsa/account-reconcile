# Copyright 2021 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, models

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def show_related_statement_line(self):
        self.ensure_one()
        return {
            'name': _('Statement Line'),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'account.bank.statement.line',
            'domain': [('id', '=', self.statement_line_id.id)],
            'context': {
                'create': False,
                'delete': False,
            }
        }
