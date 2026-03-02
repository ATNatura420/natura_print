from odoo import _, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    natura_print_default_template_id = fields.Many2one(
        "zpl.label.template",
        string="Default Label Template",
        domain="[('model_id.model', 'in', ('product.template', 'stock.lot', 'stock.quant', 'mrp.production')), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids), '|', ('is_product_specific', '=', False), ('product_tmpl_id', '=', id)]",
        help="If set, this template is used as the default in label print wizards for this product when the template model matches the wizard model.",
    )

    def _natura_print_get_default_template_for_model(self, model_name):
        self.ensure_one()
        template = self.natura_print_default_template_id
        if not template:
            return False
        if template.model_id.model != model_name:
            return False
        if template.company_id and template.company_id not in self.env.companies:
            return False
        if template.is_product_specific and template.product_tmpl_id != self:
            return False
        return template

    def action_open_print_wizard(self):
        action = self.env.ref("natura_print.action_natura_print_product_label_wizard").read()[0]
        ids = self.env.context.get("active_ids") or self.ids
        action["context"] = {
            "default_product_ids": ids,
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
