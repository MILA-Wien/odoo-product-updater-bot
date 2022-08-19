# SuperCoop Product Updater Script

## Running with Docker

```
docker build -t odoo-product-updater-bot:latest .
# The default CMD in the dockerfile will start into cron mode
docker run odoo-product-updater-bot:latest  python update_from_terra_csv.py --all
```

## Description from SuperCoop Wiki

### Original Text by Leon:

Leon has written 100 lines of Python to import data from an Excel spreadsheet we get from our wholesaler Terra into the
product database (https://github.com/SuperCoopBerlin/odoo-product-updater-bot). It runs as a cronjob every minute. The
following should happen:

- Clean up the code and make it readable by other people
- Use the CSV files in BNN format delivered by Terra daily using FTP (pending setup from Terra)
- Possibly extend to other wholesalers at some point?
- Be the primary point of contact if something goes wrong. Cron will let you know :)

Contact Person: Khaled

### Knowledge Collection

Here we are collecting the knowledge about the different import/export tasks that are currently carried out by script or
manually.

#### Import entire product catalog from Terra in BNN3 format

- loaded once per day from Terra FTP server
- BNN-3 is a CSV format with specific column definition.
- compares new download with existing data and feeds the differences into Odoo via API

#### Fill new product definitions with Terra data

- runs every two minutes
- needs EAN code (usually the barcode on the product)
- is triggered if the product name is NEW
- is looking for the EAN code in Terra database and fills the missing fields in the Odoo product catalog
- image for POS is scraped from Terra webshop
- sets some accounting data to avoid additional manual work

#### Import product catalog from AGIDRA

- sent from AGIDRA as email in Excel format as order confirmation (sample? link here!)

#### Orders

- Excel sheet is generated as Odoo export per supplier manually
- the Excel sheet is sent by mail to supplier

#### What do we want to achieve?

- readability for better maintenance in the future
- more structure with a common architecture for import and export jobs
- more automation of currently manual processes
- stability and robustness
- improve electronic communication with suppliers
- extend the use of standard formats, e.g. BNN-4
