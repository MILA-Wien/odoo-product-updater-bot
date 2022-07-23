# SuperCoop Product Updater Script

More info at https://wiki.supercoop.de/wiki/Product_Importer_Script

## Running with Docker

```
docker build -t odoo-product-updater-bot:latest .
# The default CMD in the dockerfile will start into cron mode
docker run odoo-product-updater-bot:latest  python update_from_terra_csv.py --all
```

