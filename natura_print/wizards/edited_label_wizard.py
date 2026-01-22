import base64
import json
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NaturaPrintEditedLabelWizard(models.TransientModel):
    _name = "natura.print.edited.label.wizard"
    _description = "Natura Print Labels with Edits"

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
    qty = fields.Integer(string="Quantity", default=1, required=True)
    source_model = fields.Char(string="Source Model", readonly=True)
    source_res_id = fields.Integer(string="Source Record", readonly=True)
    line_ids = fields.One2many(
        "natura.print.edited.label.line",
        "wizard_id",
        string="Placeholders",
    )
    preview_image = fields.Binary(string="Preview", attachment=False)
    preview_error = fields.Char(string="Preview Error", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        template_id = res.get("template_id") or self.env.context.get("default_template_id")
        if "printer_id" in fields_list and not res.get("printer_id"):
            res["printer_id"] = self.env.context.get("default_printer_id")
        if not res.get("source_model"):
            res["source_model"] = self.env.context.get("default_source_model")
        if not res.get("source_res_id"):
            res["source_res_id"] = self.env.context.get("default_source_res_id")
        if template_id and "line_ids" in fields_list:
            template = self.env["zpl.label.template"].browse(template_id)
            source = self._get_source_record(
                res.get("source_model"),
                res.get("source_res_id"),
                template,
            )
            values = template._values_from_record(source) if source else {}
            res["line_ids"] = [
                (0, 0, {"placeholder": placeholder, "value": values.get(placeholder, "")})
                for placeholder in template._extract_placeholders(template.zpl_code)
            ]
        return res

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if not self.template_id:
            self.line_ids = [(5, 0, 0)]
            self.preview_image = False
            self.preview_error = False
            return
        source = self._get_source_record(
            self.source_model,
            self.source_res_id,
            self.template_id,
        )
        values = self.template_id._values_from_record(source) if source else {}
        placeholders = self.template_id._extract_placeholders(self.template_id.zpl_code)
        self.line_ids = [(5, 0, 0)]
        self.line_ids = [
            (0, 0, {"placeholder": placeholder, "value": values.get(placeholder, "")})
            for placeholder in placeholders
        ]
        self._update_preview_image(silent=True)

    @api.onchange("line_ids")
    def _onchange_line_ids(self):
        pass

    def _get_source_record(self, model_name, res_id, template):
        if not model_name:
            model_name = self.env.context.get("default_source_model")
        if not res_id:
            res_id = self.env.context.get("default_source_res_id")
        if model_name and res_id:
            return self.env[model_name].browse(res_id)
        if template and template.model_id:
            return self.env[template.model_id.model].browse()
        return self.env["zpl.label.template"].browse()

    def _ensure_source_context(self):
        if not self.source_model:
            self.source_model = self.env.context.get("default_source_model")
        if not self.source_res_id:
            self.source_res_id = self.env.context.get("default_source_res_id")

    def _build_values(self):
        values = {}
        self._ensure_source_context()
        source = self._get_source_record(
            self.source_model,
            self.source_res_id,
            self.template_id,
        )
        if source:
            values.update(self.template_id._values_from_record(source))
        for line in self.line_ids:
            placeholder = (line.placeholder or "").strip()
            if not placeholder:
                continue
            if line.new_value not in (False, None, ""):
                values[placeholder] = line.new_value
            else:
                values[placeholder] = line.value or ""
        return values

    def _send_labels(self, zpl):
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
            "zpl": zpl,
            "printer_ip": self.printer_id.ip_address,
            "qty": self.qty or 1,
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

    def action_update_preview(self):
        self.ensure_one()
        self.env.flush_all()
        self._ensure_source_context()
        self._update_preview_image(silent=False)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context),
        }

    def _update_preview_image(self, silent=False):
        self.ensure_one()
        self._ensure_source_context()
        self.preview_error = False
        if not self.template_id:
            self.preview_image = False
            return
        dpmm = self.template_id._labelary_dpmm()
        if not dpmm:
            self.preview_image = False
            self.preview_error = "Unsupported DPI for Labelary preview."
            if not silent:
                raise UserError(self.preview_error)
            return
        if not self.template_id.width or not self.template_id.height:
            self.preview_image = False
            return
        zpl = self.template_id._render_zpl_from_values(self._build_values())
        url = (
            f"https://api.labelary.com/v1/printers/{dpmm}dpmm/"
            f"labels/{self.template_id.width}x{self.template_id.height}/0/"
        )
        try:
            response = requests.post(
                url,
                data=zpl.encode("utf-8"),
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

    def action_print(self):
        self.ensure_one()
        self.env.flush_all()
        self._ensure_source_context()
        zpl = self.template_id._render_zpl_from_values(self._build_values())
        self._send_labels(zpl)
        return {"type": "ir.actions.act_window_close"}


class NaturaPrintEditedLabelLine(models.TransientModel):
    _name = "natura.print.edited.label.line"
    _description = "Natura Print Edited Label Line"

    wizard_id = fields.Many2one(
        "natura.print.edited.label.wizard",
        required=True,
        ondelete="cascade",
    )
    placeholder = fields.Char(readonly=True)
    value = fields.Char(string="Value")
    new_value = fields.Char(string="New Value")
