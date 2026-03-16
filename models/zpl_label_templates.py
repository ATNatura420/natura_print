import base64
import re

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

PLACEHOLDER_RE = re.compile(r"\$\{([^}]+)\}")

class LabelTemplate(models.Model):
    _name = "zpl.label.template"
    _description = "Label Template"
    _order = "is_product_specific desc, name"

    name = fields.Char('Template Name', required=True, translate=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Default Model",
        required=True,
        default=lambda self: self.env.ref("product.model_product_template"),
        domain="[('model', 'in', ('product.template', 'stock.lot', 'stock.quant', 'mrp.production', 'sale.order.line'))]",
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=False,
        index=True,
        ondelete="restrict",
        help=(
            "If set, this template is only available for that company. "
            "If left empty, this template is available across allowed companies."
        ),
    )
    template_type_id = fields.Many2one(
        "natura.print.label.template.type",
        string="Template Type",
        ondelete="set null",
    )
    is_product_specific = fields.Boolean(
        string="Product Specific",
        help="If enabled, this template is only available for the selected product.",
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Specific Product",
        domain="[('active', '=', True)]",
        ondelete="restrict",
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
    preview_image = fields.Binary(string="Preview", attachment=False)
    preview_error = fields.Char(string="Preview Error", readonly=True)
    placeholder_ids = fields.One2many(
        "natura.print.placeholder",
        "template_id",
        string="Placeholders",
    )

    @api.onchange("is_product_specific")
    def _onchange_is_product_specific(self):
        if not self.is_product_specific:
            self.product_tmpl_id = False

    @api.constrains("is_product_specific", "product_tmpl_id")
    def _check_product_specific_template(self):
        for template in self:
            if template.is_product_specific and not template.product_tmpl_id:
                raise ValidationError("Please select a product for product-specific templates.")

    @api.model
    def _natura_print_available_domain(self, model_name, product_tmpl_ids=None):
        domain = [
            ("model_id.model", "=", model_name),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", self.env.companies.ids),
        ]
        if product_tmpl_ids:
            domain += [
                "|",
                ("is_product_specific", "=", False),
                ("product_tmpl_id", "in", product_tmpl_ids),
            ]
        else:
            domain += [("is_product_specific", "=", False)]
        return domain

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
                        "model_id": template.model_id.id,
                    }
                )

            for placeholder, record in existing.items():
                if placeholder not in desired:
                    record.unlink()
                elif not record.model_id:
                    record.model_id = template.model_id.id

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
            if ph:
                field_path = (ph.field_path or "").strip()
                if not field_path and ph.field_id:
                    field_path = ph.field_id.name
                if field_path:
                    raw_value = self._resolve_field_path(record, field_path, as_text=False)
                    raw_value = self._filter_attribute_records(raw_value, ph.attribute_name)
                    value = self._value_to_text(raw_value)
                    if not value and ph.attribute_name:
                        value = self._resolve_attribute_value(record, raw_value, ph.attribute_name)
                value = ph._apply_transform(value)
            zpl = zpl.replace(f"${{{placeholder}}}", value)
        return zpl

    def _render_zpl_from_values(self, values, skip_transform_placeholders=None):
        self.ensure_one()
        zpl = self.zpl_code or ""
        skip_transform_placeholders = set(skip_transform_placeholders or [])
        placeholder_map = {}
        for ph in self.placeholder_ids:
            key = ph.placeholder
            if key and key.startswith("${") and key.endswith("}"):
                key = key[2:-1].strip()
            placeholder_map[key] = ph
        for placeholder in self._extract_placeholders(zpl):
            if placeholder not in values:
                continue
            value = values.get(placeholder)
            value = "" if value is None else str(value)
            ph = placeholder_map.get(placeholder)
            if ph and placeholder not in skip_transform_placeholders:
                value = ph._apply_transform(value)
            zpl = zpl.replace(f"${{{placeholder}}}", value)
        return zpl

    def _values_from_record(self, record):
        self.ensure_one()
        zpl = self.zpl_code or ""
        mapping = {}
        placeholder_map = {}
        for ph in self.placeholder_ids:
            key = ph.placeholder
            if key and key.startswith("${") and key.endswith("}"):
                key = key[2:-1].strip()
            placeholder_map[key] = ph

        for placeholder in self._extract_placeholders(zpl):
            value = ""
            ph = placeholder_map.get(placeholder)
            if ph:
                field_path = (ph.field_path or "").strip()
                if not field_path and ph.field_id:
                    field_path = ph.field_id.name
                if field_path:
                    raw_value = self._resolve_field_path(record, field_path, as_text=False)
                    raw_value = self._filter_attribute_records(raw_value, ph.attribute_name)
                    value = self._value_to_text(raw_value)
                    if not value and ph.attribute_name:
                        value = self._resolve_attribute_value(record, raw_value, ph.attribute_name)
                value = ph._apply_transform(value)
            mapping[placeholder] = value
        return mapping

    @staticmethod
    def _resolve_field_path(record, field_path, as_text=True):
        value = record
        try:
            for part in field_path.split("."):
                if not value:
                    return "" if as_text else value
                value = value[part]
        except Exception:
            return ""

        return LabelTemplate._value_to_text(value) if as_text else value

    @staticmethod
    def _value_to_text(value):
        if isinstance(value, models.BaseModel):
            return ", ".join(value.mapped("display_name")) if value else ""
        return "" if value in (False, None) else str(value)

    @staticmethod
    def _filter_attribute_records(value, attribute_name):
        if not attribute_name or not isinstance(value, models.BaseModel):
            return value
        target = str(attribute_name).strip().lower()
        if not target:
            return value
        filtered = value.browse()
        for rec in value:
            attr = ""
            if "attribute_id" in rec._fields and rec.attribute_id:
                attr = rec.attribute_id.name or rec.attribute_id.display_name or ""
            elif "attribute_line_id" in rec._fields and rec.attribute_line_id and rec.attribute_line_id.attribute_id:
                attr = rec.attribute_line_id.attribute_id.name or rec.attribute_line_id.attribute_id.display_name or ""
            elif (
                "product_attribute_value_id" in rec._fields
                and rec.product_attribute_value_id
                and rec.product_attribute_value_id.attribute_id
            ):
                attr = rec.product_attribute_value_id.attribute_id.name or rec.product_attribute_value_id.attribute_id.display_name or ""
            if target in str(attr).strip().lower():
                filtered |= rec
        return filtered

    def _resolve_attribute_value(self, source_record, raw_value, attribute_name):
        attr_target = (attribute_name or "").strip().lower()
        if not attr_target:
            return ""

        products = self.env["product.product"]
        templates = self.env["product.template"]

        def _collect_candidates(candidate):
            nonlocal products, templates
            if not isinstance(candidate, models.BaseModel) or not candidate:
                return
            if candidate._name == "product.product":
                products |= candidate
            if candidate._name == "product.template":
                templates |= candidate
            if "product_id" in candidate._fields:
                products |= candidate.mapped("product_id")
            if "product_tmpl_id" in candidate._fields:
                templates |= candidate.mapped("product_tmpl_id")

        _collect_candidates(source_record)
        _collect_candidates(raw_value)
        templates |= products.mapped("product_tmpl_id")

        # Variant-level selected values (best for quant/lot/product.product contexts)
        ptavs = products.mapped("product_template_attribute_value_ids").filtered(
            lambda val: (val.attribute_id.name or "").strip().lower() == attr_target
        )
        if ptavs:
            return ", ".join(ptavs.mapped("name"))

        # Template-level possible values fallback
        lines = templates.mapped("attribute_line_ids").filtered(
            lambda line: (line.attribute_id.name or "").strip().lower() == attr_target
        )
        if lines:
            return ", ".join(lines.mapped("value_ids.name"))

        return ""

    def action_open_test_print(self):
        self.ensure_one()
        action = self.env.ref("natura_print.action_natura_print_test_print").read()[0]
        action["context"] = {
            "default_template_id": self.id,
        }
        return action

    def action_update_preview(self):
        self.ensure_one()
        self._update_preview_image(silent=False)
        return True


    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_placeholders()
        for record in records:
            record._update_preview_image(silent=True)
        return records

    def write(self, vals):
        res = super().write(vals)
        if "zpl_code" in vals:
            self._sync_placeholders()
        if {"zpl_code", "dpi", "width", "height"} & set(vals):
            for record in self:
                record._update_preview_image(silent=True)
        return res


    def _labelary_dpmm(self):
        mapping = {
            "203": "8",
            "300": "12",
            "600": "24",
        }
        return mapping.get(self.dpi)

    def _update_preview_image(self, silent=False):
        self.ensure_one()
        self.preview_error = False
        if not self.zpl_code or not self.width or not self.height or not self.dpi:
            self.preview_image = False
            return

        dpmm = self._labelary_dpmm()
        if not dpmm:
            self.preview_image = False
            self.preview_error = "Unsupported DPI for Labelary preview."
            if not silent:
                raise UserError(self.preview_error)
            return

        url = (
            f"https://api.labelary.com/v1/printers/{dpmm}dpmm/"
            f"labels/{self.width}x{self.height}/0/"
        )
        try:
            response = requests.post(
                url,
                data=self.zpl_code.encode("utf-8"),
                headers={"Accept": "image/png"},
                timeout=10,
            )
            response.raise_for_status()
            self.preview_image = base64.b64encode(response.content)
        except requests.RequestException as exc:
            self.preview_image = False
            self.preview_error = f"Preview failed: {exc}"
            if not silent:
                raise UserError(self.preview_error)
