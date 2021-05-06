# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountManualReconciliation(models.TransientModel):
    _name = 'account.manual.reconciliation'
    _description = 'Manual Reconciliation Model'

    statement_line_ids = fields.One2many(
        comodel_name='account.reconciliation.statement.line',
        inverse_name='reconciliation_id',
    )
    move_line_ids = fields.One2many(
        comodel_name='account.reconciliation.move.line',
        inverse_name='reconciliation_id',
    )
    selected_statement_line_ids = fields.One2many(
        comodel_name='account.reconciliation.statement.line.select',
        inverse_name='reconciliation_id',
    )
    selected_move_line_ids = fields.One2many(
        comodel_name='account.reconciliation.move.line.select',
        inverse_name='reconciliation_id',
    )

    difference = fields.Float(
        compute='_compute_dfference_selected'
    )

    @api.depends('selected_move_line_ids', 'selected_statement_line_ids')
    def _compute_dfference_selected(self):
        for rec in self:
            sum_statement = sum(rec.selected_statement_line_ids.mapped('amount'))
            sum_move = sum(rec.selected_move_line_ids.mapped('amount'))
            rec.difference = sum_move - sum_statement

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        date = self._context.get('date')
        journal_id = self._context.get('journal_id')
        journal = self.env['account.journal'].browse(journal_id)
        self.env.cr.execute("""
        SELECT
            absl.id AS statement_line_id,
            COALESCE(absl.currency_id, company.currency_id) AS currency_id
        FROM account_bank_statement_line AS absl
        LEFT JOIN account_move_line AS aml ON aml.statement_line_id = absl.id
        LEFT JOIN res_company AS company ON company.id = absl.company_id
        WHERE
            absl.date <= %s AND
            absl.journal_id = %s AND
            aml.statement_line_id IS NULL
        ORDER BY absl.date

        """, (date, journal_id))
        statement_lines = [(0, 0, line) for line in self.env.cr.dictfetchall()]

        self.env.cr.execute("""
        SELECT
            aml.id AS move_line_id,
            COALESCE(aml.currency_id, company.currency_id) AS currency_id
        FROM account_move_line AS aml
        LEFT JOIN account_move AS am ON am.id = aml.move_id
        LEFT JOIN res_company AS company ON company.id = aml.company_id
        WHERE
            aml.date <= %s AND
            aml.account_id = %s AND
            aml.statement_line_id IS NULL AND
            am.state = 'posted'
        ORDER BY aml.date

        """, (date, journal.default_debit_account_id.id, ))
        move_line_ids = [(0, 0, line) for line in self.env.cr.dictfetchall()]

        res['statement_line_ids'] = statement_lines
        res['move_line_ids'] = move_line_ids
        return res

    def reconcile(self):
        for rec in self:
            if len(rec.selected_statement_line_ids) > 1:
                raise UserError(_('A selected move line was already reconciled.'))
            sum_statement = sum(rec.selected_statement_line_ids.mapped('amount'))
            sum_move = sum(rec.selected_move_line_ids.mapped('amount'))
            compare = float_compare(sum_statement, sum_move, precision_digits=5, precision_rounding=None)
            if compare != 0:
                difference = sum_statement - sum_move
                context = rec._context.copy()
                context.update({
                    'amount': difference,
                    'statement_lines': rec.selected_statement_line_ids[0].id,
                    'move_lines': rec.selected_move_line_ids.ids[0],
                })
                for statement in rec.selected_statement_line_ids:
                    statement.statement_line_id.write({
                        'move_name': rec.selected_move_line_ids.move_line_id[0].name,
                        'sequence': len(rec.selected_move_line_ids)
                    })
                for move in rec.selected_move_line_ids:
                    stateme = rec.selected_statement_line_ids.statement_line_id[0]
                    move.move_line_id.write({
                        'statement_line_id': stateme.id,
                        'statement_id': stateme.statement_id.id
                    })
                    payment = move.move_line_id.payment_id
                    if payment:
                        payment.write({
                            'state': 'reconciled'
                        })
                return {
                    'name': ('Manual Reconciliation'),
                    'res_model': 'account.bank.reconciliation.difference.wizard',
                    'view_mode': 'form',
                    'view_id': self.env.ref(
                        'account_manual_reconciliation.'
                        'account_bank_reconciliation_difference_wizard_view'
                    ).id,
                    'context': context,
                    'target': 'new',
                    'type': 'ir.actions.act_window',
                }
            stateme = rec.selected_statement_line_ids.statement_line_id[0]
            for statement in rec.selected_statement_line_ids:
                statement.statement_line_id.write({
                    'move_name': rec.selected_move_line_ids.move_line_id[0].name,
                    'sequence': len(rec.selected_move_line_ids)
                })
                rec.write({
                    'selected_statement_line_ids': [(2, statement.id, 0)]
                })
            for move in rec.selected_move_line_ids:
                move.move_line_id.write({
                    'statement_line_id': stateme.id,
                    'statement_id': stateme.statement_id.id
                })
                payment = move.move_line_id.payment_id
                if payment:
                    payment.write({
                        'state': 'reconciled'
                    })
                rec.write({
                    'selected_move_line_ids': [(2, move.id, 0)]
                })


class AccounReconcileStatementLine(models.TransientModel):
    _name = 'account.reconciliation.statement.line'
    _description = 'Statement Lines'

    reconciliation_id = fields.Many2one(
        comodel_name='account.manual.reconciliation',
    )
    statement_line_id = fields.Many2one(
        comodel_name='account.bank.statement.line',
    )
    partner_id = fields.Many2one(
        related='statement_line_id.partner_id',
        store=True,
    )
    date = fields.Date(
        related='statement_line_id.date',
        store=True,
    )
    name = fields.Char(
        related='statement_line_id.name',
        store=True,
    )
    ref = fields.Char(
        related='statement_line_id.ref',
        store=True,
    )
    note = fields.Text(
        related='statement_line_id.note',
        store=True,
    )
    amount = fields.Monetary(
        related='statement_line_id.amount',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
    )

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'statement_line_ids': [(2, rec.id, 0)],
                'selected_statement_line_ids': [(0, 0, {
                    'statement_line_id': rec.statement_line_id.id,
                    'currency_id': rec.currency_id.id,
                })]
            })


class AccounReconcileMoveLine(models.TransientModel):
    _name = 'account.reconciliation.move.line'
    _description = 'Move Lines'

    reconciliation_id = fields.Many2one(
        comodel_name='account.manual.reconciliation',
    )
    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
    )
    partner_id = fields.Many2one(
        related='move_line_id.partner_id',
    )
    date = fields.Date(
        related='move_line_id.date',
        store=True,
    )
    name = fields.Char(
        related='move_line_id.name',
        store=True,
    )
    ref = fields.Char(
        related='move_line_id.ref',
        store=True,
    )
    note = fields.Text(
        related='move_line_id.internal_note',
        store=True,
    )
    amount = fields.Monetary(
        related='move_line_id.balance',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
    )

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'move_line_ids': [(2, rec.id, 0)],
                'selected_move_line_ids': [(0, 0, {
                    'move_line_id': rec.move_line_id.id,
                    'currency_id': rec.currency_id.id,
                })]
            })


class AccounReconcileStatementLineSelect(models.TransientModel):
    _name = 'account.reconciliation.statement.line.select'
    _inherit = 'account.reconciliation.statement.line'
    _description = 'Selected Statement Lines'

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'selected_statement_line_ids': [(2, rec.id, 0)],
                'statement_line_ids': [(0, 0, {
                    'statement_line_id': rec.statement_line_id.id,
                    'currency_id': rec.currency_id.id,
                })]
            })


class AccounReconcileMoveLineSelect(models.TransientModel):
    _name = 'account.reconciliation.move.line.select'
    _inherit = 'account.reconciliation.move.line'
    _description = 'Selected Move Lines'

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'selected_move_line_ids': [(2, rec.id, 0)],
                'move_line_ids': [(0, 0, {
                    'move_line_id': rec.move_line_id.id,
                    'currency_id': rec.currency_id.id,
                })]
            })
