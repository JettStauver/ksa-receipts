# Category folders

This is the fixed list of categories for every year. Use the names exactly (spelling, ampersands, spacing). To add a category, update this table and release a new plugin version.

| Folder | Put here | Typical vendors / clues |
|---|---|---|
| 1099 Information | 1099s and W-9s received/sent, contractor payment summaries | "Form 1099", W-9 requests |
| Accounting & Tax Expenses | Bookkeeping, CPA, tax prep, estimated/sales/franchise tax payments, payroll service fees | QuickBooks, IRS/EFTPS, Texas Comptroller, CPA firm |
| Automobile & Licensing | Vehicle registration, inspection fees, tolls tags, business licenses, fuel for business vehicle | TxDMV, state license fees |
| Cost of Goods Sold | Parts and materials bought for resale or for a customer job; instrument parts; sample-holder manufacturing materials; Bruker purchases for resale | Bruker, Digi-Key, McMaster-Carr, Online Metals, eBay parts |
| Deposited Payment Records | Payments **received** from customers (remittance advice, ACH/wire notices) | Customer remittances - not expenses |
| Dues & Subscriptions & Events | Memberships, trade shows, conference registration, publications | ICDD, MS&T/DXC registration, LabX |
| Equipment & Machinery | Capital equipment and instruments KSA keeps (not resale) | Large tool/instrument purchases |
| Fixtures & Racks & Tools | Hand tools, shop fixtures, shelving, test gear under capital threshold | Harbor Freight, Home Depot tools |
| Inspection Records | Radiation/safety inspection fees, licensing inspections, calibration certificates | State radiation control, calibration labs |
| Insurance Expenses | Business insurance premiums | Liability, auto, workers comp |
| Maintenance & Repair | Repairs to KSA facility, vehicles, equipment | Repair shops, HVAC service |
| Meals & Entertainment | Business meals, customer entertainment | Restaurants on travel days or with customers |
| Office & Facility Supplies | Office supplies, printer ink, cleaning, small furniture, postage supplies | Staples, Amazon office items |
| Owners Draw | Owner draws/distributions, and personal purchases paid with **business** funds | See rule below |
| Received Packing Slips | Packing slips and delivery documents with no price | Shipment packing lists |
| Shipping & Freight | Postage, couriers, freight, crating, shipping brokers | USPS, UPS, FedEx, MoveIt, RL Carriers |
| Software & Internet & IT Services | SaaS, software licenses, domains, hosting, internet/phone service, AI tools | Anthropic, Google Workspace, Microsoft, Sectigo |
| Travel Expenses | Airfare, hotels, rental cars, airport parking, tolls, rideshare, travel fuel | Airlines, Hilton, NTTA, DFW Parking, Hertz |
| Utilities | Electricity, water, gas, trash for the facility | Utility providers |

**Personal** (added for this plugin, one per year): purchases that are not business expenses.

**Home Office - Indirect** (added for this plugin, one per year): household bills for the home-office address in `_settings` (`ADDRESS home-office ...`) (city utilities, home gas/electric, water, trash, lawn care, home internet, home repairs). Not deductible directly; kept so the share for home-office use can be calculated. Never put these in Utilities - that folder is for the business address (`ADDRESS business ...` in `_settings`).

## Rules

- Packing slips with prices are receipts or invoices - categorize by what was bought. Price-less slips go to Received Packing Slips only if one has a corresponding order; otherwise skip them (they are not receipts).
- Personal purchase paid with a **business** card or account: ask the user whether it belongs in `Personal` or `Owners Draw` the first time a given situation comes up, and record the answer as a `RULE` setting (see `dedupe.md` section 5).
- Regular monthly phone and data service plan payments (Verizon, AT&T, etc. - autopay or bill-pay confirmations): always Business, Software & Internet & IT Services. One-off phone-store purchases (devices, cases, accessories, in-store payments that are not the monthly plan) are not covered by this rule - ask, and lean Personal.
- Travel meals: Meals & Entertainment, not Travel Expenses.
- Fuel: Travel Expenses when on a trip; Automobile & Licensing for local business-vehicle fuel. Ask if unclear.
- Parts for a specific customer's instrument repair: Cost of Goods Sold.
- When nothing fits, ask. Do not invent new category folders.
