# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, fields, models, api
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountBankReconciliationDifferenceWizard(models.TransientModel):
    _name = 'account.bank.reconciliation.difference.wizard'
    _description = 'Manual Reconciliation Difference Wizard'

    statement_lines_ids = fields.One2many(
        'account.reconciliation.statement.line.select',
        'statement_line_difference_wizard'
    )
    move_lines_ids = fields.One2many(
        'account.reconciliation.move.line.select',
        'move_line_difference_wizard'
    )
    amount = fields.Float()
    line_ids = fields.One2many(
        'account.bank.reconciliation.difference.line.wizard',
        'reconciliation_id',
        string='Journal Items',
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res["amount"] = self._context.get('amount', 0)
        res["statement_lines_ids"] = self._context.get('statement_lines')
        res["move_lines_ids"] = self._context.get('move_lines_ids')
        return res

    def action_difference_reconciliation(self):
        for selected_line in self.statement_lines_ids:
            sum_move = sum(self.line_ids.mapped('amount'))
            if not self.line_ids and self.amount:
                raise UserError(_('You need to define at least one line.'))
            compare = float_compare(self.amount, sum_move, precision_digits=5)
            if compare != 0:
                raise UserError(_('The amount is different, please checks amounts'))
            statement_line = selected_line.statement_line_id
            currency_id = (
                statement_line.currency_id.id if
                statement_line.currency_id else self.env.company.currency_id.id)
            partner_id = statement_line.partner_id.id if statement_line.partner_id else False
            amount = self.amount if self.amount else selected_line.amount
            move_dict = {
                'type': 'entry',
                'journal_id': statement_line.journal_id.id,
                'currency_id': currency_id,
                'date': statement_line.date,
                'partner_id': partner_id,
                'ref': statement_line.ref,
                'line_ids': [],
            }
            payment_methods = (
                statement_line.journal_id.inbound_payment_method_ids if
                (amount > 0) else
                statement_line.journal_id.outbound_payment_method_ids
            )
            data_payment = {
                'payment_method_id': payment_methods[0].id,
                'payment_type': 'inbound' if amount > 0 else 'outbound',
                'partner_id': partner_id,
                'partner_type': statement_line.account_id.user_type_id.name,
                'journal_id': statement_line.journal_id.id,
                'payment_date': statement_line.date,
                'state': 'reconciled',
                'currency_id': currency_id,
                'amount': abs(amount),
                'communication': statement_line.ref,
                'name': statement_line.name or _("Bank Statement %s") % statement_line.date,
            }
            payment = self.env['account.payment'].create(data_payment)
            account_id = (
                statement_line.statement_id.journal_id.default_credit_account_id.id if
                amount >= 0
                else statement_line.statement_id.journal_id.default_debit_account_id.id)
            move_dict['line_ids'].append((0, 0, {
                'name': statement_line.name,
                'partner_id': partner_id,
                'account_id': account_id,
                'credit': abs(amount) if amount < 0 else 0.0,
                'debit': amount if amount > 0 else 0.0,
                'statement_line_id': statement_line.id,
                'statement_id': statement_line.statement_id.id,
                'payment_id': payment.id,
            }))
            if not self.amount:
                move_dict['line_ids'].append((0, 0, {
                    'name': statement_line.name,
                    'partner_id': partner_id,
                    'account_id': self.account_id.id,
                    'credit': amount if amount > 0 else 0.0,
                    'debit': abs(amount) if amount < 0 else 0.0,
                    'statement_line_id': statement_line.id,
                    'statement_id': statement_line.statement_id.id,
                    'payment_id': payment.id,
                }))
            else:
                for line in self.line_ids:
                    move_dict['line_ids'].append((0, 0, {
                        'name': line.name,
                        'partner_id': partner_id,
                        'account_id': line.account_id.id,
                        'analytic_account_id': line.account_analytic_id.id,
                        'credit': line.amount if line.amount > 0 else 0.0,
                        'debit': abs(line.amount) if line.amount else 0.0,
                        'statement_line_id': statement_line.id,
                        'statement_id': statement_line.statement_id.id,
                        'payment_id': payment.id,
                    }))
            move = self.env['account.move'].with_context(
                default_journal_id=move_dict['journal_id']).create(move_dict)
            move.action_post()
            selected_line.unlink()
        self.move_lines_ids.unlink()


class AccountBankReconciliationDifferenceLineWizard(models.TransientModel):
    _name = 'account.bank.reconciliation.difference.line.wizard'
    _description = 'Manual Reconciliation Line Difference Wizard'

    amount = fields.Float(
        compute="_compute_total_amount")
    name = fields.Char()
    account_id = fields.Many2one(
        'account.account'
    )
    account_analytic_id = fields.Many2one(
        'account.analytic.account'
    )
    reconciliation_id = fields.Many2one(
        'account.bank.reconciliation.difference.wizard',
        string='Journal Entry',
    )
    partner_id = fields.Many2one(
        'res.partner'
    )

    @api.depends('account_id')
    def _compute_total_amount(self):
        for rec in self:
            rec.amount = self.reconciliation_id.amount - rec.amount
