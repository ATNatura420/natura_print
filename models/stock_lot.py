from odoo import _, fields, models
from odoo.exceptions import UserError


class StockLot(models.Model):
    _inherit = "stock.lot"

    # Compatibility shim for environments that reference studio fields in views.
    x_studio_batch_result = fields.Char(string="Batch Result")

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_lot_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_lot_ids": ids,
            "active_ids": ids,
            "active_model": "stock.lot",
        }
        return action

    def natura_print_print_label(
        self,
        qty=1,
        template=None,
        template_id=None,
        template_xmlid=None,
        template_name=None,
        printer=None,
        printer_id=None,
        printer_ip=None,
        printer_name=None,
        overrides=None,
    ):
        """Callable from Server Actions / Automated Actions."""
        service = self.env["natura.print.service"]

        template = service.resolve_template(
            self._name,
            template=template,
            template_id=template_id,
            template_xmlid=template_xmlid,
            template_name=template_name,
        )
        if not template:
            raise UserError(_("Missing label template for %s.") % self._description)

        if template.model_id and template.model_id.model and template.model_id.model != self._name:
            raise UserError(
                _(
                    "Template '%(template)s' is for model '%(template_model)s' "
                    "but you are printing '%(record_model)s'."
                )
                % {
                    "template": template.display_name,
                    "template_model": template.model_id.model,
                    "record_model": self._name,
                }
            )

        printer_ip_value = service.resolve_printer_ip(
            printer=printer,
            printer_id=printer_id,
            printer_ip=printer_ip,
            printer_name=printer_name,
        )
        if not printer_ip_value:
            raise UserError(
                _(
                    "Missing printer. Set a default printer in your preferences, "
                    "or pass printer_id / printer_ip / printer_name."
                )
            )

        for record in self:
            service.print_record(
                record,
                template=template,
                printer_ip=printer_ip_value,
                qty=qty or 1,
                overrides=overrides,
            )
