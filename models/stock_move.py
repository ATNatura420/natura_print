from odoo import _, models
from odoo.exceptions import UserError
import math


class StockMove(models.Model):
    _inherit = "stock.move"

    def _natura_print_get_config_partner(self):
        self.ensure_one()
        picking = self.picking_id
        if not picking:
            return self.env["res.partner"]
        partner = picking.partner_id
        if partner and partner.natura_print_label_config_required and partner.natura_print_label_line_ids:
            return partner
        commercial = partner.commercial_partner_id if partner else self.env["res.partner"]
        if commercial and commercial.natura_print_label_config_required and commercial.natura_print_label_line_ids:
            return commercial
        return self.env["res.partner"]

    def _natura_print_should_use_partner_config(self):
        self.ensure_one()
        picking = self.picking_id
        if not picking or picking.picking_type_id.code != "outgoing":
            return False
        return bool(self._natura_print_get_config_partner())

    def action_natura_print_line_labels(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Please select a product line to print labels."))

        if self._natura_print_should_use_partner_config():
            ctx = {
                "default_move_id": self.id,
                "default_use_partner_config": True,
            }
            wizard = self.env["natura.print.transfer.line.label.wizard"].with_context(ctx).create({})
            action = self.env.ref("natura_print.action_natura_print_transfer_line_label_wizard").read()[0]
            action["context"] = ctx
            action["res_id"] = wizard.id
            return action

        default_line_qty = max(1, int(math.ceil(self.product_uom_qty or 0.0)))
        action = self.env.ref("natura_print.action_natura_print_product_label_wizard").read()[0]
        ctx = {
            "default_product_ids": [self.product_id.product_tmpl_id.id],
            "default_line_qty": default_line_qty,
            "active_ids": [self.product_id.product_tmpl_id.id],
            "active_model": "product.template",
        }
        if self.picking_id and self.picking_id.picking_type_id.code == "outgoing":
            ctx.update(
                {
                    "default_enable_model_selector": True,
                    "default_transfer_move_id": self.id,
                }
            )
        action["context"] = ctx
        return action
