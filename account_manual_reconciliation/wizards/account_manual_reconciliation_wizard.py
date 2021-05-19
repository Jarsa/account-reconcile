# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, fields, models


class AccountManualReconciliationWizard(models.TransientModel):
    _name = 'account.manual.reconciliation.wizard'

    date = fields.Date(
        required=True,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        required=True,
    )

    def action_reconciliation(self):
        self.ensure_one()
        context = self._context.copy()
        context.update({
            'journal_id': self.journal_id.id,
            'date': self.date,
        })
        return {
            'name': _('Manual Reconciliation'),
            'res_model': 'account.manual.reconciliation',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'account_manual_reconciliation.'
                'account_manual_reconciliation_form'
            ).id,
            'context': context,
            'type': 'ir.actions.act_window',
        }
