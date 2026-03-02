from odoo import _, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _natura_print_get_kit_bom(self):
        self.ensure_one()
        if not self.product_id:
            return self.env["mrp.bom"]
        domain = [
            ("type", "=", "phantom"),
            ("company_id", "in", [False, self.order_id.company_id.id]),
            "|",
            ("product_id", "=", self.product_id.id),
            "&",
            ("product_id", "=", False),
            ("product_tmpl_id", "=", self.product_template_id.id),
        ]
        return self.env["mrp.bom"].search(domain, limit=1, order="product_id desc, id desc")

    def action_natura_print_line_labels(self):
        self.ensure_one()
        if self.display_type or not self.product_id:
            raise UserError(_("Please select a product line to print labels."))

        bom = self._natura_print_get_kit_bom()
        if bom and bom.natura_print_label_line_ids:
            ctx = {
                "default_sale_line_id": self.id,
            }
            wizard = self.env["natura.print.sale.line.kit.label.wizard"].with_context(ctx).create({})
            action = self.env.ref("natura_print.action_natura_print_sale_line_kit_label_wizard").read()[0]
            action["context"] = ctx
            action["res_id"] = wizard.id
            return action

        action = self.env.ref("natura_print.action_natura_print_product_label_wizard").read()[0]
        action["context"] = {
            "default_product_ids": [self.product_template_id.id],
            "default_line_qty": int(self.product_uom_qty or 1),
            "active_ids": [self.product_template_id.id],
            "active_model": "product.template",
        }
        return action
