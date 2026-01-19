import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NaturaPrintProductLabelWizard(models.TransientModel):
    _name = "natura.print.product.label.wizard"
    _description = "Natura Print Product Labels"

    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
        domain="[('model_id.model', '=', 'product.template')]",
    )
    printer_id = fields.Many2one(
        "printers.list",
        string="Printer",
        required=True,
    )
    line_ids = fields.One2many(
        "natura.print.product.label.line",
        "wizard_id",
        string="Products",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        product_ids = self.env.context.get("default_product_ids")
        if product_ids and isinstance(product_ids, list) and product_ids and isinstance(product_ids[0], (list, tuple)):
            if product_ids[0][0] == 6:
                product_ids = product_ids[0][2]
        if product_ids and "line_ids" in fields_list:
            res["line_ids"] = [
                (0, 0, {"product_id": product_id, "qty": 1})
                for product_id in product_ids
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
            if not line.product_id:
                continue
            zpl = self.template_id._render_zpl(line.product_id)
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


class NaturaPrintProductLabelLine(models.TransientModel):
    _name = "natura.print.product.label.line"
    _description = "Natura Print Product Label Line"

    wizard_id = fields.Many2one(
        "natura.print.product.label.wizard",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.template",
        string="Product",
        required=True,
    )
    qty = fields.Integer(string="Quantity", default=1, required=True)
