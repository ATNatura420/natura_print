from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_product_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_product_ids": ids,
        }
        return action
