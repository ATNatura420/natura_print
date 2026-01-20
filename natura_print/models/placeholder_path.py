from odoo import api, fields, models


class NaturaPrintPlaceholderPath(models.Model):
    _name = "natura.print.placeholder.path"
    _description = "Natura Print Placeholder Path"
    _order = "sequence, id"

    placeholder_id = fields.Many2one(
        "natura.print.placeholder",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    allowed_model = fields.Char(
        string="Allowed Model",
        compute="_compute_allowed_model",
    )
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        domain="[('model', '=', allowed_model)]",
    )
    relation_model = fields.Char(
        string="Relation Model",
        compute="_compute_relation_model",
        readonly=True,
    )

    @api.depends("field_id")
    def _compute_relation_model(self):
        for line in self:
            if line.field_id and line.field_id.ttype in ("many2one", "one2many", "many2many"):
                line.relation_model = line.field_id.relation
            else:
                line.relation_model = False

    @api.depends(
        "placeholder_id",
        "placeholder_id.model_id",
        "placeholder_id.path_line_ids.field_id",
        "placeholder_id.path_line_ids.sequence",
    )
    def _compute_allowed_model(self):
        for line in self:
            if not line.placeholder_id or not line.placeholder_id.model_id:
                line.allowed_model = False
                continue

            ordered = line.placeholder_id.path_line_ids.sorted("sequence")
            prev_line = False
            for current in ordered:
                if current == line:
                    break
                prev_line = current

            if not prev_line or not prev_line.field_id:
                line.allowed_model = line.placeholder_id.model_id.model
                continue

            if prev_line.field_id.ttype in ("many2one", "one2many", "many2many"):
                line.allowed_model = prev_line.field_id.relation
            else:
                line.allowed_model = False
