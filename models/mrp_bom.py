import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    natura_print_label_line_ids = fields.One2many(
        "natura.print.bom.label.line",
        "bom_id",
        string="Label Templates",
    )


class NaturaPrintBomLabelLine(models.Model):
    _name = "natura.print.bom.label.line"
    _description = "Natura Print BoM Label Line"
    _order = "id"

    bom_id = fields.Many2one(
        "mrp.bom",
        required=True,
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
        domain="[('model_id.model', 'in', ('product.template', 'sale.order.line')), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        ondelete="restrict",
    )
    qty_multiplier = fields.Float(
        string="Qty Multiplier",
        default=1.0,
        required=True,
        help="Multiplier applied to the sales order line quantity to compute print quantity.",
    )

    @api.constrains("qty_multiplier")
    def _check_qty_multiplier(self):
        for rec in self:
            if rec.qty_multiplier <= 0:
                raise ValidationError(_("Qty Multiplier must be greater than 0."))

    def get_effective_qty(self, base_qty):
        self.ensure_one()
        value = (base_qty or 0.0) * (self.qty_multiplier or 0.0)
        return max(1, int(math.ceil(value)))
