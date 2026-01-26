import base64
import csv
import io
import html
import json

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


CSV_BATCH_SIZE = 12
CSV_PREVIEW_ROWS = 10


class NaturaPrintCsvLabelWizard(models.TransientModel):
    _name = "natura.print.csv.label.wizard"
    _description = "Natura Print CSV Labels"

    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
    )
    printer_id = fields.Many2one(
        "printers.list",
        string="Printer",
        required=True,
    )
    delimiter = fields.Char(
        string="Delimiter",
        default=",",
        help="Single-character delimiter for parsing the CSV.",
    )
    start_row = fields.Integer(
        string="Start Row",
        default=2,
        help="1-based row number to begin printing (row 1 is headers).",
    )
    csv_file = fields.Binary(string="CSV File", required=True)
    csv_filename = fields.Char(string="CSV Filename")
    csv_headers_display = fields.Char(
        string="CSV Columns",
        readonly=True,
        help="Display-only summary of detected column headers.",
    )
    csv_preview = fields.Html(
        string="CSV Preview",
        sanitize=False,
        readonly=True,
        help="Preview of the CSV header and first rows.",
    )
    mapping_json = fields.Text(string="Mapping JSON")
    source_model = fields.Char(string="Source Model", readonly=True)
    source_res_id = fields.Integer(string="Source Record", readonly=True)
    preview_image = fields.Binary(string="Preview", attachment=False)
    preview_error = fields.Char(string="Preview Error", readonly=True)
    mapping_line_ids = fields.One2many(
        "natura.print.csv.mapping.line",
        "wizard_id",
        string="Mappings",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        template_id = res.get("template_id") or self.env.context.get("default_template_id")
        if "source_model" in fields_list and not res.get("source_model"):
            res["source_model"] = self.env.context.get("default_source_model")
        if "source_res_id" in fields_list and not res.get("source_res_id"):
            res["source_res_id"] = self.env.context.get("default_source_res_id")
        if template_id and "mapping_line_ids" in fields_list:
            template = self.env["zpl.label.template"].browse(template_id)
            placeholders = template._extract_placeholders(template.zpl_code)
            base_values = self._build_base_values(template, res)
            res["mapping_line_ids"] = [
                (
                    0,
                    0,
                    {
                        "placeholder": placeholder,
                        "value_preview": base_values.get(placeholder, ""),
                    },
                )
                for placeholder in placeholders
            ]
            if "preview_image" in fields_list:
                preview = self._render_preview_image(template, base_values)
                if preview:
                    res["preview_image"] = preview
        return res

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if not self.template_id:
            self.mapping_line_ids = [(5, 0, 0)]
            self.preview_image = False
            self.preview_error = False
            return
        placeholders = self.template_id._extract_placeholders(self.template_id.zpl_code)
        base_values = self._build_base_values(self.template_id)
        self.mapping_line_ids = [(5, 0, 0)]
        self.mapping_line_ids = [
            (
                0,
                0,
                {
                    "placeholder": placeholder,
                    "value_preview": base_values.get(placeholder, ""),
                },
            )
            for placeholder in placeholders
        ]
        self._update_preview_image(silent=True)

    def _decode_csv(self):
        self.ensure_one()
        if not self.csv_file:
            raise UserError(_("Please upload a CSV file."))
        encoding = self.env.user.natura_print_csv_encoding or "utf-8"
        try:
            data = base64.b64decode(self.csv_file)
            return data.decode(encoding)
        except Exception as exc:
            raise UserError(_("Failed to decode CSV using %s: %s") % (encoding, exc)) from exc

    def _get_source_record(self):
        self.ensure_one()
        if not self.source_model or not self.source_res_id:
            return self.env[self.template_id.model_id.model].browse()
        return self.env[self.source_model].browse(self.source_res_id)

    def _build_base_values(self, template, defaults=None):
        model_name = None
        res_id = None
        if defaults:
            model_name = defaults.get("source_model")
            res_id = defaults.get("source_res_id")
        if not model_name:
            model_name = self.env.context.get("default_source_model")
        if not res_id:
            res_id = self.env.context.get("default_source_res_id")
        if model_name and res_id:
            source = self.env[model_name].browse(res_id)
        elif template and template.model_id:
            source = self.env[template.model_id.model].browse()
        else:
            source = self.env["zpl.label.template"].browse()
        return template._values_from_record(source) if source else {}

    def _render_preview_image(self, template, values):
        if not template:
            return False
        dpmm = template._labelary_dpmm()
        if not dpmm or not template.width or not template.height:
            return False
        zpl = template._render_zpl_from_values(values or {})
        url = (
            f"https://api.labelary.com/v1/printers/{dpmm}dpmm/"
            f"labels/{template.width}x{template.height}/0/"
        )
        try:
            response = requests.post(
                url,
                data=zpl.encode("utf-8"),
                headers={"Accept": "image/png"},
                timeout=10,
            )
            response.raise_for_status()
            return base64.b64encode(response.content)
        except requests.RequestException:
            return False

    @staticmethod
    def _normalize_header(value):
        value = str(value or "").strip().lower()
        return value.replace(" ", "").replace("_", "").replace("-", "")

    def _parse_headers(self, text):
        reader = csv.reader(io.StringIO(text), delimiter=(self.delimiter or ",")[:1])
        rows = list(reader)
        if not rows:
            return []
        headers = [header.strip() for header in rows[0]]
        if headers:
            headers[0] = headers[0].lstrip("\ufeff")
        return headers

    def _build_csv_preview(self, rows):
        if not rows:
            return ""
        header = rows[0]
        start_index = max((self.start_row or 2) - 1, 1)
        sample_rows = rows[start_index:start_index + CSV_PREVIEW_ROWS]
        header_cells = "".join(
            f"<th>{html.escape(str(cell or '').strip())}</th>" for cell in header
        )
        body_rows = []
        for row in sample_rows:
            cells = "".join(
                f"<td>{html.escape(str(cell or '').strip())}</td>" for cell in row
            )
            body_rows.append(f"<tr>{cells}</tr>")
        return (
            "<table class=\"o_natura_csv_table\">"
            "<thead>"
            f"<tr>{header_cells}</tr>"
            "</thead>"
            "<tbody>"
            + "".join(body_rows)
            + "</tbody>"
            "</table>"
        )

    @api.onchange("csv_file", "delimiter", "start_row")
    def _onchange_csv_file(self):
        if not self.csv_file:
            self.csv_headers_display = False
            self.csv_preview = False
            return
        try:
            text = self._decode_csv()
        except UserError:
            self.csv_headers_display = False
            self.csv_preview = False
            return
        headers = self._parse_headers(text)
        headers_text = ", ".join([header for header in headers if header])
        self.csv_headers_display = headers_text or self.csv_filename
        reader = csv.reader(io.StringIO(text), delimiter=(self.delimiter or ",")[:1])
        rows = list(reader)
        self.csv_preview = self._build_csv_preview(rows)
        normalized = {self._normalize_header(h): h for h in headers}
        for line in self.mapping_line_ids:
            if line.column_selector:
                continue
            key = self._normalize_header(line.placeholder)
            if key in normalized:
                line.column_selector = normalized[key]
        self._sync_mapping_json()

    @api.onchange("mapping_line_ids", "mapping_line_ids.column_selector")
    def _onchange_mapping_line_ids(self):
        self._sync_mapping_json()

    def _sync_mapping_json(self):
        lines = []
        for line in self.mapping_line_ids:
            lines.append(
                {
                    "placeholder": line.placeholder,
                    "column_selector": line.column_selector or "",
                    "column_header": line.column_header or "",
                    "column_ref": line.column_ref or "",
                }
            )
        self.mapping_json = json.dumps(lines)

    def _update_preview_image(self, silent=False):
        self.ensure_one()
        self.preview_error = False
        if not self.template_id:
            self.preview_image = False
            return
        values = self._build_base_values(self.template_id)
        preview = self._render_preview_image(self.template_id, values)
        if not preview:
            self.preview_image = False
            if not silent:
                self.preview_error = "Preview failed to generate."
            return
        self.preview_image = preview

    def _column_ref_to_index(self, ref):
        if not ref:
            return None
        ref = str(ref).strip()
        if not ref:
            return None
        if ref.isdigit():
            idx = int(ref) - 1
            return idx if idx >= 0 else None
        letters = ref.upper()
        if not letters.isalpha():
            return None
        value = 0
        for char in letters:
            value = value * 26 + (ord(char) - ord("A") + 1)
        return value - 1

    def _build_mapping(self, headers, lines=None):
        mapping = {}
        header_map = {self._normalize_header(header): idx for idx, header in enumerate(headers)}
        lines = lines or self.mapping_line_ids
        for line in lines:
            if isinstance(line, dict):
                placeholder = (line.get("placeholder") or "").strip()
                selector = (line.get("column_selector") or "").strip()
                header = (line.get("column_header") or "").strip()
                column_ref = (line.get("column_ref") or "").strip()
            else:
                placeholder = (line.placeholder or "").strip()
                selector = (line.column_selector or "").strip()
                header = (line.column_header or "").strip()
                column_ref = (line.column_ref or "").strip()
            if not placeholder:
                continue
            if selector:
                normalized = self._normalize_header(selector)
                if normalized in header_map:
                    mapping[placeholder] = header_map[normalized]
                    continue
                idx = self._column_ref_to_index(selector)
                if idx is not None:
                    mapping[placeholder] = idx
                    continue
                continue
            if header:
                normalized = self._normalize_header(header)
                if normalized in header_map:
                    mapping[placeholder] = header_map[normalized]
                    continue
            idx = self._column_ref_to_index(column_ref)
            if idx is not None:
                mapping[placeholder] = idx
        return mapping

    def _send_batch(self, batch_zpl):
        params = self.env["ir.config_parameter"].sudo()
        hostname = params.get_param("natura_print.hostname")
        api_user = params.get_param("natura_print.api_user")
        api_password = params.get_param("natura_print.api_password")

        if not hostname or not api_user or not api_password:
            raise UserError(
                _(
                    "Missing configuration. Set Hostname, API User, and API Password "
                    "under Settings > Configuration."
                )
            )

        payload = {
            "zpl": batch_zpl,
            "printer_ip": self.printer_id.ip_address,
            "qty": 1,
        }
        try:
            response = requests.post(
                hostname,
                json=payload,
                auth=(api_user, api_password),
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Print failed: %s") % exc) from exc

    def action_print_csv(self):
        self.ensure_one()
        # Ensure any inline edits in the one2many are persisted before reading.
        self.env.flush_all()
        text = self._decode_csv()
        delimiter = (self.delimiter or ",")[:1]
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            raise UserError(_("CSV file is empty."))

        headers = rows[0]
        # Prefer JSON snapshot from onchange (round-tripped via hidden field).
        mapping = {}
        if self.mapping_json:
            try:
                mapping = self._build_mapping(headers, json.loads(self.mapping_json))
            except Exception:
                mapping = {}
        if not mapping:
            # Prefer values persisted on mapping lines.
            lines_read = self.mapping_line_ids.read(
                ["placeholder", "column_selector", "column_header", "column_ref"]
            )
            mapping = self._build_mapping(headers, lines_read)
        if not mapping:
            # Fallback: direct DB search (if transient got recreated).
            lines_db = self.env["natura.print.csv.mapping.line"].search([("wizard_id", "=", self.id)])
            mapping = self._build_mapping(headers, lines_db) if lines_db else {}
        source_record = self._get_source_record()
        base_values = {}
        if source_record:
            base_values = self.template_id._values_from_record(source_record)
        start_index = max((self.start_row or 2) - 1, 0)
        if start_index >= len(rows):
            raise UserError(_("Start row is beyond the end of the CSV file."))

        batch = []
        for row in rows[start_index:]:
            values = dict(base_values)
            for placeholder, idx in mapping.items():
                if idx < len(row):
                    values[placeholder] = row[idx]
            zpl = self.template_id._render_zpl_from_values(values)
            batch.append(zpl)
            if len(batch) >= CSV_BATCH_SIZE:
                self._send_batch("".join(batch))
                batch = []

        if batch:
            self._send_batch("".join(batch))

        return {"type": "ir.actions.act_window_close"}


class NaturaPrintCsvMappingLine(models.TransientModel):
    _name = "natura.print.csv.mapping.line"
    _description = "Natura Print CSV Mapping Line"

    wizard_id = fields.Many2one(
        "natura.print.csv.label.wizard",
        required=True,
        ondelete="cascade",
    )
    placeholder = fields.Char(required=True)
    value_preview = fields.Char(string="Value", readonly=True)
    column_selector = fields.Char(
        string="New Value (Column Header or Index)",
        help="Enter a column header or index like A, B, 1, 2.",
    )
    column_header = fields.Char(string="Column Header")
    column_ref = fields.Char(
        string="Column Index (A/B/C or 1/2/3)",
        help="Fallback column reference if headers are missing or incorrect.",
    )
