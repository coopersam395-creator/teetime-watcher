# Tee-time cancellation watcher

Checks a Chronogolf club's public tee sheet every couple of minutes and sends a
push notification (via [ntfy](https://ntfy.sh)) when a fully booked slot in your
chosen window frees up. It doesn't log in or book anything.

Configure the club, days, time window and party size in `config.json`.
Set the `NTFY_TOPIC` repository secret to your ntfy channel name.
