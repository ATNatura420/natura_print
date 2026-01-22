import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    child_mo_ids = fields.Many2many(
        "mrp.production",
        string="Child MOs",
        compute="_compute_child_mo_ids",
        readonly=True,
    )
    child_lot_ids = fields.Many2many(
        "stock.lot",
        string="Child Lots",
        compute="_compute_child_lot_ids",
        readonly=True,
    )

    @api.depends(
        "procurement_group_id",
        "procurement_group_id.stock_move_ids",
        "procurement_group_id.stock_move_ids.created_production_id",
        "procurement_group_id.stock_move_ids.move_orig_ids.created_production_id",
    )
    def _compute_child_mo_ids(self):
        for production in self:
            if hasattr(production, "_get_children"):
                production.child_mo_ids = production._get_children()
            else:
                production.child_mo_ids = self.env["mrp.production"]

    @api.depends(
        "procurement_group_id",
        "procurement_group_id.stock_move_ids",
        "procurement_group_id.stock_move_ids.move_line_ids.lot_id",
        "procurement_group_id.stock_move_ids.created_production_id",
        "procurement_group_id.stock_move_ids.move_orig_ids.created_production_id",
    )
    def _compute_child_lot_ids(self):
        for production in self:
            lots = self.env["stock.lot"]
            child_mos = (
                production._get_children()
                if hasattr(production, "_get_children")
                else self.env["mrp.production"]
            )
            if child_mos:
                lots |= child_mos.move_raw_ids.move_line_ids.lot_id
                lots |= child_mos.move_finished_ids.move_line_ids.lot_id
            production.child_lot_ids = lots

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_mrp_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_mrp_production_ids": ids,
            "active_ids": ids,
            "active_model": "mrp.production",
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
