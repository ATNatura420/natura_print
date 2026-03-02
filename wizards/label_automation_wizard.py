import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


class NaturaPrintLabelAutomationWizard(models.TransientModel):
    _name = "natura.print.label.automation.wizard"
    _description = "Natura Print Label Automation Wizard"

    automation_id = fields.Many2one(
        "natura.print.label.automation",
        string="Label Automation Rule",
        required=True,
    )
    source_model = fields.Char(string="Source Model", required=True)
    source_res_id = fields.Integer(string="Source Record ID", required=True)

    def action_run(self):
        self.ensure_one()
        if not self.automation_id or not self.automation_id.webhook_url:
            raise UserError(_("Missing label automation rule or webhook URL."))

        if self.automation_id.model_id and self.automation_id.model_id.model != self.source_model:
            raise UserError(
                _(
                    "Selected automation rule is for %(rule_model)s, but this wizard is for %(source_model)s."
                )
                % {
                    "rule_model": self.automation_id.model_id.model,
                    "source_model": self.source_model,
                }
            )

        payload = {
            "_model": self.automation_id.model_id.model or self.source_model,
            "_id": self.source_res_id,
        }

        try:
            response = requests.post(
                self.automation_id.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Webhook call failed: %s") % exc) from exc

        return {"type": "ir.actions.act_window_close"}
