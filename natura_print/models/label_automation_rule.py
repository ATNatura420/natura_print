from odoo import api, fields, models


class NaturaPrintLabelAutomation(models.Model):
    _name = "natura.print.label.automation"
    _description = "Natura Print Label Automation"
    _rec_name = "name"

    name = fields.Char(
        string="Name",
        required=True,
    )
    active = fields.Boolean(
        default=True,
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Default Model",
        required=True,
        ondelete="cascade",
    )
    webhook_url = fields.Char(
        string="Webhook URL",
        required=True,
    )
    available_model_ids = fields.Many2many(
        "ir.model",
        compute="_compute_available_models",
        store=False,
    )

    @api.depends()
    def _compute_available_models(self):
        templates = self.env["zpl.label.template"].sudo().search([("active", "=", True)])
        models = templates.mapped("model_id")
        if not models:
            allowed_model_names = [
                "product.template",
                "stock.lot",
                "stock.quant",
                "mrp.production",
            ]
            models = self.env["ir.model"].sudo().search([("model", "in", allowed_model_names)])
        for record in self:
            record.available_model_ids = models
