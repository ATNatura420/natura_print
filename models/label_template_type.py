from odoo import fields, models


class NaturaPrintLabelTemplateType(models.Model):
    _name = "natura.print.label.template.type"
    _description = "Natura Print Label Template Type"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "natura_print_label_template_type_name_unique",
            "unique(name)",
            "Template type name must be unique.",
        ),
    ]
