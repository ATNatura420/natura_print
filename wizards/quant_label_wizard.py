import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NaturaPrintQuantLabelWizard(models.TransientModel):
    _name = "natura.print.quant.label.wizard"
    _description = "Natura Print Inventory Labels"

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
    line_ids = fields.One2many(
        "natura.print.quant.label.line",
        "wizard_id",
        string="Inventory Lines",
    )
    show_csv_button = fields.Boolean(
        compute="_compute_show_csv_button",
        string="Show CSV Button",
    )
    show_automation_button = fields.Boolean(
        compute="_compute_show_csv_button",
        string="Show Label Automation Button",
    )

    @api.depends("line_ids")
    def _compute_show_csv_button(self):
        for wizard in self:
            wizard.show_csv_button = len(wizard.line_ids) == 1
            wizard.show_automation_button = wizard.show_csv_button

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        quant_ids = self.env.context.get("default_quant_ids")
        if quant_ids and "line_ids" in fields_list:
            res["line_ids"] = [
                (0, 0, {"quant_id": quant_id, "qty": 1})
                for quant_id in quant_ids
            ]
        if "printer_id" in fields_list and not res.get("printer_id"):
            res["printer_id"] = self.env.user.natura_print_default_printer_id.id
        if "template_id" in fields_list and not res.get("template_id"):
            template = False
            if quant_ids:
                quants = self.env["stock.quant"].browse(quant_ids).exists()
                template = self._get_product_override_template(quants.mapped("product_id.product_tmpl_id"))
            if not template:
                template = self.env.user._natura_print_get_default_template("stock.quant")
            res["template_id"] = template.id if template else False
        return res

    def _get_product_tmpl_ids(self):
        self.ensure_one()
        return self.line_ids.mapped("quant_id.product_id.product_tmpl_id").ids

    def _get_available_templates(self):
        self.ensure_one()
        domain = self.env["zpl.label.template"]._natura_print_available_domain(
            "stock.quant",
            product_tmpl_ids=self._get_product_tmpl_ids(),
        )
        return self.env["zpl.label.template"].search(domain)

    def _get_product_override_template(self, product_templates):
        product_templates = product_templates.filtered(lambda rec: rec)
        if len(product_templates) != 1:
            return False
        template = product_templates._natura_print_get_default_template_for_model("stock.quant")
        if not template:
            return False
        return template

    @api.depends("line_ids", "line_ids.quant_id", "line_ids.quant_id.product_id")
    def _compute_available_template_ids(self):
        for wizard in self:
            wizard.available_template_ids = wizard._get_available_templates()

    @api.onchange("line_ids", "line_ids.quant_id")
    def _onchange_line_ids_apply_template(self):
        for wizard in self:
            available = wizard._get_available_templates()
            preferred = wizard._get_product_override_template(
                wizard.line_ids.mapped("quant_id.product_id.product_tmpl_id")
            )
            if preferred and preferred in available:
                wizard.template_id = preferred
                continue
            if wizard.template_id and wizard.template_id in available:
                continue
            wizard.template_id = available[:1] if available else False

    def action_send_labels(self):
        self.ensure_one()
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

        for line in self.line_ids:
            if not line.quant_id:
                continue
            zpl = self.template_id._render_zpl(line.quant_id)
            payload = {
                "zpl": zpl,
                "printer_ip": self.printer_id.ip_address,
                "qty": line.qty or 1,
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

        return {"type": "ir.actions.act_window_close"}

    def action_open_csv_wizard(self):
        self.ensure_one()
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to print from CSV."))
        record = self.line_ids[0].quant_id
        action = self.env.ref("natura_print.action_natura_print_csv_label_wizard").read()[0]
        action["context"] = {
            "default_template_id": self.template_id.id,
            "default_printer_id": self.printer_id.id,
            "default_source_model": record._name,
            "default_source_res_id": record.id,
        }
        return action

    def action_open_edit_wizard(self):
        self.ensure_one()
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to print with edits."))
        record = self.line_ids[0].quant_id
        action = self.env.ref("natura_print.action_natura_print_edited_label_wizard").read()[0]
        action["context"] = {
            "default_template_id": self.template_id.id,
            "default_printer_id": self.printer_id.id,
            "default_source_model": record._name,
            "default_source_res_id": record.id,
        }
        return action

    def action_open_multiples_wizard(self):
        self.ensure_one()
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to print multiples."))
        record = self.line_ids[0].quant_id
        action = self.env.ref("natura_print.action_natura_print_multiples_wizard").read()[0]
        action["context"] = {
            "default_template_id": self.template_id.id,
            "default_printer_id": self.printer_id.id,
            "default_source_model": record._name,
            "default_source_res_id": record.id,
            "default_label_count": 1,
        }
        return action

    def action_open_label_automation_wizard(self):
        self.ensure_one()
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to run a label automation."))
        line = self.line_ids[0]
        record = line.quant_id
        action = self.env.ref("natura_print.action_natura_print_label_automation_wizard").read()[0]
        action["context"] = {
            "default_source_model": record._name,
            "default_source_res_id": record.id,
        }
        return action


class NaturaPrintQuantLabelLine(models.TransientModel):
    _name = "natura.print.quant.label.line"
    _description = "Natura Print Inventory Label Line"
    _rec_name = "line_label"

    wizard_id = fields.Many2one(
        "natura.print.quant.label.wizard",
        required=True,
        ondelete="cascade",
    )

    quant_id = fields.Many2one(
        "stock.quant",
        string="Inventory Line",
        required=True,
    )

    line_label = fields.Char(
        compute="_compute_line_label",
        string="Product",
        store=False
    )

    qty = fields.Integer(string="Quantity", default=1, required=True)

    def _compute_line_label(self):
        for line in self:
            product = line.quant_id.product_id.display_name if line.quant_id.product_id else ""
            lot = line.quant_id.lot_id.name if line.quant_id.lot_id else ""
            parts = [p for p in [product, lot] if p]
            line.line_label = " - ".join(parts)
