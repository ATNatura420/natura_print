import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


MAX_DYNAMIC_PLACEHOLDERS = 4
SPECIAL_MULTI_PLACEHOLDERS = {
    "multi_print_qty_1",
    "multi_print_qty_x",
    "multi_print_target_qty",
    "multi_print_qty_index",
    "multi_print_qty_total",
    "multi_print_qty",
}


class NaturaPrintMultiplesWizard(models.TransientModel):
    _name = "natura.print.multiples.wizard"
    _description = "Natura Print Multiples"

    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
    )
    available_template_ids = fields.Many2many(
        "zpl.label.template",
        compute="_compute_available_template_ids",
        string="Available Templates",
    )
    printer_id = fields.Many2one(
        "printers.list",
        string="Printer",
        required=True,
    )
    label_count = fields.Integer(
        string="Number of Labels",
        default=1,
        required=True,
    )
    source_model = fields.Char(string="Source Model", readonly=True)
    source_res_id = fields.Integer(string="Source Record", readonly=True)
    placeholder_1 = fields.Char(string="Placeholder 1", readonly=True)
    placeholder_2 = fields.Char(string="Placeholder 2", readonly=True)
    placeholder_3 = fields.Char(string="Placeholder 3", readonly=True)
    placeholder_4 = fields.Char(string="Placeholder 4", readonly=True)
    placeholder_help = fields.Char(string="Input Mapping", readonly=True)
    entry_summary = fields.Char(
        string="Entry Summary",
        compute="_compute_entry_summary",
        readonly=True,
    )
    line_ids = fields.One2many(
        "natura.print.multiples.line",
        "wizard_id",
        string="Per Label Inputs",
    )

    @staticmethod
    def _inject_multi_print_placeholders(values, index, total):
        values["multi_print_qty_1"] = str(index)
        values["multi_print_qty_x"] = str(total)
        values["multi_print_target_qty"] = str(total)
        values["multi_print_qty_index"] = str(index)
        values["multi_print_qty_total"] = str(total)
        values["multi_print_qty"] = f"{index} of {total}"
        return values

    @api.depends("label_count", "line_ids.value_1", "line_ids.value_2", "line_ids.value_3", "line_ids.value_4")
    def _compute_entry_summary(self):
        for wizard in self:
            lines = wizard.line_ids.sorted("sequence")
            label_count = len(lines) if lines else int(wizard.label_count or 0)
            total = 0.0
            for line in lines:
                for val in (line.value_1, line.value_2, line.value_3, line.value_4):
                    if val in (False, None, ""):
                        continue
                    try:
                        total += float(str(val).strip())
                    except Exception:
                        continue
            wizard.entry_summary = (
                f"Your entries - {label_count} labels, sum of weights: {total:.1f} Grams"
            )

    @api.depends("source_model", "source_res_id")
    def _compute_available_template_ids(self):
        for wizard in self:
            model_name = wizard.source_model or self.env.context.get("default_source_model")
            if not model_name:
                wizard.available_template_ids = self.env["zpl.label.template"]
                continue
            product_tmpl_ids = wizard._get_source_product_tmpl_ids()
            domain = self.env["zpl.label.template"]._natura_print_available_domain(
                model_name,
                product_tmpl_ids=product_tmpl_ids,
            )
            wizard.available_template_ids = self.env["zpl.label.template"].search(domain)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "printer_id" in fields_list and not res.get("printer_id"):
            res["printer_id"] = self.env.context.get("default_printer_id")
        if "template_id" in fields_list and not res.get("template_id"):
            res["template_id"] = self.env.context.get("default_template_id")
        if "source_model" in fields_list and not res.get("source_model"):
            res["source_model"] = self.env.context.get("default_source_model")
        if "source_res_id" in fields_list and not res.get("source_res_id"):
            res["source_res_id"] = self.env.context.get("default_source_res_id")
        if not res.get("label_count"):
            res["label_count"] = int(self.env.context.get("default_label_count") or 1)

        template_id = res.get("template_id")
        if template_id:
            template = self.env["zpl.label.template"].browse(template_id)
            model_name = res.get("source_model") or self.env.context.get("default_source_model")
            res_id = res.get("source_res_id") or self.env.context.get("default_source_res_id")
            source = self.env[model_name].browse(res_id) if model_name and res_id else self.env["zpl.label.template"].browse()
            base_values = template._values_from_record(source) if source else {}
            placeholders = template._extract_placeholders(template.zpl_code)
            unmapped = [
                p for p in placeholders
                if p not in SPECIAL_MULTI_PLACEHOLDERS and base_values.get(p) in (False, None, "")
            ]
            unmapped = unmapped[:MAX_DYNAMIC_PLACEHOLDERS]
            res["placeholder_1"] = unmapped[0] if len(unmapped) > 0 else False
            res["placeholder_2"] = unmapped[1] if len(unmapped) > 1 else False
            res["placeholder_3"] = unmapped[2] if len(unmapped) > 2 else False
            res["placeholder_4"] = unmapped[3] if len(unmapped) > 3 else False
            labels = []
            if res["placeholder_1"]:
                labels.append(f"Value 1: {res['placeholder_1']}")
            if res["placeholder_2"]:
                labels.append(f"Value 2: {res['placeholder_2']}")
            if res["placeholder_3"]:
                labels.append(f"Value 3: {res['placeholder_3']}")
            if res["placeholder_4"]:
                labels.append(f"Value 4: {res['placeholder_4']}")
            res["placeholder_help"] = " | ".join(labels) if labels else "All placeholders are already mapped."

        if "line_ids" in fields_list:
            count = max(1, int(res.get("label_count") or 1))
            res["line_ids"] = [(0, 0, {"sequence": seq}) for seq in range(1, count + 1)]
        return res

    def _get_source_product_tmpl_ids(self):
        self.ensure_one()
        model_name = self.source_model or self.env.context.get("default_source_model")
        res_id = self.source_res_id or self.env.context.get("default_source_res_id")
        if not model_name or not res_id:
            return []
        record = self.env[model_name].browse(res_id)
        if model_name == "product.template":
            return [record.id]
        if model_name in ("stock.lot", "stock.quant", "mrp.production"):
            product = record.product_id
            return [product.product_tmpl_id.id] if product and product.product_tmpl_id else []
        return []

    def _get_source_record(self):
        self.ensure_one()
        model_name = self.source_model or self.env.context.get("default_source_model")
        res_id = self.source_res_id or self.env.context.get("default_source_res_id")
        if not model_name or not res_id:
            return self.env["zpl.label.template"].browse()
        return self.env[model_name].browse(res_id)

    def _get_unmapped_placeholders(self):
        self.ensure_one()
        if not self.template_id:
            return []
        source = self._get_source_record()
        base_values = self.template_id._values_from_record(source) if source else {}
        placeholders = self.template_id._extract_placeholders(self.template_id.zpl_code)
        unmapped = [
            p for p in placeholders
            if p not in SPECIAL_MULTI_PLACEHOLDERS and base_values.get(p) in (False, None, "")
        ]
        return unmapped[:MAX_DYNAMIC_PLACEHOLDERS]

    def _sync_placeholder_fields(self):
        for wizard in self:
            placeholders = wizard._get_unmapped_placeholders()
            wizard.placeholder_1 = placeholders[0] if len(placeholders) > 0 else False
            wizard.placeholder_2 = placeholders[1] if len(placeholders) > 1 else False
            wizard.placeholder_3 = placeholders[2] if len(placeholders) > 2 else False
            wizard.placeholder_4 = placeholders[3] if len(placeholders) > 3 else False
            labels = []
            if wizard.placeholder_1:
                labels.append(f"Value 1: {wizard.placeholder_1}")
            if wizard.placeholder_2:
                labels.append(f"Value 2: {wizard.placeholder_2}")
            if wizard.placeholder_3:
                labels.append(f"Value 3: {wizard.placeholder_3}")
            if wizard.placeholder_4:
                labels.append(f"Value 4: {wizard.placeholder_4}")
            wizard.placeholder_help = " | ".join(labels) if labels else "All placeholders are already mapped."

    def _sync_lines(self):
        for wizard in self:
            count = max(1, int(wizard.label_count or 1))
            existing = {line.sequence: line for line in wizard.line_ids}
            commands = [(5, 0, 0)]
            for seq in range(1, count + 1):
                if seq in existing:
                    line = existing[seq]
                    commands.append(
                        (
                            0,
                            0,
                            {
                                "sequence": seq,
                                "value_1": line.value_1,
                                "value_2": line.value_2,
                                "value_3": line.value_3,
                                "value_4": line.value_4,
                            },
                        )
                    )
                else:
                    commands.append((0, 0, {"sequence": seq}))
            wizard.line_ids = commands

    @api.onchange("label_count", "template_id", "source_model", "source_res_id")
    def _onchange_refresh_dynamic_inputs(self):
        for wizard in self:
            wizard._sync_placeholder_fields()
            wizard._sync_lines()

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

    def action_print_multiples(self):
        self.ensure_one()
        self.env.flush_all()
        source = self._get_source_record()
        base_values = self.template_id._values_from_record(source) if source else {}

        placeholder_order = [
            self.placeholder_1,
            self.placeholder_2,
            self.placeholder_3,
            self.placeholder_4,
        ]
        placeholder_order = [placeholder for placeholder in placeholder_order if placeholder]
        override_set = set(placeholder_order)

        zpl_chunks = []
        lines = self.line_ids.sorted("sequence")
        total = len(lines)
        for line in lines:
            values = dict(base_values)
            self._inject_multi_print_placeholders(values, line.sequence, total)
            if len(placeholder_order) > 0:
                values[placeholder_order[0]] = line.value_1 or ""
            if len(placeholder_order) > 1:
                values[placeholder_order[1]] = line.value_2 or ""
            if len(placeholder_order) > 2:
                values[placeholder_order[2]] = line.value_3 or ""
            if len(placeholder_order) > 3:
                values[placeholder_order[3]] = line.value_4 or ""
            zpl_chunks.append(
                self.template_id._render_zpl_from_values(
                    values,
                    skip_transform_placeholders=override_set,
                )
            )

        if not zpl_chunks:
            raise UserError(_("Nothing to print."))

        self._send_labels("".join(zpl_chunks))
        return {"type": "ir.actions.act_window_close"}


class NaturaPrintMultiplesLine(models.TransientModel):
    _name = "natura.print.multiples.line"
    _description = "Natura Print Multiples Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "natura.print.multiples.wizard",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="#", default=1, required=True)
    value_1 = fields.Char(string="Value 1")
    value_2 = fields.Char(string="Value 2")
    value_3 = fields.Char(string="Value 3")
    value_4 = fields.Char(string="Value 4")
