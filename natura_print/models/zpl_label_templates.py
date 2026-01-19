import re

from odoo import api, fields, models

PLACEHOLDER_RE = re.compile(r"\$\{([^}]+)\}")

class LabelTemplate(models.Model):
    _name = "zpl.label.template"
    _description = "Label Template"

    name = fields.Char('Template Name', required=True, translate=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Default Model",
        required=True,
        default=lambda self: self.env.ref("product.model_product_template"),
        domain="[('model', '=', 'product.template')]",
        ondelete="cascade",
    )
    dpi = fields.Selection(
        [('203', '8 dpmm (203 DPI)'), ('300', '12 dpmm (300 DPI)'), ('600', '24 dpmm (600 DPI)')],
        string='DPI',
        help="Dots Per Inch - print resolution",
        required=True,
    )
    width = fields.Float('Label Width (in)', required=True)
    height = fields.Float('Label Height (in)', required=True)
    zpl_code = fields.Text('ZPL Code', required=True)
    active = fields.Boolean(
        'Active',
        default=True,
        help="If unchecked, it will allow you to hide the template without removing it.",
    )
    placeholder_ids = fields.One2many(
        "natura.print.placeholder",
        "template_id",
        string="Placeholders",
    )

    def _extract_placeholders(self, zpl_code):
        return sorted(set(PLACEHOLDER_RE.findall(zpl_code or "")))

    @api.onchange("zpl_code")
    def _onchange_zpl_code(self):
        placeholders = set(self._extract_placeholders(self.zpl_code))
        existing = set(self.placeholder_ids.mapped("placeholder"))
        for placeholder in placeholders - existing:
            self.placeholder_ids |= self.placeholder_ids.new(
                {"placeholder": placeholder}
            )

    def _sync_placeholders(self):
        for template in self:
            desired = set(self._extract_placeholders(template.zpl_code))
            existing = {ph.placeholder: ph for ph in template.placeholder_ids}

            for placeholder in desired - set(existing):
                self.env["natura.print.placeholder"].create(
                    {
                        "template_id": template.id,
                        "placeholder": placeholder,
                    }
                )

            for placeholder, record in existing.items():
                if placeholder not in desired:
                    record.unlink()

    def _render_zpl(self, record):
        self.ensure_one()
        zpl = self.zpl_code or ""
        mapping = {}
        for ph in self.placeholder_ids:
            key = ph.placeholder
            if key and key.startswith("${") and key.endswith("}"):
                key = key[2:-1].strip()
            mapping[key] = ph
        for placeholder in self._extract_placeholders(zpl):
            value = ""
            ph = mapping.get(placeholder)
            if ph and ph.field_id:
                field_value = record[ph.field_id.name]
                if isinstance(field_value, models.BaseModel):
                    value = field_value.display_name or ""
                else:
                    value = "" if field_value in (False, None) else str(field_value)
            zpl = zpl.replace(f"${{{placeholder}}}", value)
        return zpl

    def action_open_test_print(self):
        self.ensure_one()
        action = self.env.ref("natura_print.action_natura_print_test_print").read()[0]
        action["context"] = {
            "default_template_id": self.id,
        }
        return action

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_placeholders()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "zpl_code" in vals:
            self._sync_placeholders()
        return res
