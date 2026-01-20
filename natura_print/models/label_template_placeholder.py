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
        string="Model",
        required=True,
        ondelete="cascade",
    )
    placeholder = fields.Char(string="Placeholder", required=True)
    field_path = fields.Char(
        string="Field Path",
        help="Dot-separated field path starting from the default model, e.g. product_id.name",
    )
    related_model = fields.Char(
        string="Related Model",
        compute="_compute_related_model",
        readonly=True,
    )
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
    )
    related_field_id = fields.Many2one(
        "ir.model.fields",
        string="Related Field",
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
            if "model_id" not in vals and vals.get("template_id"):
                template = self.env["zpl.label.template"].browse(vals["template_id"])
                if template.model_id:
                    vals["model_id"] = template.model_id.id
            self._build_field_path_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        if "placeholder" in vals:
            vals["placeholder"] = self._normalize_placeholder(vals["placeholder"])
        self._build_field_path_vals(vals, record=self)
        return super().write(vals)

    @api.depends("field_id")
    def _compute_related_model(self):
        for record in self:
            if record.field_id and record.field_id.ttype == "many2one":
                record.related_model = record.field_id.relation
            else:
                record.related_model = False

    @api.onchange("field_id", "related_field_id")
    def _onchange_field_path(self):
        for record in self:
            if record.field_id and record.field_id.ttype != "many2one":
                record.related_field_id = False
            record.field_path = record._build_field_path(
                record.field_id, record.related_field_id
            )

    @staticmethod
    def _build_field_path(field_id, related_field_id):
        if not field_id:
            return ""
        path = field_id.name
        if related_field_id:
            path = f"{path}.{related_field_id.name}"
        return path

    def _build_field_path_vals(self, vals, record=None):
        if vals.get("field_path"):
            return

        field_id = vals.get("field_id")
        related_field_id = vals.get("related_field_id")
        if record and not field_id:
            field_id = record.field_id.id if record.field_id else False
        if record and not related_field_id:
            related_field_id = record.related_field_id.id if record.related_field_id else False

        if field_id:
            field = self.env["ir.model.fields"].browse(field_id)
            related_field = self.env["ir.model.fields"].browse(related_field_id) if related_field_id else False
            vals["field_path"] = self._build_field_path(field, related_field)
