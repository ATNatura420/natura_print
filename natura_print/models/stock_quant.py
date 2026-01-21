import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Compatibility shim: some environments include views referencing stock.quant.reason_note/reason_id.
    # Keeping these fields here prevents upgrade failures until those views are cleaned up.

    reason_note = fields.Text(string="Reason Note")
    reason_id = fields.Many2one("stock.inventory.reason", string="Reason")
    note_required = fields.Boolean(string="Note Required")

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_quant_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_quant_ids": ids,
            "active_ids": ids,
            "active_model": "stock.quant",
        }
        return action

    def natura_print_print_label(self, qty=1):
        user = self.env.user
        template = user._natura_print_get_default_template(self._name)
        printer = user.natura_print_default_printer_id

        if not template:
            raise UserError(_("Missing default label template for %s.") % self._description)
        if not printer:
            raise UserError(_("Missing default printer in your preferences."))

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

        for record in self:
            zpl = template._render_zpl(record)
            payload = {
                "zpl": zpl,
                "printer_ip": printer.ip_address,
                "qty": qty or 1,
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
