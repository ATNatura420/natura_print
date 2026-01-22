import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockLot(models.Model):
    _inherit = "stock.lot"

    # Compatibility shim for environments that reference studio fields in views.
    x_studio_batch_result = fields.Char(string="Batch Result")

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_lot_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_lot_ids": ids,
            "active_ids": ids,
            "active_model": "stock.lot",
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
