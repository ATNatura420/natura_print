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

    transform_type = fields.Selection(
        [
            ("none", "None"),
            ("split", "Split by Delimiter"),
            ("first_n", "Take First N Characters"),
            ("last_n", "Take Last N Characters"),
            ("replace", "Replace Text"),
            ("case", "Uppercase / Lowercase"),
            ("prefix", "Prefix"),
            ("suffix", "Suffix"),
            ("between", "Extract Between Two Words"),
        ],
        string="Transform",
        default="none",
    )
    split_delimiter = fields.Char(string="Delimiter")
    split_part = fields.Selection(
        [("first", "First"), ("last", "Last"), ("index", "Index")],
        string="Which Part",
        default="last",
    )
    split_index = fields.Integer(string="Index (1-based)")
    first_n = fields.Integer(string="First N")
    last_n = fields.Integer(string="Last N")
    replace_from = fields.Char(string="Replace This")
    replace_to = fields.Char(string="With This")
    case_type = fields.Selection(
        [("upper", "Uppercase"), ("lower", "Lowercase"), ("title", "Title Case")],
        string="Case",
    )
    prefix_text = fields.Char(string="Prefix Text")
    suffix_text = fields.Char(string="Suffix Text")
    between_start = fields.Char(string="Start Text")
    between_end = fields.Char(string="End Text")
   
    field_path = fields.Char(
        string="Field Path",
        compute="_compute_field_path",
        store=True,
        readonly=True,
        help="Dot-separated field path starting from the default model, e.g. product_id.name",
    )
    attribute_name = fields.Char(
        string="Attribute Name",
        help=(
            "Optional attribute filter for variant values, e.g. Size or Color. "
            "Used by attribute fallback resolution."
        ),
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
    path_line_ids = fields.One2many(
        "natura.print.placeholder.path",
        "placeholder_id",
        string="Field Path Lines",
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
        return super().create(vals_list)

    def write(self, vals):
        if "placeholder" in vals:
            vals["placeholder"] = self._normalize_placeholder(vals["placeholder"])
        return super().write(vals)

    @api.depends("field_id")
    def _compute_related_model(self):
        for record in self:
            if record.field_id and record.field_id.ttype in ("many2one", "one2many", "many2many"):
                record.related_model = record.field_id.relation
            else:
                record.related_model = False

    @api.onchange("field_id", "related_field_id")
    def _onchange_field_path(self):
        for record in self:
            if record.field_id and record.field_id.ttype not in ("many2one", "one2many", "many2many"):
                record.related_field_id = False
            if not record.path_line_ids:
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

    @api.depends("path_line_ids.field_id", "path_line_ids.sequence", "field_id", "related_field_id")
    def _compute_field_path(self):
        for record in self:
            if record.path_line_ids:
                parts = [
                    line.field_id.name
                    for line in record.path_line_ids.sorted("sequence")
                    if line.field_id
                ]
                record.field_path = ".".join(parts)
            else:
                record.field_path = record._build_field_path(
                    record.field_id, record.related_field_id
                )

    def _apply_transform(self, value):
        self.ensure_one()
        text = "" if value is None else str(value)
        transform = self.transform_type or "none"
        if transform == "none":
            return text
        if transform == "split":
            delimiter = self.split_delimiter or " "
            parts = text.split(delimiter)
            if not parts:
                return ""
            if self.split_part == "first":
                return parts[0]
            if self.split_part == "index":
                idx = (self.split_index or 0) - 1
                if 0 <= idx < len(parts):
                    return parts[idx]
                return ""
            return parts[-1]
        if transform == "first_n":
            n = self.first_n or 0
            return text[:n] if n > 0 else ""
        if transform == "last_n":
            n = self.last_n or 0
            return text[-n:] if n > 0 else ""
        if transform == "replace":
            if not self.replace_from:
                return text
            return text.replace(self.replace_from, self.replace_to or "")
        if transform == "case":
            if self.case_type == "upper":
                return text.upper()
            if self.case_type == "lower":
                return text.lower()
            if self.case_type == "title":
                return text.title()
            return text
        if transform == "prefix":
            return f"{self.prefix_text or ''}{text}"
        if transform == "suffix":
            return f"{text}{self.suffix_text or ''}"
        if transform == "between":
            if not self.between_start or not self.between_end:
                return text
            start_idx = text.find(self.between_start)
            if start_idx == -1:
                return text
            start_idx += len(self.between_start)
            end_idx = text.find(self.between_end, start_idx)
            if end_idx == -1:
                return text
            return text[start_idx:end_idx]
        return text
