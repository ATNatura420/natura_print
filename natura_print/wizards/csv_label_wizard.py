import base64
import csv
import io

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


CSV_BATCH_SIZE = 12


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
    source_model = fields.Char(string="Source Model", readonly=True)
    source_res_id = fields.Integer(string="Source Record", readonly=True)
    headers_preview = fields.Text(
        string="Detected Headers",
        readonly=True,
        help="Parsed from the first row of the CSV file.",
    )
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
            res["mapping_line_ids"] = [
                (0, 0, {"placeholder": placeholder}) for placeholder in placeholders
            ]
        return res

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if not self.template_id:
            self.mapping_line_ids = [(5, 0, 0)]
            return
        placeholders = self.template_id._extract_placeholders(self.template_id.zpl_code)
        self.mapping_line_ids = [(5, 0, 0)]
        self.mapping_line_ids = [
            (0, 0, {"placeholder": placeholder}) for placeholder in placeholders
        ]

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

    @api.onchange("csv_file", "delimiter")
    def _onchange_csv_file(self):
        if not self.csv_file:
            self.headers_preview = False
            return
        try:
            text = self._decode_csv()
        except UserError:
            self.headers_preview = False
            return
        headers = self._parse_headers(text)
        self.headers_preview = ", ".join(headers)
        normalized = {self._normalize_header(h): h for h in headers}
        for line in self.mapping_line_ids:
            if line.column_header:
                continue
            key = self._normalize_header(line.placeholder)
            if key in normalized:
                line.column_header = normalized[key]

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

    def _build_mapping(self, headers):
        mapping = {}
        header_map = {self._normalize_header(header): idx for idx, header in enumerate(headers)}
        for line in self.mapping_line_ids:
            placeholder = (line.placeholder or "").strip()
            if not placeholder:
                continue
            header = (line.column_header or "").strip()
            if header:
                normalized = self._normalize_header(header)
                if normalized in header_map:
                    mapping[placeholder] = header_map[normalized]
                    continue
                continue
            idx = self._column_ref_to_index(line.column_ref)
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
        text = self._decode_csv()
        delimiter = (self.delimiter or ",")[:1]
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            raise UserError(_("CSV file is empty."))

        headers = rows[0]
        mapping = self._build_mapping(headers)
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
    column_header = fields.Char(string="Column Header")
    column_ref = fields.Char(
        string="Column Index (A/B/C or 1/2/3)",
        help="Fallback column reference if headers are missing or incorrect.",
    )
