# Purchase Lot & Serial Expiration Tracking with QR Automation (Odoo 19)
**Module:** `purchase_lot_expiry` | **Version:** `19.0.3.1.0` | **License:** LGPL-3

This guide provides a comprehensive walkthrough of the Purchase Lot/Serial synchronization, dynamic QR label printing, zero-click receipt quick scanning, and strict receipt order scope limitations for testing and training with your team.

---

## Table of Contents
1. [Overview & Key Capabilities](#1-overview--key-capabilities)
2. [Zero-Click Quick Scan in Receipts](#2-zero-click-quick-scan-in-receipts)
3. [Strict Receipt Scope Limitations (Anti-Contamination Rules)](#3-strict-receipt-scope-limitations-anti-contamination-rules)
4. [Label Printing Options Explained](#4-label-printing-options-explained)
5. [Warehouse Receiving Scanning Modes](#5-warehouse-receiving-scanning-modes)
6. [Step-by-Step Team Testing Walkthrough](#6-step-by-step-team-testing-walkthrough)
7. [Safety Validation Guards](#7-safety-validation-guards)
8. [Technical Reference & File Map](#8-technical-reference--file-map)

---

## 1. Overview & Key Capabilities

- **Procurement Lot Assignment**: Assign Lot/Serial numbers and expiration dates directly on Purchase Order lines before receiving.
- **Dynamic Lot Redistribution**: Split and redistribute demand quantities across multiple lots via an interactive wizard.
- **Instant Cascade Synchronization**: Automatically propagates lot assignments to linked active stock pickings and draft vendor bills.
- **Zero-Click Quick Scanner Widget in Receipts**: Incorporates the instant scanning technology from sales into warehouse receipts: auto-focus, Arabic keyboard auto-translation, audio chimes (success chime and error buzz), and live DOM reloads without refreshing the page.
- **Strict Receipt Order Scope Enforcement**: Warehouse workers are restricted to scanning **only** the products and lots belonging to the specific receipt being received. Scanning outside products or lots from other orders is strictly rejected.
- **Lot-Centric Pure QR Labels**: Generates product and lot stickers (`PROD:<barcode>|LOT:<lot>|EXP:<date>`) independent of specific operations.
- **Print Anywhere**: Print labels directly from **Inventory > Lots/Serial Numbers** (single form or batch multi-select), from Purchase Orders, Sales Orders, or any Stock Transfer.
- **Precision 1-Scan = 1-Unit Fulfillment**: Every scan adds precisely 1.0 unit.
- **Over-Scanning Prevention**: Strictly blocks scanning once the demanded quantity is reached.
- **Pre-Creation Enforcement**: Scanned lots must pre-exist in the system; creating unknown lots on the fly during receipt scanning is strictly prevented.
- **Safety Locking Guards**: Strictly blocks accidental alteration of PO lots once the receipt is processed (`done`) or vendor bill is posted.

---

## 2. Zero-Click Quick Scan in Receipts

Warehouse operators receiving shipments with barcode/QR scanner guns previously had to click buttons or endure full-page reloads after every item scanned.

The receipt scanning engine has been upgraded with the **Quick Scanner OWL Widget** (`receipt_quick_scanner`):
1. **Zero Mouse Clicks**: The scanner input field maintains constant auto-focus with a pulsing readiness indicator. Point the scanner gun at box labels and pull the trigger.
2. **Audio & Haptic Feedback**:
   - **Success (High Chime - 880Hz)**: Crisp confirmation sound when an item is recognized and received (+1 unit).
   - **Error (Sawtooth Buzz - 220Hz)**: Low warning buzz when a scan fails, over-scanning is attempted, or an unauthorized product/lot is scanned.
   - **Vibration**: Supported on mobile and handheld Android terminal scanners.
3. **Arabic Keyboard Auto-Translation**: Fixes scanner guns that send keystrokes mapped to Arabic keyboard layout (e.g. `PROD` typed as `؛ٌ×]`).
4. **Instant In-Place Reload**: Live Done quantities, progress bars, and move lines update immediately without closing the modal or reloading the webpage.

---

## 3. Strict Receipt Scope Limitations (Anti-Contamination Rules)

To eliminate warehouse receiving errors and cross-order contamination, receipt scanning enforces strict boundaries:

### A. Product Scope Limitation
- Only products that have open moves on the active receipt (`WH/IN/...`) are allowed to be scanned.
- If a worker accidentally scans an item from another vendor, another shipment, or an unassociated product:
  - **Result**: The scan is rejected with a red error badge:
    `"Product '[Product Name]' is not in this receipt order (WH/IN/...). You can only scan products that belong to this receipt."`

### B. Lot Scope Limitation
- When purchase lines specify designated lots (e.g. `LOT-A`, `LOT-B` pre-assigned on the PO):
  - Only those specific pre-assigned lots can be scanned to fulfill that line.
  - If a worker scans a lot sticker belonging to another purchase order, an existing batch in another warehouse, or an unassigned lot:
  - **Result**: The scan is strictly rejected with a detailed error:
    `"Lot 'LOT-XYZ' does not belong to receipt order WH/IN/... for product '[Product Name]'. Only the lots assigned to this receipt order (LOT-A, LOT-B) can be scanned."`

### C. Over-Scanning Prevention
- Every scan accounts for precisely 1.0 unit. If a move has a demand of 5.0 units, attempting a 6th scan is blocked immediately:
  `"Cannot scan: Required quantity (5.0) for '[Product Name]' is already fulfilled (Done: 5.0). Over-scanning is strictly blocked."`

---

## 4. Label Printing Options Explained

When opening the **Print Lot/Serial QR Labels** wizard:

### A. Label Format (Physical Paper & Printer)
| Option | Dimensions | Ideal Use Case |
|---|---|---|
| **Thermal Roll (50 x 30 mm)** | 50mm wide × 30mm high | Dedicated roll printers (Zebra, Brother, Xprinter, Dymo, TSC). Standard carton/box adhesive sticker. |
| **Thermal Roll (40 x 20 mm)** | 40mm wide × 20mm high | Compact thermal roll for smaller parts, hardware, or shelf tags. |
| **Avery Sheet (3 x 4 per page)** | Standard A4 Sheet | Regular office laser/inkjet printers using standard A4 sticker paper (12 peel-off labels per sheet). |

### B. QR Payload Format (Data Encoded Inside the QR Code)
| Option | Encoded String Example | When to Use |
|---|---|---|
| **Structured Delimited** *(Recommended)* | `PROD:887766554433\|LOT:LOT-101\|EXP:2027-09-17` | **Best for standard 2D barcode scanner guns.** Combines SKU, Lot, and Expiration Date with no operation dependencies. |
| **Structured JSON** | `{"b":"887766554433","l":"LOT-101","e":"2027-09-17"}` | Best for mobile phone cameras, automated optical sorters, and API integrations. |
| **Plain Lot Number** | `LOT-101` | Encodes *only* the Lot/Serial text. Best if you want the QR code to behave purely like a traditional 1D barcode. |

---

## 5. Warehouse Receiving Scanning Modes

1. **Inline Quick Scanner Bar (Directly on Receipt Form)**:
   - Visible above the notebook on incoming receipt forms:
     ```text
     [ Quick Receipt Barcode / QR Scanner ] [ Point scanner gun and trigger scan... ]
     ```
   - Automatically processes each scan and refreshes line quantities in place.
2. **Kiosk Scanner Wizard ("Scan QR" Button)**:
   - Click **Scan QR** in the receipt header to enter Kiosk mode.
   - Features the large `receipt_quick_scanner` input, real-time demand vs received progress meters, activity log, and one-click **"Validate Transfer"** when 100% fulfilled.
3. **Mobile Camera Scanner ("Scan via Mobile")**:
   - Activates camera stream on mobile devices/tablets for live optical barcode scanning.

---

## 6. Step-by-Step Team Testing Walkthrough

### Step 1: Create a Tracked Product & Pre-Assign Lots on PO
1. Create a product with **Tracking** set to `By Lots`.
2. Create a **Purchase Order**, add the product (Quantity = 5.0).
3. In the PO line, select or create lot `LOT-REC-01` (Expiry: 2027-01-01).
4. Confirm the Purchase Order.

### Step 2: Open the Incoming Receipt
1. Click the **Receipt** smart button (`WH/IN/...`).
2. Notice the Quick Scanner bar is active above the operations notebook.

### Step 3: Test Scope Limitation (Negative Tests)
1. **Test A (Foreign Product)**: Scan a QR code for a completely different product not on this PO.
   - **Expected Result**: Error buzz + red alert:
     `"Product '...' is not in this receipt order (WH/IN/...). You can only scan products that belong to this receipt."`
2. **Test B (Foreign Lot)**: Scan a QR code with the correct product barcode but a lot not assigned to this PO (e.g. `LOT-UNKNOWN`).
   - **Expected Result**: Error buzz + red alert:
     `"Lot 'LOT-UNKNOWN' does not belong to receipt order WH/IN/... for product '...'. Only the lots assigned to this receipt order (LOT-REC-01) can be scanned."`

### Step 4: Test Authorized Scan (Positive Test)
1. Scan the authorized QR payload: `PROD:<barcode>|LOT:LOT-REC-01|EXP:2027-01-01`.
2. **Expected Result**:
   - Crisp high chime sound plays.
   - Done quantity increments by 1.0 unit.
   - Field auto-clears and retains focus for the next scan.
3. Continue scanning until all 5 units are fulfilled.
4. Click **Validate** to mark receipt as Done.

---

## 7. Safety Validation Guards

- **Locked Completed Receipts**: Once a linked incoming receipt (`stock.picking`) is in `done` state, PO lot numbers, expiration dates, and quantities are strictly locked.
- **Posted Vendor Bills**: Once a linked vendor bill (`account.move`) is posted, PO line lot allocations are locked.
- **Clearance Stage Guard**: In import purchase workflows, receipts remain locked in view-only mode until the vendor bill / PO reaches the **Clearance** logistics stage.

---

## 8. Technical Reference & File Map

| File Path | Description |
|---|---|
| `static/src/widgets/receipt_quick_scanner/` | OWL component providing zero-click receipt scanning, auto-focus, audio chimes, and Arabic keystroke decoding. |
| `models/stock_picking.py` | Receipt QR processing engine, strict product/lot scope validations, and `action_quick_scan` RPC endpoint. |
| `wizard/stock_picking_qr_scan_wizard.py` | Warehouse receipt scanning kiosk with `action_quick_scan` integration. |
| `wizard/stock_picking_qr_scan_wizard_views.xml` | Kiosk modal view integrating the `receipt_quick_scanner` widget. |
| `views/stock_picking_views.xml` | Stock picking form view extensions with inline `receipt_quick_scanner` bar. |
| `models/purchase_order_line.py` | PO Line lot allocations, expiration computations, and cascade sync to receipts. |
| `wizard/purchase_lot_qr_wizard.py` | Dynamic QR code label printing wizard (Thermal 50x30, 40x20, Avery A4). |
| `report/purchase_lot_qr_report_templates.xml` | QWeb PDF label layouts. |
