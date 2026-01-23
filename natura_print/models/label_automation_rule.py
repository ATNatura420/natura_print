from odoo import fields, models


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
        domain="[('model', 'in', ('product.template', 'stock.lot', 'stock.quant', 'mrp.production'))]",
        ondelete="cascade",
    )
    webhook_url = fields.Char(
        string="Webhook URL",
        required=True,
    )
