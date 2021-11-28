# Copyright 2021 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

{
    "name": "Account Manual Reconciliation",
    "summary": "Creates a new reconciliation model",
    "version": "13.0.1.0.0",
    "depends": ["account", "account_reports"],
    "author": "Jarsa, Odoo Community Association (OCA)",
    "website": "https://www.github.com/OCA/account-reconcile",
    "category": "Finance",
    "data": [
        "views/account_manual_reconciliation_view.xml",
        "views/account_bank_statement_views.xml",
        "views/account_move_views.xml",
        "wizards/account_manual_reconciliation_wizard_view.xml",
        "wizards/account_bank_reconciliation_difference_wizard_view.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
}
