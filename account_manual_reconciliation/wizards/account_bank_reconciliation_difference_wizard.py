# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, fields, models, api
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountBankReconciliationDifferenceWizard(models.TransientModel):
    _name = 'account.bank.reconciliation.difference.wizard'

    move_line_ids = fields.Many2one(
        comodel_name='account.reconciliation.move.line.select'
    )
    statement_line_ids = fields.Many2one(
        comodel_name='account.reconciliation.statement.line.select',
    )
    amount = fields.Float()
    line_ids = fields.One2many(
        'account.bank.reconciliation.difference.line.wizard',
        'reconciliation_id',
        string='Journal Items',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res["amount"] = self._context.get('amount')
        res["statement_line_ids"] = self._context.get('statement_lines')
        res["move_line_ids"] = self._context.get('move_lines')
        return res

    def action_difference_reconciliation(self):
        sum_move = sum(self.line_ids.mapped('amount'))
        if not self.line_ids:
            raise UserError(_('Not have lines'))
        compare = float_compare(self.amount, sum_move, precision_digits=5, precision_rounding=None)
        if compare != 0:
            raise UserError(_('the amount is different, please checks amounts'))
        statement_line_id = self.statement_line_ids.statement_line_id
        currency_id = statement_line_id.currency_id and statement_line_id.currency_id.id or self.env.company.currency_id.id
        data = {
            'type': 'entry',
            'journal_id': statement_line_id.journal_id.id,
            'currency_id': currency_id,
            'date': statement_line_id.date,
            'partner_id': statement_line_id.partner_id and statement_line_id.partner_id.id or False,
            'ref': statement_line_id.ref,
            'line_ids': [],
        }
        payment_methods = (
            (self.amount > 0) and
            statement_line_id.journal_id.inbound_payment_method_ids or
            statement_line_id.journal_id.outbound_payment_method_ids
        )
        data_payment = {
            'payment_method_id': payment_methods[0].id,
            'payment_type': self.amount > 0 and 'inbound' or 'outbound',
            'partner_id': statement_line_id.partner_id.id,
            'partner_type': statement_line_id.account_id.user_type_id.name,
            'journal_id': statement_line_id.journal_id.id,
            'payment_date': statement_line_id.date,
            'state': 'reconciled',
            'currency_id': currency_id,
            'amount': abs(self.amount),
            'communication': statement_line_id.ref,
            'name': statement_line_id.name or _("Bank Statement %s") % statement_line_ids.date,
        }
        payment = self.env['account.payment'].create(data_payment)
        account_id = self.amount >= 0 \
            and statement_line_id.statement_id.journal_id.default_credit_account_id.id \
            or statement_line_id.statement_id.journal_id.default_debit_account_id.id
        data['line_ids'].append((0, 0, {
            'name': statement_line_id.name,
            'partner_id': statement_line_id.partner_id and statement_line_id.partner_id.id or False,
            'account_id': account_id,
            'credit': self.amount < 0 and -self.amount or 0.0,
            'debit': self.amount > 0 and self.amount or 0.0,
            'statement_line_id': statement_line_id.id,
            'statement_id': statement_line_id.statement_id.id,
            'payment_id': payment.id
        }))
        for line in self.line_ids:
            data['line_ids'].append((0, 0, {
                'name': line.name,
                'partner_id': statement_line_id.partner_id and statement_line_id.partner_id.id or False,
                'account_id': line.account_id.id,
                'analytic_account_id': line.account_analytic_id.id,
                'credit': line.amount > 0 and line.amount or 0.0,
                'debit': line.amount < 0 and -line.amount or 0.0,
                'statement_line_id': statement_line_id.id,
                'statement_id': statement_line_id.statement_id.id,
                'payment_id': payment.id
            }))
        move = self.env['account.move'].with_context(default_journal_id=data['journal_id']).create(data)
        self.move_line_ids.unlink()
        self.statement_line_ids.unlink()


class AccountBankReconciliationDifferenceLineWizard(models.TransientModel):
    _name = 'account.bank.reconciliation.difference.line.wizard'

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

    @api.depends('account_id')
    def _compute_total_amount(self):
        for rec in self:
            rec.amount = self.reconciliation_id.amount - rec.amount
