#!/bin/sh

env >> /etc/environment

echo "
Root=leonh@ndreke.de
AuthMethod=LOGIN
UseTLS=YES
UseSTARTTLS=YES
mailhub=smtp.gmail.com:587
AuthUser=$GMAIL_USER
AuthPass=$GMAIL_PASSWORD
" > /etc/ssmtp/ssmtp.conf && \
	chown root.mail /etc/ssmtp/ssmtp.conf && \
	chmod 0640 /etc/ssmtp/ssmtp.conf

exec "$@"

