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
        domain="[('model_id.model', '=', 'stock.quant')]",
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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        quant_ids = self.env.context.get("default_quant_ids")
        if quant_ids and "line_ids" in fields_list:
            res["line_ids"] = [
                (0, 0, {"quant_id": quant_id, "qty": 1})
                for quant_id in quant_ids
            ]
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


class NaturaPrintQuantLabelLine(models.TransientModel):
    _name = "natura.print.quant.label.line"
    _description = "Natura Print Inventory Label Line"

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
    qty = fields.Integer(string="Quantity", default=1, required=True)
