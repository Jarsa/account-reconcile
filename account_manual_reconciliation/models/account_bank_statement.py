# Copyright 2021 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, models

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    def show_reconciled_moves(self):
        self.ensure_one()
        move_lines = self.journal_entry_ids.mapped('move_id.line_ids')
        apr_ids = apr_obj = self.env['account.partial.reconcile']
        am_obj = self.env['account.move']
        aml_obj = self.env['account.move.line']
        for aml in move_lines:
            if aml.account_id.reconcile:
                apr_ids |= aml.matched_debit_ids | aml.matched_credit_ids
            #aml_ids = am_obj.search([('tax_cash_basis_rec_id','in', apr_ids.ids)]).mapped('line_ids') if apr_ids else aml_obj
            aml_ids = apr_ids.mapped('debit_move_id')
            aml_ids |= apr_ids.mapped('credit_move_id')
            aml_ids |= move_lines

            # /!\ NOTE: Repeating again to fetch the FX that could be in the Payment or somewhere else
            apr_ids |= aml_ids.mapped('matched_debit_ids') | aml_ids.mapped('matched_credit_ids')
            aml_ids |= apr_ids.mapped('debit_move_id')
            aml_ids |= apr_ids.mapped('credit_move_id')

            # /!\ NOTE: Get all the lines from related the moves
            aml_ids |= aml_ids.mapped('move_id.line_ids')
        return {
            'name': _('Reconciled Moves'),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'domain': [('id', 'in', aml_ids.ids)],
            'context': {
                'create': False,
                'delete': False,
                'search_default_group_by_move': True,
                'search_default_group_by_account': True,
            },
        }
