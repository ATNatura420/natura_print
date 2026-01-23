import requests

from odoo import _, models
from odoo.exceptions import UserError


class NaturaPrintService(models.AbstractModel):
    _name = "natura.print.service"
    _description = "Natura Print Service"

    def _get_api_config(self):
        params = self.env["ir.config_parameter"].sudo()
        hostname = params.get_param("natura_print.hostname")
        api_user = params.get_param("natura_print.api_user")
        api_password = params.get_param("natura_print.api_password")

        if not hostname or not api_user or not api_password:
            raise UserError(
                _(
                    "Missing configuration. Set Hostname, API User, and API Password "
                    "under Settings > Configuration."
                )
            )
        return hostname, api_user, api_password

    def _post(self, hostname, api_user, api_password, payload, error_label="Print failed"):
        try:
            response = requests.post(
                hostname,
                json=payload,
                auth=(api_user, api_password),
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("%s: %s") % (error_label, exc)) from exc
        return response

    def print_zpl(self, zpl, printer_ip, qty=1, error_label="Print failed"):
        hostname, api_user, api_password = self._get_api_config()
        payload = {
            "zpl": zpl or "",
            "printer_ip": printer_ip,
            "qty": qty or 1,
        }
        return self._post(hostname, api_user, api_password, payload, error_label=error_label)

    def resolve_template(
        self,
        model_name,
        template=None,
        template_id=None,
        template_xmlid=None,
        template_name=None,
    ):
        if template:
            if getattr(template, "_name", None) != "zpl.label.template":
                raise UserError(_("Invalid template passed. Expected a zpl.label.template record."))
            return template

        if template_xmlid:
            try:
                template = self.env.ref(template_xmlid)
            except ValueError as exc:
                raise UserError(_("Template XMLID not found: %s") % template_xmlid) from exc
            if getattr(template, "_name", None) != "zpl.label.template":
                raise UserError(_("XMLID %s did not resolve to a label template.") % template_xmlid)
            return template

        if template_id:
            template = self.env["zpl.label.template"].browse(int(template_id))
            if not template.exists():
                raise UserError(_("Label template not found (id=%s).") % template_id)
            return template

        if template_name:
            template = self.env["zpl.label.template"].search([("name", "=", template_name)], limit=1)
            if not template:
                raise UserError(_("Label template not found (name=%s).") % template_name)
            return template

        return self.env.user._natura_print_get_default_template(model_name)

    def resolve_printer_ip(self, printer=None, printer_id=None, printer_ip=None, printer_name=None):
        if printer_ip:
            return str(printer_ip).strip()

        if printer:
            if getattr(printer, "_name", None) != "printers.list":
                raise UserError(_("Invalid printer passed. Expected a printers.list record."))
            return printer.ip_address

        if printer_id:
            printer = self.env["printers.list"].browse(int(printer_id))
            if not printer.exists():
                raise UserError(_("Printer not found (id=%s).") % printer_id)
            return printer.ip_address

        if printer_name:
            printer = self.env["printers.list"].search([("name", "=", printer_name)], limit=1)
            if not printer:
                raise UserError(_("Printer not found (name=%s).") % printer_name)
            return printer.ip_address

        printer = self.env.user.natura_print_default_printer_id
        return printer.ip_address if printer else ""

    def print_record(self, record, template, printer_ip, qty=1, overrides=None, error_label="Print failed"):
        template.ensure_one()

        if overrides:
            values = template._values_from_record(record) if record else {}
            values.update({str(k): "" if v is None else v for k, v in overrides.items()})
            zpl = template._render_zpl_from_values(values)
        else:
            zpl = template._render_zpl(record)

        return self.print_zpl(zpl, printer_ip, qty=qty, error_label=error_label)
