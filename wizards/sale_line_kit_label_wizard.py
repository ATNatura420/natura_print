import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NaturaPrintSaleLineKitLabelWizard(models.TransientModel):
    _name = "natura.print.sale.line.kit.label.wizard"
    _description = "Natura Print Sale Line Kit Labels"

    sale_line_id = fields.Many2one("sale.order.line", required=True, readonly=True)
    printer_id = fields.Many2one("printers.list", string="Printer", required=True)
    line_ids = fields.One2many(
        "natura.print.sale.line.kit.label.line",
        "wizard_id",
        string="Label Templates",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sale_line_id = res.get("sale_line_id") or self.env.context.get("default_sale_line_id")
        if "printer_id" in fields_list and not res.get("printer_id"):
            res["printer_id"] = self.env.user.natura_print_default_printer_id.id
        if sale_line_id and "line_ids" in fields_list:
            line = self.env["sale.order.line"].browse(sale_line_id)
            bom = line._natura_print_get_kit_bom()
            res["line_ids"] = []
            for cfg in bom.natura_print_label_line_ids:
                qty = cfg.get_effective_qty(line.product_uom_qty)
                res["line_ids"].append(
                    (
                        0,
                        0,
                        {
                            "template_id": cfg.template_id.id,
                            "qty": qty,
                            "source_model": cfg.template_id.model_id.model,
                        },
                    )
                )
        return res

    def _resolve_record_for_template(self, template):
        self.ensure_one()
        line = self.sale_line_id
        model_name = template.model_id.model
        if model_name == "sale.order.line":
            return line
        if model_name == "product.template":
            return line.product_template_id
        if model_name == "stock.quant":
            raise UserError(_("Template '%s' requires stock.quant context, which is not available from a sales line.") % template.display_name)
        if model_name == "stock.lot":
            raise UserError(_("Template '%s' requires stock.lot context, which is not available from a sales line.") % template.display_name)
        if model_name == "mrp.production":
            raise UserError(_("Template '%s' requires mrp.production context, which is not available from a sales line.") % template.display_name)
        raise UserError(_("Unsupported template model '%s' for sales line printing.") % model_name)

    def _get_print_api_config(self):
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
        return hostname, api_user, api_password

    def _print_single_line(self, line, qty=None):
        self.ensure_one()
        hostname, api_user, api_password = self._get_print_api_config()
        source = self._resolve_record_for_template(line.template_id)
        zpl = line.template_id._render_zpl(source)
        payload = {
            "zpl": zpl,
            "printer_ip": self.printer_id.ip_address,
            "qty": qty or line.qty or 1,
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

    def _reload_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "target": "new",
            "res_id": self.id,
        }

    def action_send_labels(self):
        self.ensure_one()
        for line in self.line_ids:
            if not line.template_id:
                continue
            self._print_single_line(line)

        return {"type": "ir.actions.act_window_close"}


class NaturaPrintSaleLineKitLabelLine(models.TransientModel):
    _name = "natura.print.sale.line.kit.label.line"
    _description = "Natura Print Sale Line Kit Label Line"

    wizard_id = fields.Many2one(
        "natura.print.sale.line.kit.label.wizard",
        required=True,
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
        ondelete="restrict",
    )
    source_model = fields.Char(string="Source Model", readonly=True)
    qty = fields.Integer(string="Quantity", required=True, default=1)

    def action_test_print(self):
        self.ensure_one()
        self.wizard_id._print_single_line(self, qty=1)
        return self.wizard_id._reload_action()

    def action_print_all(self):
        self.ensure_one()
        self.wizard_id._print_single_line(self)
        return self.wizard_id._reload_action()
