# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare
from odoo.tools.float_utils import float_round


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
        compute='_compute_difference_selected',
    )

    @api.depends('selected_move_line_ids', 'selected_statement_line_ids')
    def _compute_difference_selected(self):
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
            COALESCE(absl.currency_id, company.currency_id) AS currency_id,
            absl.partner_id
        FROM account_bank_statement_line AS absl
        LEFT JOIN account_move_line AS aml ON aml.statement_line_id = absl.id
        LEFT JOIN res_company AS company ON company.id = absl.company_id
        WHERE
            absl.date <= %s AND
            absl.journal_id = %s AND
            aml.statement_line_id IS NULL
        ORDER BY absl.amount DESC

        """, (date, journal_id))
        statement_lines = [(0, 0, line) for line in self.env.cr.dictfetchall()]

        self.env.cr.execute("""
        SELECT
            aml.id AS move_line_id,
            COALESCE(aml.currency_id, company.currency_id) AS currency_id,
            aml.partner_id
        FROM account_move_line AS aml
        LEFT JOIN account_move AS am ON am.id = aml.move_id
        LEFT JOIN res_company AS company ON company.id = aml.company_id
        WHERE
            aml.date <= %s AND
            aml.account_id = %s AND
            aml.statement_line_id IS NULL AND
            am.state = 'posted'
        ORDER BY aml.balance DESC

        """, (date, journal.default_debit_account_id.id, ))
        move_line_ids = [(0, 0, line) for line in self.env.cr.dictfetchall()]

        res['statement_line_ids'] = statement_lines
        res['move_line_ids'] = move_line_ids
        return res

    def _action_difference_wizard(self, context):
        self.ensure_one()
        new_context = self._context.copy()
        new_context.update(context)
        return {
            'name': _('Manual Reconciliation'),
            'res_model': 'account.bank.reconciliation.difference.wizard',
            'view_mode': 'form',
            'context': new_context,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def _cancel_moves(self):
        for move in self.selected_move_line_ids:
            move.move_line_id.payment_id.action_draft()
            move.move_line_id.payment_id.cancel()
            move.move_line_id.move_id.button_cancel()
            move.unlink()

    def _statement_reconcile(self):
        self.ensure_one()
        context = {
            'amount': self.selected_statement_line_ids.mapped('amount')[0],
            'statement_lines': self.selected_statement_line_ids.ids,
        }
        return self._action_difference_wizard(context)

    def _statement_reconcile_move_update(self):
        move = self.selected_move_line_ids.move_line_id
        balance = move.balance / len(self.selected_statement_line_ids)
        move.move_id['line_ids'].append((1, move.id, {
            'credit': balance < 0 and -balance or 0.0,
            'debit': balance > 0 and balance or 0.0,
        }))
        for statement in self.selected_statement_line_ids:
            move.move_id['line_ids'].append((0, 0, {
                'name': move.name,
                'partner_id': move.partner_id.id,
                'account_id': move.account_id.id,
                'credit': balance < 0 and -balance or 0.0,
                'debit': balance > 0 and balance or 0.0,
                'statement_line_id': statement.id,
                'statement_id': statement.statement_id.id,
                'payment_id': move.payment_id.id
            }))

    def conciliaci(self):
        len_state = len(self.selected_statement_line_ids)
        if len_state == 1:
            state = self.selected_statement_line_ids
            for move in self.selected_move_line_ids:
                move.move_line_id.write({
                    'statement_line_id': state.statement_line_id.id,
                    'statement_id': state.statement_line_id.statement_id.id
                })
                payment = move.move_line_id.payment_id
                if payment:
                    payment.write({
                        'state': 'reconciled'
                    })
                self.write({'selected_move_line_ids': [(2, move.id, 0)]})
            self.write(
                {'selected_statement_line_ids': [(2, state.id, 0)]}
            )
        else:
            count = 1
            while count <= len_state:
                statements = self.selected_statement_line_ids
                moves = self.selected_move_line_ids
                if statements[0].amount == moves[0].amount:
                    statements[0].statement_line_id.write({
                        'move_name': moves.move_line_id[0].name,
                        'sequence': len(moves)
                    })
                    moves[0].move_line_id.write({
                        'statement_line_id': statements[0].id,
                        'statement_id': statements[0].statement_id.id
                    })
                    payment = moves[0].move_line_id.payment_id
                    if payment:
                        payment.write({
                            'state': 'reconciled'
                        })
                    self.write({
                        'selected_statement_line_ids': [(2, statements[0].id, 0)],
                        'selected_move_line_ids': [(2, moves[0].id, 0)],
                    })
                    count += 1
                else:
                    raise UserError(_('The position are diferents'))

    def reconcile(self):
        for rec in self:
            count_statement = len(rec.selected_statement_line_ids)
            count_moves = len(rec.selected_move_line_ids)
            sum_statement = sum(rec.selected_statement_line_ids.mapped('amount'))
            sum_statement = float_round(sum_statement, precision_digits=2,)
            sum_move = sum(rec.selected_move_line_ids.mapped('amount'))
            sum_move = float_round(sum_move, precision_digits=2,)
            if count_moves > 1 and count_statement == 0:
                if sum_move == 0.00:
                    return self._cancel_moves()
                raise UserError(_('The difference in moves is not 0.', sum_move))
            if count_statement > 1 and count_moves == 0:
                if sum_statement == 0.00:
                    return self._statement_reconcile()
                raise UserError(_('The difference in statements is not 0.', sum_statement))
            if count_statement > 1 and count_moves == 1:
                return self._statement_reconcile_move_update()
            compare = float_compare(
                sum_statement,
                sum_move, precision_digits=5, precision_rounding=None
            )
            if compare != 0:
                difference = sum_statement - sum_move
                context = {
                    'amount': difference,
                    'statement_lines': rec.selected_statement_line_ids.ids,
                    'move_lines_ids': rec.selected_move_line_ids.ids
                }
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
                return self._action_difference_wizard(context)
            stateme = rec.selected_statement_line_ids.statement_line_id[0]
            if len(rec.selected_statement_line_ids) != 1 and len(rec.selected_move_line_ids) != 1:
                return self.conciliaci()
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
    partner_id = fields.Many2one(
        comodel_name='res.partner'
    )

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'statement_line_ids': [(2, rec.id, 0)],
                'selected_statement_line_ids': [(0, 0, {
                    'statement_line_id': rec.statement_line_id.id,
                    'currency_id': rec.currency_id.id,
                    'partner_id': rec.partner_id.id,
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
    partner_id = fields.Many2one(
        comodel_name='res.partner'
    )

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'move_line_ids': [(2, rec.id, 0)],
                'selected_move_line_ids': [(0, 0, {
                    'move_line_id': rec.move_line_id.id,
                    'currency_id': rec.currency_id.id,
                    'partner_id': rec.partner_id.id,
                })]
            })


class AccounReconcileStatementLineSelect(models.TransientModel):
    _name = 'account.reconciliation.statement.line.select'
    _inherit = 'account.reconciliation.statement.line'
    _description = 'Selected Statement Lines'

    statement_line_difference_wizard = fields.Many2one(
        'account.bank.reconciliation.difference.wizard'
    )

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'selected_statement_line_ids': [(2, rec.id, 0)],
                'statement_line_ids': [(0, 0, {
                    'statement_line_id': rec.statement_line_id.id,
                    'currency_id': rec.currency_id.id,
                    'partner_id': rec.partner_id.id,
                })]
            })


class AccounReconcileMoveLineSelect(models.TransientModel):
    _name = 'account.reconciliation.move.line.select'
    _inherit = 'account.reconciliation.move.line'
    _description = 'Selected Move Lines'

    move_line_difference_wizard = fields.Many2one(
        'account.bank.reconciliation.difference.wizard'
    )

    def select_line(self):
        for rec in self:
            rec.reconciliation_id.write({
                'selected_move_line_ids': [(2, rec.id, 0)],
                'move_line_ids': [(0, 0, {
                    'move_line_id': rec.move_line_id.id,
                    'currency_id': rec.currency_id.id,
                    'partner_id': rec.partner_id.id,
                })]
            })
