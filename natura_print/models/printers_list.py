from odoo import fields, models

class PrintersList(models.Model):
    _name = "printers.list"
    _description = "List of Printers"

    name = fields.Char('Printer Name', required=True, translate=True)
    location = fields.Text('Location', translate=True)
    ip_address = fields.Char('IP Address', required=True)
    dpi = fields.Selection(
        [('203', '8 dpmm (203 DPI)'), ('300', '12 dpmm (300 DPI)'), ('600', '24 dpmm (600 DPI)')],
        string='DPI',
        help="Dots Per Inch - print resolution",
        required=True,
    )
    note = fields.Text('Note', translate=True)
    active = fields.Boolean(
        'Active',
        default=True,
        help="If unchecked, it will allow you to hide the printer without removing it.",
    )