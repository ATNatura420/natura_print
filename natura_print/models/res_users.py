from odoo import api, fields, models


NATURA_PRINT_ALLOWED_MODELS = (
    "product.template",
    "stock.lot",
    "stock.quant",
    "mrp.production",
)


class ResUsers(models.Model):
    _inherit = "res.users"

    natura_print_default_printer_id = fields.Many2one(
        "printers.list",
        string="Default Printer",
    )
    natura_print_template_pref_ids = fields.One2many(
        "natura.print.user.template.pref",
        "user_id",
        string="Default Templates",
    )
    natura_print_csv_encoding = fields.Selection(
        [
            ("utf-8", "UTF-8"),
            ("utf-8-sig", "UTF-8 (BOM)"),
            ("latin-1", "Latin-1"),
        ],
        string="CSV Encoding",
        default="utf-8",
    )
    natura_print_csv_test_rows = fields.Integer(
        string="CSV Test Print Rows",
        default=12,
        help="Number of CSV rows to include when using Test Print in the CSV wizard.",
    )

    def _natura_print_allowed_model_names(self):
        return NATURA_PRINT_ALLOWED_MODELS

    def _natura_print_ensure_template_prefs(self):
        self.ensure_one()
        allowed = self._natura_print_allowed_model_names()
        existing = set(self.natura_print_template_pref_ids.mapped("model_id.model"))
        missing = [model for model in allowed if model not in existing]
        if not missing:
            return
        model_recs = self.env["ir.model"].search([("model", "in", missing)])
        self.env["natura.print.user.template.pref"].create(
            [{"user_id": self.id, "model_id": model.id} for model in model_recs]
        )

    def _natura_print_get_default_template(self, model_name):
        self.ensure_one()
        pref = self.natura_print_template_pref_ids.filtered(
            lambda rec: rec.model_id.model == model_name
        )[:1]
        if not pref or not pref.template_id:
            return False
        if pref.template_id.company_id not in self.env.companies:
            return False
        return pref.template_id

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users:
            user._natura_print_ensure_template_prefs()
        return users


class NaturaPrintUserTemplatePref(models.Model):
    _name = "natura.print.user.template.pref"
    _description = "Natura Print User Template Preference"
    _order = "id"

    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
        domain="[('model', 'in', ('product.template', 'stock.lot', 'stock.quant', 'mrp.production'))]",
    )
    template_id = fields.Many2one(
        "zpl.label.template",
        string="Template",
        domain="[('model_id', '=', model_id), ('company_id', 'in', allowed_company_ids)]",
    )

    _sql_constraints = [
        (
            "natura_print_user_model_unique",
            "unique(user_id, model_id)",
            "Each model can only have one default template per user.",
        ),
    ]
