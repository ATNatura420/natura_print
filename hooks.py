from odoo import api, SUPERUSER_ID


def post_init_hook(cr_or_env, registry=None):
    # Odoo versions calling with env
    if registry is None:
        env = cr_or_env
    else:
        env = api.Environment(cr_or_env, SUPERUSER_ID, {})
    users = env["res.users"].search([])
    for user in users:
        user._natura_print_ensure_template_prefs()
