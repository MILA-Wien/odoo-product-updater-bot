FROM python:slim

RUN apt-get update && apt-get install -y cron ssmtp && rm -rf /etc/cron.*/* && rm -rf /var/lib/{apt,dpkg,cache,log}/
RUN echo "*/2 * * * * /usr/local/bin/python /app/update_from_terra_csv.py --all >/proc/1/fd/1 2>/proc/1/fd/2" > /etc/cron.d/odoo-product-updater-bot && crontab /etc/cron.d/odoo-product-updater-bot && chmod 0644 /etc/cron.d/odoo-product-updater-bot

COPY . /app

WORKDIR /app

RUN pip install -r requirements.txt

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["cron", "-f"]


