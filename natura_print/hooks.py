from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    users = env["res.users"].search([])
    for user in users:
        user._natura_print_ensure_template_prefs()
