from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    natura_print_hostname = fields.Char(
        string="Hostname",
        config_parameter="natura_print.hostname",
    )
    natura_print_api_user = fields.Char(
        string="API User",
        config_parameter="natura_print.api_user",
    )
    natura_print_api_password = fields.Char(
        string="API Password",
        config_parameter="natura_print.api_password",
    )
