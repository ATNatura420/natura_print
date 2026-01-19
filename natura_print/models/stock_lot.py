from odoo import models


class StockLot(models.Model):
    _inherit = "stock.lot"

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_lot_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_lot_ids": ids,
            "active_ids": ids,
            "active_model": "stock.lot",
        }
        return action
