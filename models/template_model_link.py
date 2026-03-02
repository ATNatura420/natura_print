from odoo import fields, models


class NaturaPrintTemplateModelLink(models.Model):
    _name = "natura.print.template.model.link"
    _description = "Natura Print Template Model Link"
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
    default_model = fields.Char(
        string="Default Model",
        related="template_id.model_id.model",
        store=True,
        readonly=True,
    )
    relation_field_id = fields.Many2one(
        "ir.model.fields",
        string="Link Field",
        required=True,
        ondelete="cascade",
        domain="[('model_id', '=', model_id), ('ttype', '=', 'many2one')]",
        help="Field on the selected model that links back to the default model.",
    )
