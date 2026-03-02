import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    natura_print_label_config_required = fields.Boolean(
        string="Label Config Required",
        help="If enabled, transfer-out line printing uses this contact's template configuration.",
    )
    natura_print_label_line_ids = fields.One2many(
        "natura.print.partner.label.line",
        "partner_id",
        string="Label Templates",
    )


class NaturaPrintPartnerLabelLine(models.Model):
    _name = "natura.print.partner.label.line"
    _description = "Natura Print Partner Label Line"
    _order = "id"

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        default=lambda self: self.env.ref("product.model_product_template"),
        domain="[('model', 'in', ('product.template', 'stock.quant', 'stock.lot'))]",
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
        domain="[('model_id', '=', model_id), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        ondelete="restrict",
    )
    qty_multiplier = fields.Float(
        string="Qty Multiplier",
        default=1.0,
        required=True,
        help="Multiplier applied to transfer line quantity to compute print quantity.",
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

    @api.onchange("template_id")
    def _onchange_template_id_sync_model(self):
        for rec in self:
            if rec.template_id and rec.template_id.model_id:
                rec.model_id = rec.template_id.model_id

    @api.constrains("template_id", "model_id")
    def _check_template_model_match(self):
        for rec in self:
            if rec.template_id and rec.model_id and rec.template_id.model_id != rec.model_id:
                raise ValidationError(_("Template model must match the selected model."))
