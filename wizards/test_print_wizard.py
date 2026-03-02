import requests

from odoo import fields, models, _
from odoo.exceptions import UserError


class NaturaPrintTestWizard(models.TransientModel):
    _name = "natura.print.test.wizard"
    _description = "Natura Print Test"

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

    def action_send_test(self):
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

        payload = {
            "zpl": self.template_id.zpl_code or "",
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
            raise UserError(_("Test print failed: %s") % exc) from exc

        return {"type": "ir.actions.act_window_close"}
