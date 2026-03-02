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
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Default Model",
        domain="[('model', 'in', ('product.template', 'stock.lot', 'stock.quant'))]",
    )
    enable_model_selector = fields.Boolean(
        string="Enable Model Selector",
        readonly=True,
    )
    transfer_move_id = fields.Many2one(
        "stock.move",
        string="Transfer Line",
        readonly=True,
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
        "natura.print.product.label.line",
        "wizard_id",
        string="Products",
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
        if "enable_model_selector" in fields_list:
            res["enable_model_selector"] = bool(self.env.context.get("default_enable_model_selector"))
        if "transfer_move_id" in fields_list and self.env.context.get("default_transfer_move_id"):
            res["transfer_move_id"] = self.env.context.get("default_transfer_move_id")
        if "model_id" in fields_list and not res.get("model_id"):
            res["model_id"] = self.env.ref("product.model_product_template").id
        product_ids = self.env.context.get("default_product_ids")
        if product_ids and isinstance(product_ids, list) and product_ids and isinstance(product_ids[0], (list, tuple)):
            if product_ids[0][0] == 6:
                product_ids = product_ids[0][2]
        if product_ids and "line_ids" in fields_list:
            default_line_qty = int(self.env.context.get("default_line_qty") or 1)
            res["line_ids"] = [
                (0, 0, {"product_id": product_id, "qty": default_line_qty})
                for product_id in product_ids
            ]
        if "printer_id" in fields_list and not res.get("printer_id"):
            res["printer_id"] = self.env.user.natura_print_default_printer_id.id
        if "template_id" in fields_list and not res.get("template_id"):
            template = False
            model_name = self.env["ir.model"].browse(res.get("model_id")).model if res.get("model_id") else "product.template"
            if product_ids and model_name == "product.template":
                products = self.env["product.template"].browse(product_ids).exists()
                template = self._get_product_override_template(products)
            if not template:
                template = self.env.user._natura_print_get_default_template(model_name)
            if not template:
                domain = self.env["zpl.label.template"]._natura_print_available_domain(
                    model_name,
                    product_tmpl_ids=product_ids if model_name == "product.template" else None,
                )
                template = self.env["zpl.label.template"].search(domain, limit=1)
            res["template_id"] = template.id if template else False
        return res

    def _get_product_tmpl_ids(self):
        self.ensure_one()
        return self.line_ids.mapped("product_id").ids

    def _get_available_templates(self):
        self.ensure_one()
        model_name = "product.template"
        product_tmpl_ids = self._get_product_tmpl_ids()
        if self.enable_model_selector and self.model_id:
            model_name = self.model_id.model
            if model_name != "product.template":
                product_tmpl_ids = None
        domain = self.env["zpl.label.template"]._natura_print_available_domain(
            model_name,
            product_tmpl_ids=product_tmpl_ids,
        )
        return self.env["zpl.label.template"].search(domain)

    def _get_product_override_template(self, products):
        products = products.filtered(lambda rec: rec)
        if len(products) != 1:
            return False
        template = products._natura_print_get_default_template_for_model("product.template")
        if not template:
            return False
        return template

    @api.depends("line_ids", "model_id")
    def _compute_available_template_ids(self):
        for wizard in self:
            wizard.available_template_ids = wizard._get_available_templates()

    @api.onchange("line_ids", "model_id")
    def _onchange_line_ids_apply_template(self):
        for wizard in self:
            available = wizard._get_available_templates()
            preferred = False
            if not wizard.enable_model_selector or (wizard.model_id and wizard.model_id.model == "product.template"):
                preferred = wizard._get_product_override_template(wizard.line_ids.mapped("product_id"))
            if preferred and preferred in available:
                wizard.template_id = preferred
                continue
            if wizard.template_id and wizard.template_id in available:
                continue
            wizard.template_id = available[:1] if available else False

    def _resolve_sources_for_print(self, line):
        self.ensure_one()
        model_name = self.template_id.model_id.model
        if model_name == "product.template":
            return [line.product_id]
        if model_name == "stock.lot":
            if not self.transfer_move_id:
                raise UserError(_("Lot/Serial templates require a transfer line context."))
            lots = self.transfer_move_id.move_line_ids.mapped("lot_id").exists()
            if line.product_id:
                lots = lots.filtered(lambda lot: lot.product_id.product_tmpl_id == line.product_id)
            if not lots:
                raise UserError(_("No lots/serials were found for this transfer line."))
            return lots
        if model_name == "stock.quant":
            if not self.transfer_move_id:
                raise UserError(_("Quant templates require a transfer line context."))
            move = self.transfer_move_id
            quants = self.env["stock.quant"].browse()
            for ml in move.move_line_ids:
                domain = [
                    ("product_id", "=", move.product_id.id),
                    ("location_id", "=", ml.location_id.id),
                ]
                if ml.lot_id:
                    domain.append(("lot_id", "=", ml.lot_id.id))
                quant = self.env["stock.quant"].search(domain, limit=1)
                if quant:
                    quants |= quant
            if not quants:
                quants = self.env["stock.quant"].search(
                    [
                        ("product_id", "=", move.product_id.id),
                        ("location_id", "=", move.location_id.id),
                    ],
                    limit=1,
                )
            if not quants:
                raise UserError(_("No inventory lines (quants) were found for this transfer line."))
            return quants
        raise UserError(_("Unsupported template model '%s'.") % model_name)

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
            for source in self._resolve_sources_for_print(line):
                zpl = self.template_id._render_zpl(source)
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
        if self.template_id.model_id.model != "product.template":
            raise UserError(_("Print from CSV is only available for Product Template model in this wizard."))
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to print from CSV."))
        record = self.line_ids[0].product_id
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
        if self.template_id.model_id.model != "product.template":
            raise UserError(_("Print with Edits is only available for Product Template model in this wizard."))
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to print with edits."))
        record = self.line_ids[0].product_id
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
        if self.template_id.model_id.model != "product.template":
            raise UserError(_("Label Automations are only available for Product Template model in this wizard."))
        if len(self.line_ids) != 1:
            raise UserError(_("Select exactly one line to run a label automation."))
        line = self.line_ids[0]
        record = line.product_id
        action = self.env.ref("natura_print.action_natura_print_label_automation_wizard").read()[0]
        action["context"] = {
            "default_source_model": record._name,
            "default_source_res_id": record.id,
        }
        return action


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
