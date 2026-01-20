from odoo import api, fields, models


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
