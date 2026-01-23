from odoo import api, fields, models


class NaturaPrintPlaceholder(models.Model):
    _name = "natura.print.placeholder"
    _description = "Natura Print Placeholder"
    _order = "id"

    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        "ir.model",
        related="template_id.model_id",
        store=True,
        readonly=True,
    )
    placeholder = fields.Char(string="Placeholder", required=True)
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
    )

    @staticmethod
    def _normalize_placeholder(value):
        if not value:
            return value
        value = value.strip()
        if value.startswith("${") and value.endswith("}"):
            return value[2:-1].strip()
        return value

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "placeholder" in vals:
                vals["placeholder"] = self._normalize_placeholder(vals["placeholder"])
        return super().create(vals_list)

    def write(self, vals):
        if "placeholder" in vals:
            vals["placeholder"] = self._normalize_placeholder(vals["placeholder"])
        return super().write(vals)
