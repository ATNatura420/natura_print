# Natura Print (Odoo 17)

Natura Print is an Odoo 17 addon that manages ZPL label templates, printers, and
print workflows across Product, Lot/Serial, Quant, and MRP Production. It
supports placeholder mapping (including field paths), batch CSV printing,
"print with edits" overrides, and Labelary previews.

## Key Features

- ZPL template management with placeholder mapping.
- Printer list and API-based label output with Basic Auth.
- Print wizards for Product, Lot/Serial, Quant, and MRP Production.
- CSV-based printing with header or column index mapping and batching.
- "Print with Edits" wizard to override placeholder values at print time.
- Labelary preview in the template form.
- User preferences for default printer and default template per model.
- Automation friendly helper methods (one-liner server actions).

## Module Layout

```
custom_addons/natura_print/
  __manifest__.py
  __init__.py
  hooks.py

  models/
    __init__.py
    zpl_label_templates.py
    label_template_placeholder.py
    placeholder_path.py
    printers_list.py
    product_template.py
    stock_lot.py
    stock_quant.py
    mrp_production.py
    res_config_settings.py
    res_users.py
    template_model_link.py

  wizards/
    product_label_wizard.py
    lot_label_wizard.py
    quant_label_wizard.py
    mrp_label_wizard.py
    test_print_wizard.py
    csv_label_wizard.py
    edited_label_wizard.py

  views/
    natura_print_menus.xml
    label_template_views.xml
    label_template_placeholder_views.xml
    printers_list_views.xml
    product_template_views.xml
    stock_lot_views.xml
    stock_quant_views.xml
    mrp_production_views.xml
    res_config_settings_views.xml
    res_users_views.xml
    product_label_wizard_views.xml
    lot_label_wizard_views.xml
    quant_label_wizard_views.xml
    mrp_label_wizard_views.xml
    test_print_wizard_views.xml
    csv_label_wizard_views.xml
    edited_label_wizard_views.xml

  security/
    ir.model.access.csv

  static/
    src/css/natura_print.css
```

## Configuration

### System Parameters

Stored in `ir.config_parameter`:

- `natura_print.hostname`
- `natura_print.api_user`
- `natura_print.api_password`

### User Preferences

Stored on `res.users` and editable under Profile > Preferences:

- `natura_print_default_printer_id`
- per-model default template (user preference records)
- `natura_print_csv_encoding`

## Printing API Payload

```
{
  "zpl": "<ZPL STRING>",
  "printer_ip": "10.1.0.35",
  "qty": 1
}
```

## ZPL Template Rendering

Templates use placeholders like `${product_name}`. Mappings are stored in
`natura.print.placeholder`. Field paths support multi-hop access, such as:

- `product_id.barcode`
- `procurement_group_id.name`

The `_render_zpl(record)` method on `zpl.label.template` builds the final ZPL.

## Helper Method (Automation Friendly)

Each default model has a helper to print from server actions without imports.

Example from `product.template`:

```python
def natura_print_print_label(self, qty=1):
    user = self.env.user
    template = user._natura_print_get_default_template(self._name)
    printer = user.natura_print_default_printer_id

    if not template:
        raise UserError(_("Missing default label template for %s.") % self._description)
    if not printer:
        raise UserError(_("Missing default printer in your preferences."))

    params = self.env["ir.config_parameter"].sudo()
    hostname = params.get_param("natura_print.hostname")
    api_user = params.get_param("natura_print.api_user")
    api_password = params.get_param("natura_print.api_password")

    if not hostname or not api_user or not api_password:
        raise UserError(_("Missing configuration. Set Hostname, API User, and API Password."))

    for record in self:
        zpl = template._render_zpl(record)
        payload = {"zpl": zpl, "printer_ip": printer.ip_address, "qty": qty or 1}
        response = requests.post(hostname, json=payload, auth=(api_user, api_password), timeout=10)
        response.raise_for_status()
```

Helper added to:

- `product.template`
- `stock.lot`
- `stock.quant`
- `mrp.production`

### Server Action One-liner

```
record.natura_print_print_label()
```

## CSV Print Wizard

- Appears only when a single record is selected.
- CSV parsing uses header row (row 1) and fallback by column index (A/B/C or 1/2/3).
- Start row default is 2.
- Batch size defaults to 12 ZPL labels per API call.

## Print With Edits Wizard

- Shows placeholders with current values.
- Supports per-placeholder "New Value" override at print time.
- Preview update is optional and can be disabled if not needed.

## Compatibility Shims

Some environments include fields in views that are not present in this module:

### stock.quant

```
reason_note = fields.Text(string="Reason Note")
reason_id = fields.Many2one("stock.inventory.reason", string="Reason")
note_required = fields.Boolean(string="Note Required")
```

### stock.lot

```
x_studio_batch_result = fields.Char(string="Batch Result")
```

These prevent view parse errors if other modules or Studio customizations
reference those fields.

## MRP Enhancements

`mrp.production` adds:

- `child_mo_ids` (computed Many2many)
- `child_lot_ids` (computed Many2many)

This enables templates to pull data from child MOs and lots.

## Upgrade Command (DevHost/CloudPepper)

```
cd /var/odoo/natura17-stage-db && \
sudo -u odoo venv/bin/python3 src/odoo-bin -c odoo.conf \
  --no-http --stop-after-init --update all
```

## Notes

- Odoo 17 no longer supports `attrs`/`states` in views. Use `invisible`, `readonly`.
- View modifiers require fields to appear in the view XML, even if invisible.
- If staging has missing columns for user preferences, add columns or perform a full module install/upgrade.
