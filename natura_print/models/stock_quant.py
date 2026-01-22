from odoo import fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Compatibility shim: some environments include views referencing stock.quant.reason_note/reason_id.
    # Keeping these fields here prevents upgrade failures until those views are cleaned up.

    # reason_note = fields.Text(string="Reason Note")
    stock_inventory_reason_id = fields.Many2one("stock.inventory.reason", string="Reason")
    # note_required = fields.Boolean(string="Note Required")

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_quant_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_quant_ids": ids,
            "active_ids": ids,
            "active_model": "stock.quant",
        }
        return action
