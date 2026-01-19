from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_quant_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_quant_ids": ids,
            "active_ids": ids,
            "active_model": "stock.quant",
        }
        return action
