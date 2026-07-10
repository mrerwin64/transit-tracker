#!/bin/bash
python rt_downloader.py &
RT_PID=$!

supercronic /app/syncer_crontab &
CRON_PID=$!

trap 'kill -TERM $RT_PID $CRON_PID 2>/dev/null; wait $RT_PID $CRON_PID 2>/dev/null; exit 0' TERM INT

wait -n $RT_PID $CRON_PID

kill $RT_PID $CRON_PID
wait $RT_PID $CRON_PID

exit 1