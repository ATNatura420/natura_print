import math

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NaturaPrintTransferLineLabelWizard(models.TransientModel):
    _name = "natura.print.transfer.line.label.wizard"
    _description = "Natura Print Transfer Line Labels"

    move_id = fields.Many2one("stock.move", required=True, readonly=True)
    printer_id = fields.Many2one("printers.list", string="Printer", required=True)
    use_partner_config = fields.Boolean(string="Use Partner Config", readonly=True)
    line_ids = fields.One2many(
        "natura.print.transfer.line.label.line",
        "wizard_id",
        string="Label Templates",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move_id = res.get("move_id") or self.env.context.get("default_move_id")
        res["use_partner_config"] = bool(
            res.get("use_partner_config") if "use_partner_config" in res else self.env.context.get("default_use_partner_config")
        )

        if "printer_id" in fields_list and not res.get("printer_id"):
            res["printer_id"] = self.env.user.natura_print_default_printer_id.id

        if move_id and "line_ids" in fields_list:
            move = self.env["stock.move"].browse(move_id)
            use_partner = bool(res.get("use_partner_config")) and move._natura_print_should_use_partner_config()
            res["line_ids"] = self._default_line_values_for_move(move, use_partner)

        return res

    @api.model
    def _move_base_qty(self, move):
        return max(1, int(math.ceil(move.product_uom_qty or 0.0)))

    @api.model
    def _default_product_template_template(self, move):
        product_tmpl = move.product_id.product_tmpl_id
        template = product_tmpl._natura_print_get_default_template_for_model("product.template")
        if template:
            return template
        domain = self.env["zpl.label.template"]._natura_print_available_domain(
            "product.template",
            product_tmpl_ids=[product_tmpl.id],
        )
        return self.env["zpl.label.template"].search(domain, limit=1)

    @api.model
    def _default_line_values_for_move(self, move, use_partner):
        base_qty = self._move_base_qty(move)
        lines = []
        if use_partner:
            partner = move._natura_print_get_config_partner()
            for cfg in partner.natura_print_label_line_ids:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "template_id": cfg.template_id.id,
                            "qty": cfg.get_effective_qty(base_qty),
                            "source_model": cfg.model_id.model,
                        },
                    )
                )
            if lines:
                return lines

        template = self._default_product_template_template(move)
        if not template:
            raise UserError(
                _(
                    "No product template label is available for '%s'. "
                    "Configure at least one product template label template."
                )
                % move.product_id.display_name
            )
        return [
            (
                0,
                0,
                {
                    "template_id": template.id,
                    "qty": base_qty,
                    "source_model": "product.template",
                },
            )
        ]

    def _resolve_records_for_template(self, template):
        self.ensure_one()
        model_name = template.model_id.model
        if model_name == "product.template":
            return [self.move_id.product_id.product_tmpl_id]
        if model_name == "stock.lot":
            lots = self.move_id.move_line_ids.mapped("lot_id").exists()
            if not lots:
                raise UserError(
                    _(
                        "Template '%s' requires lot/serial records, but this transfer line has no lots."
                    )
                    % template.display_name
                )
            return lots
        if model_name == "stock.quant":
            move = self.move_id
            quant_model = self.env["stock.quant"]
            quants = quant_model.browse()
            for ml in move.move_line_ids:
                domain = [
                    ("product_id", "=", move.product_id.id),
                    ("location_id", "=", ml.location_id.id),
                ]
                if ml.lot_id:
                    domain.append(("lot_id", "=", ml.lot_id.id))
                quant = quant_model.search(domain, limit=1)
                if quant:
                    quants |= quant
            if not quants:
                fallback_domain = [
                    ("product_id", "=", move.product_id.id),
                    ("location_id", "=", move.location_id.id),
                ]
                quants = quant_model.search(fallback_domain, limit=1)
            if not quants:
                raise UserError(
                    _(
                        "Template '%s' requires inventory lines, but no matching stock.quant was found."
                    )
                    % template.display_name
                )
            return quants
        raise UserError(
            _("Unsupported template model '%s' for transfer line printing.") % model_name
        )

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
        sources = self._resolve_records_for_template(line.template_id)
        for source in sources:
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


class NaturaPrintTransferLineLabelLine(models.TransientModel):
    _name = "natura.print.transfer.line.label.line"
    _description = "Natura Print Transfer Line Label Line"

    wizard_id = fields.Many2one(
        "natura.print.transfer.line.label.wizard",
        required=True,
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        "zpl.label.template",
        string="Label Template",
        required=True,
        domain="[('model_id.model', 'in', ('product.template', 'stock.quant', 'stock.lot')), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        ondelete="restrict",
    )
    source_model = fields.Char(string="Source Model", readonly=True)
    qty = fields.Integer(string="Quantity", required=True, default=1)

    @api.onchange("template_id")
    def _onchange_template_id(self):
        for rec in self:
            rec.source_model = rec.template_id.model_id.model if rec.template_id else False

    def action_test_print(self):
        self.ensure_one()
        self.wizard_id._print_single_line(self, qty=1)
        return self.wizard_id._reload_action()

    def action_print_all(self):
        self.ensure_one()
        self.wizard_id._print_single_line(self)
        return self.wizard_id._reload_action()
