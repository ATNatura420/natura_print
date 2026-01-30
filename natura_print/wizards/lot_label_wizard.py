import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NaturaPrintLotLabelWizard(models.TransientModel):
    _name = "natura.print.lot.label.wizard"
    _description = "Natura Print Lot Labels"

    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
        domain="[('model_id.model', '=', 'stock.lot')]",
    )
    printer_id = fields.Many2one(
        "printers.list",
        string="Printer",
        required=True,
    )
    line_ids = fields.One2many(
        "natura.print.lot.label.line",
        "wizard_id",
        string="Lots/Serials",
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
        lot_ids = self.env.context.get("default_lot_ids")
        if lot_ids and "line_ids" in fields_list:
            res["line_ids"] = [
                (0, 0, {"lot_id": lot_id, "qty": 1})
                for lot_id in lot_ids
            ]
        if "printer_id" in fields_list and not res.get("printer_id"):
            res["printer_id"] = self.env.user.natura_print_default_printer_id.id
        if "template_id" in fields_list and not res.get("template_id"):
            template = self.env.user._natura_print_get_default_template("stock.lot")
            res["template_id"] = template.id if template else False
        return res

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
            if not line.lot_id:
                continue
            zpl = self.template_id._render_zpl(line.lot_id)
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
        record = self.line_ids[0].lot_id
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
        record = self.line_ids[0].lot_id
        action = self.env.ref("natura_print.action_natura_print_edited_label_wizard").read()[0]
        action["context"] = {
            "default_template_id": self.template_id.id,
            "default_printer_id": self.printer_id.id,
            "default_source_model": record._name,
            "default_source_res_id": record.id,
        }
        return action

    def action_open_label_automation_wizard(self):
        self.ensure_one()
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to run a label automation."))
        line = self.line_ids[0]
        record = line.lot_id
        action = self.env.ref("natura_print.action_natura_print_label_automation_wizard").read()[0]
        action["context"] = {
            "default_source_model": record._name,
            "default_source_res_id": record.id,
        }
        return action


class NaturaPrintLotLabelLine(models.TransientModel):
    _name = "natura.print.lot.label.line"
    _description = "Natura Print Lot Label Line"
    _rec_name = "line_label"

    wizard_id = fields.Many2one(
        "natura.print.lot.label.wizard",
        required=True,
        ondelete="cascade",
    )

    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial",
        required=True,
        invisible=True
    )

    line_label = fields.Char(
        compute="_compute_line_label",
        string="Lot/Serial — Product",
        store=False
    )

    qty = fields.Integer(string="Quantity", default=1, required=True)

    def _compute_line_label(self):
        for line in self:
            lot = line.lot_id.name or ""
            product = line.lot_id.product_id.display_name if line.lot_id.product_id else ""
            parts = [p for p in [lot, product] if p]
            line.line_label = " — ".join(parts)
