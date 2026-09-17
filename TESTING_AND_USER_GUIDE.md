# Purchase Lot & Serial Expiration Tracking with QR Automation (Odoo 19)
**Module:** `purchase_lot_expiry` | **Version:** `19.0.2.0.0` | **License:** LGPL-3

This guide provides a comprehensive walkthrough of the Lot/Serial synchronization, dynamic QR label printing, and warehouse receiving scanning workflows for testing and training with your team.

---

## Table of Contents
1. [Overview & Key Capabilities](#1-overview--key-capabilities)
2. [Label Printing Options Explained](#2-label-printing-options-explained)
3. [Warehouse Scanning Modes](#3-warehouse-scanning-modes)
4. [Step-by-Step Team Testing Walkthrough](#4-step-by-step-team-testing-walkthrough)
5. [Safety Validation Guards (Anti-Divergence Rules)](#5-safety-validation-guards-anti-divergence-rules)
6. [Technical Reference & File Map](#6-technical-reference--file-map)

---

## 1. Overview & Key Capabilities

- **Procurement Lot Assignment**: Assign Lot/Serial numbers and expiration dates directly on Purchase Order lines before receiving.
- **Dynamic Lot Redistribution**: Split and redistribute demand quantities across multiple lots via an interactive wizard.
- **Instant Cascade Synchronization**: Automatically propagates lot assignments and quantity updates to:
  - Linked active incoming stock pickings (`stock.move.line`).
  - Linked draft vendor bills (`account.move.line`).
- **Native QR Label Printing**: Generates print-ready QR codes dynamically using Odoo's built-in barcode engine.
- **1-Scan Warehouse Fulfillment**: Warehouse receivers scan a single QR code to identify product, lot, expiry date, and quantity in one pass.
- **Safety Locking Guards**: Strictly blocks accidental alteration of PO lots once the receipt is processed (`done`) or vendor bill is posted.

---

## 2. Label Printing Options Explained

When opening the **Print Lot/Serial QR Labels** wizard (accessible from the **Purchase Order** or **Stock Receipt** header), you will see the following settings:

### A. Label Format (Physical Paper & Printer)
| Option | Dimensions | Ideal Use Case |
|---|---|---|
| **Thermal Roll (50 x 30 mm)** | 50mm wide × 30mm high | Dedicated roll printers (Zebra, Brother, Xprinter, Dymo, TSC). Standard carton/box adhesive sticker. |
| **Thermal Roll (40 x 20 mm)** | 40mm wide × 20mm high | Compact thermal roll for smaller parts, hardware, jewelry, or shelf tags. |
| **Avery Sheet (3 x 4 per page)** | Standard A4 Sheet | Regular office laser/inkjet printers using standard A4 sticker paper (12 peel-off labels per sheet). |

### B. QR Payload Format (Data Encoded Inside the QR Code)
| Option | Encoded String Example | When to Use |
|---|---|---|
| **Structured Delimited** *(Recommended)* | `PROD:887766554433\|LOT:LOT-101\|EXP:2027-09-17\|QTY:10.0` | **Best for standard 2D barcode scanner guns.** Combines SKU, Lot, Expiration Date, and Quantity with no JSON escaping. |
| **Structured JSON** | `{"b":"887766554433","l":"LOT-101","e":"2027-09-17","q":10.0}` | Best for mobile phone cameras, automated optical sorters, and API integrations. |
| **Plain Lot Number** | `LOT-101` | Encodes *only* the Lot/Serial text. Best if you want the QR code to behave purely like a traditional 1D barcode. |

---

## 3. Warehouse Scanning Modes

When receiving goods in the warehouse, open the incoming receipt (`WH/IN/...`). You have two scanning workflows:

### Mode 1: Fast QR Scan Bar (Directly on the Form)
- Located directly above the Operations table on the receipt form:
  ```text
  [ Fast QR Scan ] [ Scan Lot / Product QR Code here... ]  [ Scan ]
  ```
- **Action**: Click into the field (or scan with a wireless 2D barcode gun).
- **Result**: Odoo matches the product, assigns the lot, increments the received quantity, and shows a green status message:
  `✓ Scanned [Product Name] | Lot: LOT-101 | Qty: +10.0 (Done: 10.0 / 10.0)`

### Mode 2: Warehouse Kiosk Scanner Wizard ("Scan Receipt QR")
- Click the **Scan Receipt QR** button in the receipt's top header.
- A dedicated modal dialog opens with:
  1. Auto-focused large scan input field.
  2. Live progress tracker (Demand vs Received quantities per product and lot).
  3. Real-time audit log with timestamped scan activity.
  4. Automatic **"Validate Receipt"** button activation once all lines reach 100% completion.

---

## 4. Step-by-Step Team Testing Walkthrough

Follow these 6 steps to test the entire lifecycle with your colleagues:

### Step 1: Create a Tracked Product & Lots
1. Navigate to **Inventory > Products > Products**.
2. Create or open a product and ensure **Tracking** is set to `By Lots` or `By Unique Serial Number`.
3. Give the product an **Internal Reference** (e.g. `PROD-TEST-01`) and a **Barcode** (e.g. `887766554433`).

### Step 2: Create and Confirm a Purchase Order
1. Go to **Purchase > Orders > Purchase Orders** and click **New**.
2. Select a Vendor and add an order line for your tracked product (e.g., Quantity = `10.0`).
3. In the **Lots/Serial Numbers** column, select or create two lots:
   - `LOT-A` (Allocated: 6.0, Expiry: 1 year from today)
   - `LOT-B` (Allocated: 4.0, Expiry: 6 months from today)
   *(If assigning multiple lots, click the **Redistribute** button to set individual quantities).*
4. Click **Confirm Order**.

### Step 3: Verify Receipt Allocation & Redistribution
1. Click the **Receipt** smart button on the PO to open the incoming transfer (`WH/IN/...`).
2. Notice that the receipt's operation lines already have `LOT-A` (6.0) and `LOT-B` (4.0) pre-allocated!
3. *(Optional Test)* Go back to the PO line, click **Redistribute**, change quantities to `7.0` and `3.0`, and confirm. Return to the receipt: the lines are immediately updated to `7.0` and `3.0`.

### Step 4: Print QR Labels
1. On the Purchase Order or the Receipt, click **Print Lot QR Labels**.
2. Select **Thermal Roll (50 x 30 mm)** and **Structured Delimited**.
3. Click **Print QR Labels**:
   - The PDF downloads with pages formatted to **50mm × 30mm**.
   - Each label features the dynamic QR code on the left and Product Name, Barcode, Bold Lot Number, Expiration Date, and Quantity on the right.
4. *(Optional Test)* Switch to **Avery Sheet (3 x 4 per page)**: Odoo prints a standard A4 sheet with 12 labels in a grid.

### Step 5: Test QR Code Scanning
1. On the Receipt (`WH/IN/...`), test scanning either:
   - **Method A**: Scan the printed QR code (or paste the payload `PROD:887766554433|LOT:LOT-A|EXP:2027-09-17|QTY:7.0`) into the **Fast QR Scan** input on the form.
   - **Method B**: Click **Scan Receipt QR** in the header to open Kiosk Mode, scan the QR code, and watch the live progress bar update.
2. Once all items are scanned, click **Validate Receipt**.
3. The transfer state changes to **Done**.

### Step 6: Test the Safety Guard
1. Return to the Purchase Order.
2. Attempt to delete or edit the Lot/Serial numbers or order quantity on the line.
3. **Expected Result**: Odoo intercepts the action and displays a safety error:
   > *"Cannot modify Lot/Serial numbers, quantities, or expiration dates on PO line because linked receipt(s) have already been processed and marked as Done. Please process returns or scrap adjustments instead."*

---

## 5. Safety Validation Guards (Anti-Divergence Rules)

To prevent accounting and inventory mismatches:
- If a linked incoming receipt (`stock.picking`) is in `done` state:
  **PO lot numbers, expiration dates, and quantities are locked.**
- If a linked vendor bill (`account.move`) is in `posted` state:
  **PO lot numbers, expiration dates, and quantities are locked.**
- If the receipt is still in `draft`, `waiting`, or `assigned` (ready) state:
  **Modifications cascade automatically to update stock move lines and draft vendor bills.**

---

## 6. Technical Reference & File Map

| File Path | Description |
|---|---|
| `models/purchase_order_line.py` | PO Line lot allocations, cascade sync, and safety validation guards. |
| `models/stock_picking.py` | Fast scanner input, multi-format QR parser, and receipt QR triggers. |
| `wizard/purchase_lot_redistribute_wizard.py` | Interactive lot redistribution wizard with safety checks. |
| `wizard/purchase_lot_qr_wizard.py` | Dynamic QR code generation wizard with layout options. |
| `wizard/stock_picking_qr_scan_wizard.py` | Dedicated warehouse kiosk scanning wizard with one-click validation. |
| `report/purchase_lot_qr_report.xml` | Report action and custom paperformat definitions (50x30mm, 40x20mm). |
| `report/purchase_lot_qr_report_templates.xml` | QWeb PDF report templates using Odoo's dynamic barcode engine. |
| `views/purchase_order_views.xml` | PO form view extensions and "Print Lot QR Labels" button. |
| `views/stock_picking_views.xml` | Stock receipt form view extensions, fast scanner bar, and header buttons. |
| `security/ir.model.access.csv` | Access rights for all models and transient wizards. |
| `__manifest__.py` | Module metadata, dependencies (`barcodes`), and registered data files. |
